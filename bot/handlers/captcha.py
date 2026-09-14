import asyncio
import logging
from typing import Dict, Any
from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    ChatMemberUpdated,
    ChatPermissions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from bot.config import config
from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.services.logger import log_captcha
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="captcha")

# Tasdiqlashni kutayotgan foydalanuvchilar: user_id -> task & metadata
pending_captchas: Dict[int, Dict[str, Any]] = {}

def get_captcha_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Faqat bitta tugmali qulay tasdiqlash klaviaturasi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Men robot emasman",
                    callback_data=f"verify_captcha:{user_id}"
                )
            ]
        ]
    )

async def _captcha_timeout_worker(bot: Bot, chat_id: int, user_id: int, message_id: int):
    """Belgilangan vaqt ichida tugmani bosmasa guruhdan chiqarish."""
    try:
        await asyncio.sleep(config.CAPTCHA_TIMEOUT)
        
        # Agar hali ham tasdiqlamagan bo'lsa
        if user_id in pending_captchas:
            del pending_captchas[user_id]
            
            # Xabarni o'chirish
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                pass
                
            # Foydalanuvchini kick qilish (chiqarib yuborish)
            try:
                user_info = await bot.get_chat_member(chat_id, user_id)
                await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
                
                await log_captcha(
                    bot=bot,
                    user=user_info.user,
                    passed=False,
                    reason=f"{config.CAPTCHA_TIMEOUT} soniya ichida tasdiqlash tugmasini bosmadi."
                )
            except Exception as e:
                logger.error(f"Foydalanuvchini kick qilishda xatolik ({user_id}): {e}")
    except asyncio.CancelledError:
        pass

@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER), IsGroupFilter())
async def on_user_joined_chat_member(event: ChatMemberUpdated, bot: Bot):
    """Telegram 7.0+ hodisasi orqali yangi a'zo qo'shilganda ishlaydi."""
    user = event.new_chat_member.user
    if user.is_bot:
        return

    chat = event.chat

    # Admin paneldan Captcha o'chirilgan bo'lsa tekshirish
    if not await db.get_chat_setting_bool(chat.id, "captcha_enabled", default=True):
        return

    # 1. Guruhda yozish huquqini darhol cheklaymiz
    try:
        await bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
        )
    except Exception as e:
        logger.warning(f"Foydalanuvchini cheklashda xatolik ({user.id}): {e}")

    # 2. Captcha xabarini yuboramiz
    text = (
        f"👋 Assalomu alaykum, <a href=\"tg://user?id={user.id}\">{user.full_name}</a>!\n\n"
        f"🤖 Guruhda spamlarni oldini olish uchun pastdagi tugmani bosing.\n"
        f"⏳ Sizga berilgan vaqt: <b>{config.CAPTCHA_TIMEOUT} soniya</b>."
    )
    
    try:
        msg = await bot.send_message(
            chat_id=chat.id,
            text=text,
            reply_markup=get_captcha_keyboard(user.id),
            parse_mode="HTML"
        )
        
        # Taymer vazifasini ishga tushiramiz
        task = asyncio.create_task(
            _captcha_timeout_worker(bot, chat.id, user.id, msg.message_id)
        )
        pending_captchas[user.id] = {
            "chat_id": chat.id,
            "message_id": msg.message_id,
            "task": task
        }
    except Exception as e:
        logger.error(f"Captcha xabarini yuborishda xatolik: {e}")

@router.callback_query(F.data.startswith("verify_captcha:"))
async def on_captcha_verified(callback: CallbackQuery, bot: Bot):
    """Tugma bosilganda captchani tekshirish."""
    parts = callback.data.split(":")
    if len(parts) < 2:
        return
        
    target_user_id = int(parts[1])
    
    # Begona foydalanuvchi bossa ogohlantiramiz
    if callback.from_user.id != target_user_id:
        await callback.answer("⚠️ Bu tugma siz uchun emas!", show_alert=True)
        return
        
    user = callback.from_user
    chat = callback.message.chat
    
    # 1. Taymerni bekor qilamiz
    if user.id in pending_captchas:
        task_info = pending_captchas.pop(user.id)
        if "task" in task_info and not task_info["task"].done():
            task_info["task"].cancel()
            
    # 2. Xabar yozish ruxsatini qaytarib beramiz
    try:
        await bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
    except Exception as e:
        logger.error(f"Ruxsat berishda xatolik ({user.id}): {e}")

    # 3. Captcha xabarini o'chiramiz
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    # 4. Foydalanuvchiga xush kelibsiz xabari (chat toza bo'lishi uchun 15 soniyada o'chiriladi)
    welcome_msg = await bot.send_message(
        chat_id=chat.id,
        text=(
            f"🎉 <a href=\"tg://user?id={user.id}\">{user.full_name}</a> muvaffaqiyatli tasdiqlandi!\n"
            f"Guruhga xush kelibsiz! Qoidalar bilan tanishish uchun: /rules"
        ),
        parse_mode="HTML"
    )
    auto_delete(welcome_msg, delay=15)
    
    # 5. Log kanalga yuborish
    await log_captcha(bot, user, passed=True, reason="Tugma orqali tasdiqlandi.")
    await callback.answer("✅ Siz muvaffaqiyatli tasdiqlandingiz!", show_alert=False)
