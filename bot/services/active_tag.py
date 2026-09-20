import logging
import html
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from bot.database import db
from bot.filters.admin import invalidate_chat_admins_cache

logger = logging.getLogger(__name__)

def get_chat_today_date_str(gmt_offset: int = 5) -> str:
    """Guruhning GMT mintaqasi bo'yicha bugungi sanani YYYY-MM-DD formatida qaytaradi."""
    tz = timezone(timedelta(hours=gmt_offset))
    return datetime.now(tz).strftime("%Y-%m-%d")

async def grant_active_tag(bot: Bot, chat_id: int, user_id: int, custom_title: str = "Active") -> Tuple[bool, str]:
    """
    Foydalanuvchiga Telegramda rasmiy 'Active' (yoki ko'rsatilgan) unvonini beradi.
    Xavfsizlik: Barcha ma'muriy huquqlar (o'chirish, cheklash va h.k.) False qilib qo'yiladi.
    """
    clean_title = custom_title.strip()[:16] or "Active"
    try:
        # 1. Xavfsiz huquqlar bilan administrator sifatida ko'tarish
        await bot.promote_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_invite_users=True,
            can_change_info=False,
            can_delete_messages=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_manage_video_chats=False,
            can_manage_topics=False,
            is_anonymous=False
        )
        # 2. Telegram nishoni (Custom Title) ni o'rnatish
        await bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=user_id,
            custom_title=clean_title
        )
        # Keshni yangilaymiz
        invalidate_chat_admins_cache(chat_id)
        return True, f"«{clean_title}» unvoni muvaffaqiyatli berildi!"
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "not enough rights" in err_msg or "right_forbidden" in err_msg:
            return False, "Botda guruh a'zolariga unvon berish huquqi (can_promote_members) yo'q. Iltimos botga admin ko'tarish huquqini bering!"
        elif "user is an administrator of the chat" in err_msg:
            # Foydalanuvchi allaqachon admin bo'lsa faqat unvonini yangilashga urinib ko'ramiz
            try:
                await bot.set_chat_administrator_custom_title(
                    chat_id=chat_id,
                    user_id=user_id,
                    custom_title=clean_title
                )
                invalidate_chat_admins_cache(chat_id)
                return True, f"Mavjud admin uchun «{clean_title}» unvoni o'rnatildi!"
            except Exception as e2:
                return False, f"Foydalanuvchi allaqachon boshqa admin tomonidan tayinlangan, unvonini o'zgartirib bo'lmadi: {e2}"
        return False, f"Telegram xatoligi: {e}"
    except Exception as e:
        logger.error(f"grant_active_tag xatoligi: {e}")
        return False, f"Kutilmagan xatolik yuz berdi: {e}"

async def revoke_active_tag(bot: Bot, chat_id: int, user_id: int) -> Tuple[bool, str]:
    """
    Foydalanuvchining 'Active' unvonini bekor qilib, oddiy a'zo holatiga qaytaradi.
    """
    try:
        await bot.promote_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_invite_users=False,
            can_change_info=False,
            can_delete_messages=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_manage_video_chats=False,
            can_manage_topics=False,
            is_anonymous=False
        )
        invalidate_chat_admins_cache(chat_id)
        return True, "«Active» unvoni muvaffaqiyatli olib tashlandi va oddiy a'zo holatiga qaytarildi."
    except Exception as e:
        logger.error(f"revoke_active_tag xatosi: {e}")
        return False, f"Unvonni bekor qilishda xatolik: {e}"

async def process_user_activity_and_check_reward(bot: Bot, chat_id: int, user, gmt_offset: int = 5):
    """
    Xabar kelganda foydalanuvchining kunlik faolligini hisoblaydi va 10 ta xabar bo'lganda 'Active' unvonini beradi.
    """
    date_str = get_chat_today_date_str(gmt_offset)
    count, granted = await db.record_user_activity(chat_id, user.id, date_str)

    # Guruh sozlamalarini olamiz
    settings = await db.get_all_chat_settings(chat_id)
    if not settings.get("active_tag_enabled", True):
        return

    threshold = int(settings.get("active_tag_threshold", 10))
    if count >= threshold and not granted:
        success, msg = await grant_active_tag(bot, chat_id, user.id, "Active")
        if success:
            await db.mark_active_granted(chat_id, user.id, date_str)
            from bot.services.cleaner import auto_delete
            from bot.services.logger import send_log

            congrats_text = (
                f"🎖 <a href=\"tg://user?id={user.id}\">{html.escape(user.full_name)}</a> "
                f"bugun guruhda faol bo'lganingiz uchun sizga <b>«Active»</b> unvoni (tag) berildi!\n"
                f"📊 Bugungi xabarlaringiz: <b>{count} ta</b>"
            )
            try:
                sent = await bot.send_message(chat_id=chat_id, text=congrats_text, parse_mode="HTML")
                auto_delete(sent, delay=45)
            except Exception as e:
                logger.debug(f"Tabrik xabarini yuborishda xatolik: {e}")

            log_text = (
                f"🎖 <b>YANGI «ACTIVE» UNVONI BERILDI</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>A'zo:</b> <a href=\"tg://user?id={user.id}\">{html.escape(user.full_name)}</a>\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"💬 <b>Bugungi xabarlari:</b> {count} ta\n"
                f"⚡️ <b>Turi:</b> Avtomatik (Kunlik {threshold} ta xabar)"
            )
            asyncio.create_task(send_log(bot, log_text, category="members"))
