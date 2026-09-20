import re
import time
import logging
import html
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, List, Dict, Any

from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from bot.database import db
from bot.filters.admin import invalidate_chat_admins_cache

logger = logging.getLogger(__name__)

# Foydalanuvchining oxirgi xabarlari keshi: {(chat_id, user_id): (timestamp, text_lower)}
_recent_user_messages: Dict[Tuple[int, int], Tuple[float, str]] = {}

def is_valid_activity_message(message: Message) -> bool:
    """
    Xabar faollik hisobiga o'tishi mumkinligini tekshiradi:
    1. Kamida 3 ta mustaqil so'zdan iborat bo'lishi (2 ta so'zdan oshishi sharti).
    2. Kamida 8 ta belgidan iborat bo'lishi.
    3. Buyruq bo'lmasligi ('/' bilan boshlanmasligi).
    4. Bir xil harflar takroridan iborat bo'lmasligi (aaaa, qweqwe).
    5. Bir xil xabarni qayta-qayta nusxalab yubormasligi (Anti-Duplicate).
    6. Minimal 4 soniyalik tanaffus (Anti-Fast-Spam Cooldown).
    """
    text = (message.text or message.caption or "").strip()
    if not text:
        return False

    # 1. Buyruqlar hisobga o'tmaydi
    if text.startswith("/"):
        return False

    # 2. 2 ta so'zdan oshishi sharti (kamida 3 ta to'liq so'z)
    # Lotin, krill harflari va raqamlardan iborat so'zlarni ajratamiz
    words = [w for w in re.findall(r"\b[\w\u0400-\u04FF']+\b", text) if len(w) >= 2]
    if len(words) <= 2:
        return False

    # 3. Minimal uzunlik
    if len(text) < 8:
        return False

    # 4. Be'mani harflar ketma-ketligi (Gibberish) yoki bir xil harflar takrori
    clean_lower = re.sub(r"\s+", "", text.lower())
    if len(set(clean_lower)) < 4:
        return False

    # Bir xil harf ketma-ket 4 martadan ko'p takrorlansa (masalan "soooooloooom")
    if re.search(r"(.)\1{4,}", clean_lower):
        return False

    # 5. Cooldown va Anti-Duplicate tekshiruvi
    now = time.time()
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return False

    cache_key = (chat_id, user_id)
    if cache_key in _recent_user_messages:
        last_time, last_text = _recent_user_messages[cache_key]
        # Agar oxirgi xabardan keyin 4 soniya o'tmagan bo'lsa (Fast-spam)
        if now - last_time < 4.0:
            return False
        # Agar aynan oldingi xabarni takrorlagan bo'lsa (Copy-paste spam)
        if text.lower() == last_text:
            return False

    _recent_user_messages[cache_key] = (now, text.lower())
    return True

# Faollik darajalari (Tiers)
# (xabarlar_soni, tag_nomi, badge_emoji)
ACTIVITY_TIERS = [
    (150, "Legend", "💎"),
    (70, "Master", "🥇"),
    (30, "Active+", "🥈"),
    (10, "Active", "🥉"),
]

MONTHLY_WINNER_TITLES = {
    1: ("Top Chatter", "👑"),
    2: ("Legend", "💎"),
    3: ("Master", "🥇"),
}

def get_chat_today_date_str(gmt_offset: int = 5) -> str:
    """Guruhning GMT mintaqasi bo'yicha bugungi sanani YYYY-MM-DD formatida qaytaradi."""
    tz = timezone(timedelta(hours=gmt_offset))
    return datetime.now(tz).strftime("%Y-%m-%d")

def get_chat_current_month_str(gmt_offset: int = 5) -> str:
    """Guruhning GMT mintaqasi bo'yicha joriy oyni YYYY-MM formatida qaytaradi."""
    tz = timezone(timedelta(hours=gmt_offset))
    return datetime.now(tz).strftime("%Y-%m")

def get_tier_info(message_count: int) -> Tuple[Optional[str], Optional[str]]:
    """Xabarlar soni bo'yicha erishilgan unvon va emojini qaytaradi."""
    for threshold, title, emoji in ACTIVITY_TIERS:
        if message_count >= threshold:
            return title, emoji
    return None, None

def get_next_tier_info(message_count: int) -> Optional[Tuple[int, str, str, int]]:
    """
    Keyingi daraja ma'lumotlarini qaytaradi:
    (kerakli_jami, keyingi_unvon, keyingi_emoji, qolgan_xabarlar)
    """
    # Pastdan yuqoriga tekshiramiz
    for threshold, title, emoji in reversed(ACTIVITY_TIERS):
        if message_count < threshold:
            return threshold, title, emoji, (threshold - message_count)
    return None  # Eng yuqori darajada (Legend)

async def grant_active_tag(bot: Bot, chat_id: int, user_id: int, custom_title: str = "Active") -> Tuple[bool, str]:
    """
    Foydalanuvchiga Telegramda rasmiy teg (Member Tag) beradi.
    Telegramning 'Edit member tags' (can_manage_tags) huquqidan foydalanadi.
    Foydalanuvchini admin qilish shart emas, u oddiy a'zo bo'lib qoladi.
    """
    clean_tag = custom_title.strip()[:16] or "Active"

    # 1. Telegramning rasmiy set_chat_member_tag metodi ('Edit member tags')
    try:
        await bot.set_chat_member_tag(
            chat_id=chat_id,
            user_id=user_id,
            tag=clean_tag
        )
        return True, f"«{clean_tag}» tegi muvaffaqiyatli berildi!"
    except TelegramBadRequest as e:
        err_msg = str(e).lower()

        # Agar a'zo guruh admini bo'lsa (adminlar uchun custom_title ishlatiladi)
        if "user is an administrator" in err_msg or "chat_admin_required" in err_msg:
            try:
                await bot.set_chat_administrator_custom_title(
                    chat_id=chat_id,
                    user_id=user_id,
                    custom_title=clean_tag
                )
                invalidate_chat_admins_cache(chat_id)
                return True, f"Admin a'zo uchun «{clean_tag}» unvoni o'rnatildi!"
            except Exception as e2:
                return False, f"Admin unvonini o'rnatishda xatolik: {e2}"

        # Agar botda huquq yetishmasa
        if "not enough rights" in err_msg or "right_forbidden" in err_msg or "can't edit tags" in err_msg:
            return False, "Botda a'zolarga teg berish huquqi ('Edit member tags') yo'q. Iltimos bot sozlamalarida 'Edit member tags'ni yoqing!"

        return False, f"Telegram xatoligi: {e}"
    except Exception as e:
        logger.error(f"grant_active_tag xatoligi: {e}")
        return False, f"Kutilmagan xatolik yuz berdi: {e}"

async def revoke_active_tag(bot: Bot, chat_id: int, user_id: int) -> Tuple[bool, str]:
    """
    Foydalanuvchining 'Active' tegini olib tashlaydi.
    """
    try:
        # 1. A'zo tegini bo'shatish (tag=None yoki "")
        await bot.set_chat_member_tag(
            chat_id=chat_id,
            user_id=user_id,
            tag=""
        )
        return True, "Teg muvaffaqiyatli olib tashlandi."
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        # Agar admin unvoni bo'lsa
        if "user is an administrator" in err_msg or "chat_admin_required" in err_msg:
            try:
                await bot.set_chat_administrator_custom_title(
                    chat_id=chat_id,
                    user_id=user_id,
                    custom_title=""
                )
                invalidate_chat_admins_cache(chat_id)
                return True, "Admin unvoni olib tashlandi."
            except Exception as e2:
                return False, f"Admin unvonini olib tashlashda xatolik: {e2}"
        return False, f"Tegni olib tashlashda xatolik: {e}"
    except Exception as e:
        logger.error(f"revoke_active_tag xatosi: {e}")
        return False, f"Xatolik: {e}"

async def process_user_activity_and_check_reward(bot: Bot, chat_id: int, user, message: Message, gmt_offset: int = 5):
    """
    Xabar kelganda foydalanuvchining kunlik faolligini hisoblaydi va 
    10, 30, 70, 150 ta xabar marralariga yetganda yangi Tier darajasini beradi.
    """
    # Xabar mezonlarga mosligini tekshiramiz (kamida 3 ta so'z, cooldown, anti-duplicate)
    if not is_valid_activity_message(message):
        return

    date_str = get_chat_today_date_str(gmt_offset)
    count, granted = await db.record_user_activity(chat_id, user.id, date_str)

    # Guruh sozlamalarini olamiz
    settings = await db.get_all_chat_settings(chat_id)
    if not settings.get("active_tag_enabled", True):
        return

    # Marralarni tekshirish: 10, 30, 70, 150
    tier_thresholds = [10, 30, 70, 150]
    if count in tier_thresholds:
        tier_title, tier_emoji = get_tier_info(count)
        if tier_title:
            success, msg = await grant_active_tag(bot, chat_id, user.id, tier_title)
            if success:
                await db.mark_active_granted(chat_id, user.id, date_str)
                from bot.services.logger import send_log

                log_text = (
                    f"{tier_emoji} <b>FOYDALANUVCHI DARAJASI OSHDI (LEVEL UP)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>A'zo:</b> <a href=\"tg://user?id={user.id}\">{html.escape(user.full_name)}</a>\n"
                    f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                    f"🏆 <b>Yangi Daraja:</b> «{tier_title}»\n"
                    f"💬 <b>Bugungi xabarlari:</b> {count} ta"
                )
                asyncio.create_task(send_log(bot, log_text, category="members"))

async def reward_monthly_top_chatters(bot: Bot, chat_id: int, month_str: str) -> List[Dict[str, Any]]:
    """
    Oylik eng faol Top-3 a'zoni taqdirlaydi:
    #1 -> 'Top Chatter' 👑
    #2 -> 'Legend' 💎
    #3 -> 'Master' 🥇
    """
    leaders = await db.get_monthly_activity_leaderboard(chat_id, month_str, limit=3)
    results = []
    if not leaders:
        return results

    for idx, item in enumerate(leaders, start=1):
        title_info = MONTHLY_WINNER_TITLES.get(idx, ("Active", "🎖"))
        title, emoji = title_info
        u_id = item["user_id"]
        success, msg = await grant_active_tag(bot, chat_id, u_id, title)
        results.append({
            "rank": idx,
            "user_id": u_id,
            "full_name": item["full_name"],
            "messages": item["message_count"],
            "title": title,
            "emoji": emoji,
            "success": success
        })

    return results
