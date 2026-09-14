import re
import logging
from typing import Optional, Tuple
from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.enums import MessageEntityType
from bot.config import config
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.database import db
from bot.services.logger import log_anti_link
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="antilink")

# URL va domenlarni topish uchun kuchli Regex
URL_REGEX = re.compile(
    r"(https?://[^\s]+|"
    r"t\.me/[^\s]+|"
    r"telegram\.me/[^\s]+|"
    r"telegram\.dog/[^\s]+|"
    r"bit\.ly/[^\s]+|"
    r"www\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}[^\s]*|"
    r"\b[a-zA-Z0-9.-]+\.(com|uz|ru|net|org|io|me|info|biz|co|app|xyz|site|top|link|online|live|pro|club|space|shop|vip|fun|tech|dev)(?:/[^\s]*)?\b)",
    re.IGNORECASE
)

# @username ko'rinishidagi kanallar yoki profillar havolasi
MENTION_REGEX = re.compile(r"@[a-zA-Z0-9_]{4,}")

def detect_link(message: Message) -> Optional[str]:
    """
    Xabar matni yoki media sarlavhasida (caption) har qanday havolani aniqlaydi.
    100% ushlash: Entities + Regex + Mention.
    """
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []

    # 1. Telegram Entities tekshiruvi (yashirin va ochiq havolalar)
    for entity in entities:
        if entity.type == MessageEntityType.URL:
            # Matndan entity kesib olinadi
            url_part = text[entity.offset : entity.offset + entity.length]
            return url_part
        elif entity.type == MessageEntityType.TEXT_LINK:
            # Matn orqasiga yashirilgan havola (masalan: [Bosing](https://...))
            return entity.url or "Yashirin havola (text_link)"
        elif entity.type == MessageEntityType.MENTION:
            mention_part = text[entity.offset : entity.offset + entity.length]
            return mention_part

    # 2. Matn bo'yicha Regex tekshiruvi
    match = URL_REGEX.search(text)
    if match:
        return match.group(0)

    # 3. Mention (@username) bo'yicha Regex tekshiruvi
    mention_match = MENTION_REGEX.search(text)
    if mention_match:
        return mention_match.group(0)

    return None

@router.message(IsGroupFilter())
async def anti_link_handler(message: Message, bot: Bot):
    """
    Oddiy foydalanuvchilar yuborgan barcha havolalarni 100% o'chiradi va log qiladi.
    Adminlar uchun ruxsat berilgan.
    """
    if not message.from_user:
        return

    # Adminlarni tekshiramiz (adminlarga ruxsat beriladi)
    is_admin = await IsAdminFilter()(message, bot)
    if is_admin:
        return

    # Admin paneldan Anti-Link o'chirilgan bo'lsa
    if not await db.get_chat_setting_bool(message.chat.id, "anti_link", default=True):
        return

    detected_link = detect_link(message)
    if not detected_link:
        return

    # Havola topildi: Darhol o'chiramiz!
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Havola xabarini o'chirishda xatolik: {e}")

    # Guruhga qisqa ogohlantirish (chat toza bo'lishi uchun 10 soniyada o'chiriladi)
    user = message.from_user
    full_text = message.text or message.caption or ""
    
    warn_msg = await message.answer(
        f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda havola (link) yoki reklama yuborish taqiqlangan!",
        parse_mode="HTML"
    )
    auto_delete(warn_msg, delay=10)

    # Maxfiy log kanalga batafsil hisobot
    await log_anti_link(
        bot=bot,
        user=user,
        chat=message.chat,
        link=detected_link,
        message_text=full_text
    )
