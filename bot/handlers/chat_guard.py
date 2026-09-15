import re
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List

from aiogram import Router, Bot
from aiogram.types import Message, ChatPermissions
from aiogram.enums import MessageEntityType

from bot.config import config
from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.logger import send_log, log_anti_link, log_anti_forward, log_moderation
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="chat_guard")

# ==================== REGEX VA SOZLAMALAR ====================
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
MENTION_REGEX = re.compile(r"@[a-zA-Z0-9_]{4,}")
ARABIC_PERSIAN_REGEX = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")

# Anti-flood xotirasi
user_message_times: Dict[int, List[float]] = {}
FLOOD_RATE_LIMIT = 5
FLOOD_TIME_WINDOW = 4.0
MUTE_DURATION_MINUTES = 10

# ==================== YORDAMCHI FUNKSIYALAR ====================
def detect_link(message: Message) -> Optional[str]:
    """Xabardagi barcha turdagi havolalarni (ochiq, yashirin, mention) aniqlaydi."""
    text = message.text or message.caption or ""
    entities = (message.entities or []) + (message.caption_entities or [])

    for entity in entities:
        if entity.type == MessageEntityType.URL:
            return text[entity.offset : entity.offset + entity.length]
        elif entity.type == MessageEntityType.TEXT_LINK:
            return entity.url or "Yashirin havola (text_link)"
        elif entity.type == MessageEntityType.MENTION:
            return text[entity.offset : entity.offset + entity.length]

    match = URL_REGEX.search(text)
    if match:
        return match.group(0)

    mention_match = MENTION_REGEX.search(text)
    if mention_match:
        return mention_match.group(0)

    return None

def is_forwarded(message: Message) -> Tuple[bool, str]:
    """Xabar har qanday manbadan forward qilinganini aniqlaydi."""
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        origin_type = getattr(origin, "type", "noma'lum")
        if origin_type == "channel":
            chat_title = getattr(origin.chat, "title", "Kanal")
            return True, f"Kanal: {chat_title}"
        elif origin_type == "chat":
            chat_title = getattr(origin.sender_chat, "title", "Guruh")
            return True, f"Guruh: {chat_title}"
        elif origin_type == "user":
            user_name = getattr(origin.sender_user, "full_name", "Foydalanuvchi")
            return True, f"Foydalanuvchi: {user_name}"
        elif origin_type == "hidden_user":
            sender_name = getattr(origin, "sender_user_name", "Maxfiy foydalanuvchi")
            return True, f"Maxfiy foydalanuvchi: {sender_name}"
        return True, f"Uzatilgan ({origin_type})"

    if message.forward_date or message.forward_from or message.forward_from_chat or message.forward_sender_name:
        if message.forward_from_chat:
            return True, f"Chat/Kanal: {message.forward_from_chat.title}"
        elif message.forward_from:
            return True, f"Foydalanuvchi: {message.forward_from.full_name}"
        elif message.forward_sender_name:
            return True, f"Shaxs: {message.forward_sender_name}"
        return True, "Uzatilgan xabar"

    return False, ""

def has_media(message: Message) -> bool:
    """Xabarda media borligini aniqlaydi."""
    return bool(
        message.photo or
        message.video or
        message.voice or
        message.audio or
        message.sticker or
        message.video_note or
        message.document or
        message.animation
    )

def has_custom_emoji(message: Message) -> bool:
    """Telegram Premium (tashqi/maxsus) emoji borligini aniqlaydi."""
    entities = (message.entities or []) + (message.caption_entities or [])
    for entity in entities:
        if entity.type == MessageEntityType.CUSTOM_EMOJI:
            return True
    if message.sticker and getattr(message.sticker, "is_custom_emoji", False):
        return True
    return False

# ==================== ASOSIY YAGONA NAZORAT HANDLERI ====================
@router.message(IsGroupFilter())
async def unified_chat_guard_handler(message: Message, bot: Bot):
    """
    Guruhdagi har bir xabarni ketma-ketlikda barcha himoya qatlamlaridan o'tkazuvchi
    yagona va tezkor moderatsiya quvuri (Pipeline).
    """
    if not message.from_user:
        return

    # Foydalanuvchi ma'lumotlarini bazada yangilab boramiz (@username orqali jazo qo'llash uchun)
    await db.save_known_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    # Adminlarga barcha himoyalardan o'tishga ruxsat beriladi
    if await IsAdminFilter()(message, bot):
        return

    chat_id = message.chat.id
    user = message.from_user
    text = message.text or message.caption or ""

    # -------------------------------------------------------------
    # 1. ANTI-FLOOD / SPAM NAZORATI
    # -------------------------------------------------------------
    if await db.get_chat_setting_bool(chat_id, "anti_flood", default=True):
        now = time.time()
        user_id = user.id
        if user_id not in user_message_times:
            user_message_times[user_id] = []
        user_message_times[user_id] = [t for t in user_message_times[user_id] if now - t < FLOOD_TIME_WINDOW]
        user_message_times[user_id].append(now)

        if len(user_message_times[user_id]) > FLOOD_RATE_LIMIT:
            user_message_times[user_id].clear()
            try:
                await message.delete()
            except Exception:
                pass

            until_date = datetime.now() + timedelta(minutes=MUTE_DURATION_MINUTES)
            try:
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date
                )
                await db.increment_stat("mutes_count")
                warn_msg = await message.answer(
                    f"🔇 <a href=\"tg://user?id={user.id}\">{user.full_name}</a> spam/flood sababli "
                    f"<b>{MUTE_DURATION_MINUTES} daqiqaga</b> mute qilindi!",
                    parse_mode="HTML"
                )
                auto_delete(warn_msg, delay=10)
                await log_moderation(
                    bot=bot,
                    admin=None,
                    target_user=user,
                    action="Mute (Anti-Flood)",
                    reason=f"{FLOOD_TIME_WINDOW}s ichida {FLOOD_RATE_LIMIT}+ xabar",
                    details=f"{MUTE_DURATION_MINUTES} daqiqa"
                )
            except Exception as e:
                logger.error(f"Anti-flood mute xatosi: {e}")
            return

    # -------------------------------------------------------------
    # 2. YANGI A'ZOLAR MEDIA SINOV MUDDATI
    # -------------------------------------------------------------
    if await db.get_chat_setting_bool(chat_id, "newcomer_media_lock", default=True):
        if has_media(message):
            if await db.is_in_probation(user.id, chat_id, probation_minutes=60):
                try:
                    await message.delete()
                except Exception:
                    pass
                await db.increment_stat("media_blocked")
                warn_msg = await message.answer(
                    f"👶 <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, "
                    f"yangi a'zolarga dastlabki <b>60 daqiqa</b> davomida rasm, video, stiker va ovozli xabar "
                    f"yuborish cheklangan. Guruhda faqat oddiy matn yoza olasiz!",
                    parse_mode="HTML"
                )
                auto_delete(warn_msg, delay=10)
                await send_log(
                    bot,
                    f"👶 <b>YANGI A'ZODAN MEDIA BLOKLANDI</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
                    f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                    f"💬 <b>Guruh:</b> {message.chat.title}\n"
                    f"ℹ️ <b>Holat:</b> Sinov davrida media yuborishga urindi"
                )
                return

    # -------------------------------------------------------------
    # 3. 100% ANTI-FORWARD
    # -------------------------------------------------------------
    if await db.get_chat_setting_bool(chat_id, "anti_forward", default=True):
        forwarded, source_info = is_forwarded(message)
        if forwarded:
            try:
                await message.delete()
            except Exception:
                pass
            await db.increment_stat("forwards_deleted")
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda boshqa joydan xabar uzatish (forward) taqiqlangan!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)
            await log_anti_forward(bot=bot, user=user, chat=message.chat, source_info=source_info)
            return

    # -------------------------------------------------------------
    # 4. 100% ANTI-LINK
    # -------------------------------------------------------------
    if await db.get_chat_setting_bool(chat_id, "anti_link", default=True):
        detected_link = detect_link(message)
        if detected_link:
            try:
                await message.delete()
            except Exception:
                pass
            await db.increment_stat("links_deleted")
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda havola (link) yoki reklama yuborish taqiqlangan!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)
            await log_anti_link(bot=bot, user=user, chat=message.chat, link=detected_link, message_text=text)
            return

    # -------------------------------------------------------------
    # 5. TAQIQLANGAN SO'ZLAR (BAD WORDS)
    # -------------------------------------------------------------
    if await db.get_chat_setting_bool(chat_id, "anti_badwords", default=True):
        detected_word = await db.check_bad_words_in_text(text)
        if detected_word:
            try:
                await message.delete()
            except Exception:
                pass
            await db.increment_stat("badwords_deleted")
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda taqiqlangan so'z yoki reklamalarni ishlatish mumkin emas!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)

            preview = (text[:120] + "...") if len(text) > 120 else text
            clean_preview = preview.replace("<", "&lt;").replace(">", "&gt;")
            await send_log(
                bot,
                f"🚫 <b>TAQIQLANGAN SO'Z ANIQLANDI</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"💬 <b>Guruh:</b> {message.chat.title}\n"
                f"🔍 <b>Ushlangan so'z:</b> <code>{detected_word}</code>\n"
                f"📝 <b>Matn:</b> <i>{clean_preview}</i>"
            )
            return

    # -------------------------------------------------------------
    # 6. ARAB VA FORS SPAM YOZUVLARI
    # -------------------------------------------------------------
    if await db.get_chat_setting_bool(chat_id, "anti_arabic", default=True):
        if text and ARABIC_PERSIAN_REGEX.search(text):
            try:
                await message.delete()
            except Exception:
                pass
            await db.increment_stat("arabic_deleted")
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda arab yoki fors alifbosida xabar yozish taqiqlangan!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)

            preview = (text[:120] + "...") if len(text) > 120 else text
            clean_preview = preview.replace("<", "&lt;").replace(">", "&gt;")
            await send_log(
                bot,
                f"🛑 <b>ARAB/FORS SPAM USHLANDI</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"💬 <b>Guruh:</b> {message.chat.title}\n"
                f"📝 <b>Matn:</b> <i>{clean_preview}</i>"
            )
            return

    # -------------------------------------------------------------
    # 7. TELEGRAM PREMIUM (TASHQI/MAXSUS) EMOJILAR
    # -------------------------------------------------------------
    if await db.get_chat_setting_bool(chat_id, "anti_custom_emoji", default=True):
        if has_custom_emoji(message):
            try:
                await message.delete()
            except Exception:
                pass
            await db.increment_stat("custom_emoji_deleted")
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda Premium (tashqi/maxsus) emojilarni yuborish taqiqlangan!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)
            await send_log(
                bot,
                f"⭐️ <b>PREMIUM EMOJI O'CHIRILDI</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"💬 <b>Guruh:</b> {message.chat.title}\n"
                f"ℹ️ <b>Sabab:</b> Xabarda Telegram Premium (custom emoji) ishlatilgan"
            )
            return
