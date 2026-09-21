import re
import time
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List

from aiogram import Router, Bot
from aiogram.types import Message, ChatPermissions, User
from aiogram.enums import MessageEntityType

from bot.config import config
from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter, get_linked_chat_id
from bot.services.logger import send_log, log_anti_link, log_anti_forward, log_moderation, log_anti_location
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

# Mentions keshini saqlash: (chat_id, username_lower) -> (timestamp, (is_allowed, reason))
_mention_cache: Dict[Tuple[int, str], Tuple[float, Tuple[bool, str]]] = {}
_bot_username: Optional[str] = None

async def get_bot_username(bot: Bot) -> str:
    """Botning o'z username ini keshlaydi."""
    global _bot_username
    if _bot_username is None:
        try:
            me = await bot.get_me()
            _bot_username = (me.username or "").lower()
        except Exception:
            _bot_username = ""
    return _bot_username

# ==================== YORDAMCHI FUNKSIYALAR ====================
def detect_explicit_link(message: Message) -> Optional[str]:
    """Xabardagi barcha ochiq va yashirin URL havolalarini aniqlaydi (mention lardan tashqari)."""
    text = message.text or message.caption or ""
    entities = (message.entities or []) + (message.caption_entities or [])

    for entity in entities:
        if entity.type == MessageEntityType.URL:
            return text[entity.offset : entity.offset + entity.length]
        elif entity.type == MessageEntityType.TEXT_LINK:
            return entity.url or "Yashirin havola (text_link)"

    match = URL_REGEX.search(text)
    if match:
        return match.group(0)

    return None

async def validate_mention(bot: Bot, chat_id: int, mention_str: str) -> Tuple[bool, str]:
    """
    @username mention ni tekshiradi:
    - Botning o'zi yoki oq ro'yxatdagi kanal bo'lsa -> Ruxsat beriladi (True)
    - Guruhda a'zo bo'lgan foydalanuvchi bo'lsa -> Ruxsat beriladi (True)
    - Kanal, tashqi guruh yoki guruhda yo'q shaxs bo'lsa -> Taqiqlanadi (False)
    """
    now = time.time()
    uname = mention_str.lstrip("@").strip().lower()
    if not uname:
        return True, "empty"

    # 1. Botning o'zini ping qilishgan bo'lsa
    bot_uname = await get_bot_username(bot)
    if bot_uname and uname == bot_uname:
        return True, "bot"

    # 2. Oq ro'yxatdagi rasmiy kanal/manbalar
    if uname in ["reker_uz", "rekeruz"]:
        return True, "whitelist"

    # 3. Keshni tekshirish (5 daqiqalik kesh)
    cache_key = (chat_id, uname)
    if cache_key in _mention_cache:
        cached_time, cached_result = _mention_cache[cache_key]
        if now - cached_time < 300:
            return cached_result

    # Kesh hajmini nazorat qilish
    if len(_mention_cache) > 1500:
        expired = [k for k, v in _mention_cache.items() if now - v[0] >= 300]
        for k in expired:
            _mention_cache.pop(k, None)

    # 4. Avvalo bazadagi 'known_users' jadvalidan qidiramiz
    user_data = await db.get_user_by_username(uname)
    if user_data:
        target_uid = user_data["user_id"]
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=target_uid)
            if member.status in ["creator", "administrator", "member", "restricted"]:
                res = (True, "member")
                _mention_cache[cache_key] = (now, res)
                return res
            else:
                res = (False, f"Guruhdan chiqqan a'zo (@{uname})")
                _mention_cache[cache_key] = (now, res)
                return res
        except Exception:
            res = (False, f"Guruhda mavjud emas (@{uname})")
            _mention_cache[cache_key] = (now, res)
            return res

    # 5. Agar bazada bo'lmasa, Telegram Bot API orqali obyekt turini aniqlaymiz
    try:
        target_chat = await bot.get_chat(f"@{uname}")
    except Exception:
        # Telegram chatni topa olmadi (noma'lum yoki begona foydalanuvchi)
        res = (False, f"Guruhda yo'q / noma'lum (@{uname})")
        _mention_cache[cache_key] = (now, res)
        return res

    # Kanal yoki guruh bo'lsa darhol taqiqlaymiz (kanallarniku albatta!)
    if target_chat.type in ["channel", "supergroup", "group"]:
        res = (False, f"Kanal yoki guruh havolasi (@{uname})")
        _mention_cache[cache_key] = (now, res)
        return res

    # Agar private chat (foydalanuvchi) bo'lsa, uni bazaga saqlaymiz va a'zoligini tekshiramiz
    if target_chat.type == "private":
        await db.save_known_user(target_chat.id, target_chat.username, target_chat.full_name)
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=target_chat.id)
            if member.status in ["creator", "administrator", "member", "restricted"]:
                res = (True, "member")
                _mention_cache[cache_key] = (now, res)
                return res
            else:
                res = (False, f"Guruhda yo'q foydalanuvchi (@{uname})")
                _mention_cache[cache_key] = (now, res)
                return res
        except Exception:
            res = (False, f"Guruh a'zosi emas (@{uname})")
            _mention_cache[cache_key] = (now, res)
            return res

    res = (False, f"Noma'lum havola (@{uname})")
    _mention_cache[cache_key] = (now, res)
    return res

async def detect_link_or_illegal_mention(message: Message, bot: Bot) -> Optional[str]:
    """
    Xabardagi havolalar va ruxsat etilmagan mention larni tekshiradi:
    - Ochiq yoki yashirin URL bo'lsa -> return link
    - Guruhda mavjud bo'lmagan begona user yoki kanal mention bo'lsa -> return mention
    - Agar faqat guruhdagi mavjud a'zolar ping qilingan bo'lsa -> return None (ruxsat beriladi)
    """
    # 1. Aniq URL / Domen havolalarini tekshirish
    explicit_link = detect_explicit_link(message)
    if explicit_link:
        return explicit_link

    # 2. Mention larni yig'ish
    text = message.text or message.caption or ""
    entities = (message.entities or []) + (message.caption_entities or [])
    mentions_to_check: List[str] = []

    for entity in entities:
        if entity.type == MessageEntityType.MENTION:
            m_text = text[entity.offset : entity.offset + entity.length]
            mentions_to_check.append(m_text)
        elif entity.type == MessageEntityType.TEXT_MENTION and entity.user:
            # Username siz nom orqali ping qilingan a'zo
            try:
                member = await bot.get_chat_member(chat_id=message.chat.id, user_id=entity.user.id)
                if member.status not in ["creator", "administrator", "member", "restricted"]:
                    return f"{entity.user.full_name} (Guruhda yo'q a'zo)"
            except Exception:
                return f"{entity.user.full_name} (Guruh a'zosi emas)"

    # Regex orqali ham matndagi @username larni tekshirish
    for m in MENTION_REGEX.finditer(text):
        mentions_to_check.append(m.group(0))

    if not mentions_to_check:
        return None

    # Takrorlanishlarni olib tashlaymiz
    unique_mentions = list(dict.fromkeys(mentions_to_check))

    for m_str in unique_mentions:
        is_allowed, reason = await validate_mention(bot, message.chat.id, m_str)
        if not is_allowed:
            return f"{m_str} ({reason})"

    return None

def is_forwarded(message: Message) -> Tuple[bool, str]:
    """Xabar har qanday manbadan forward qilinganini aniqlaydi."""
    # Telegram rasmiy avtomatik uzatmasi (kanaldan guruhga) forward sanalmaydi
    if getattr(message, "is_automatic_forward", False):
        return False, ""
    if message.from_user and message.from_user.id == 777000:
        return False, ""
    if message.sender_chat:
        sender_username = (message.sender_chat.username or "").lower()
        if sender_username in ["reker_uz", "rekeruz"]:
            return False, ""

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

def has_location(message: Message) -> Tuple[bool, str]:
    """Telegram lokatsiyasi yoki joy (venue) yuborilganini aniqlaydi."""
    if message.location is not None:
        if getattr(message.location, "live_period", None):
            return True, "Jonli lokatsiya (Live Location)"
        return True, "Oddiy lokatsiya (Location)"
    if message.venue is not None:
        venue_title = getattr(message.venue, "title", "Joy/Manzil")
        return True, f"Telegram joy/manzil (Venue: {venue_title})"
    return False, ""

# ==================== ASOSIY YAGONA NAZORAT HANDLERI ====================
@router.message(IsGroupFilter())
@router.edited_message(IsGroupFilter())
async def unified_chat_guard_handler(message: Message, bot: Bot):
    """
    Guruhdagi har bir xabarni ketma-ketlikda barcha himoya qatlamlaridan o'tkazuvchi
    yagona va tezkor moderatsiya quvuri (Pipeline).
    """
    # 0. Telegram tomonidan kanaldan avtomatik yuborilgan xabarlar (Linked Channel / Discussion)
    # va Telegram Service xabarlarini darhol o'tkazib yuborish (0ms)
    if getattr(message, "is_automatic_forward", False):
        return

    if message.from_user and message.from_user.id == 777000:
        return

    if message.sender_chat:
        # Anonim admin (guruh nomidan yozish)
        if message.chat and message.sender_chat.id == message.chat.id:
            return

        # Foydalanuvchining rasmiy kanali (@Reker_UZ)
        sender_username = (message.sender_chat.username or "").lower()
        if sender_username in ["reker_uz", "rekeruz"]:
            return

        # Guruhga ulangan rasmiy kanal (linked_chat_id)
        if message.chat:
            linked_id = await get_linked_chat_id(bot, message.chat.id)
            if linked_id and message.sender_chat.id == linked_id:
                return

    if not message.from_user:
        return

    # O'chirilgan akkaunt (Deleted Account) nazorati
    first_name = (message.from_user.first_name or "").strip().lower()
    if first_name == "deleted account" or "deleted account" in first_name or "удален" in first_name:
        try:
            await message.delete()
            await bot.ban_chat_member(chat_id=message.chat.id, user_id=message.from_user.id)
            await bot.unban_chat_member(chat_id=message.chat.id, user_id=message.from_user.id)
            await db.remove_chat_member(message.chat.id, message.from_user.id)
        except Exception:
            pass
        return

    # Foydalanuvchi ma'lumotlarini bazada yangilab boramiz (@username orqali jazo qo'llash va a'zolar ro'yxati uchun)
    await db.save_known_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await db.track_chat_member(message.chat.id, message.from_user.id)

    # Adminlarga barcha himoyalardan o'tishga ruxsat beriladi
    if await IsAdminFilter()(message, bot):
        return

    chat_id = message.chat.id
    user = message.from_user
    text = message.text or message.caption or ""

    # -------------------------------------------------------------
    # NOQONUNIY / BEGONA BARCHA SLASH BUYRUQLARNI DARHOL O'CHIRISH
    # -------------------------------------------------------------
    # Oddiy a'zolar guruhda yuborgan har qanday slash bilan boshlanuvchi buyruqlarni (/...) o'chiramiz
    is_slash_cmd = text.strip().startswith("/") or any(
        e.type == MessageEntityType.BOT_COMMAND for e in (message.entities or [])
    )
    if is_slash_cmd:
        try:
            await message.delete()
        except Exception:
            pass
        return

    # Guruh sozlamalarini xotiradan (RAM - 0ms) olamiz
    settings = await db.get_all_chat_settings(chat_id)

    # Dinamik Slowmode tekshiruvi (Orqa fonda, 0ms kechikish)
    if settings.get("auto_slowmode", False):
        from bot.services.slowmode import record_message_and_evaluate_slowmode
        asyncio.create_task(record_message_and_evaluate_slowmode(bot, chat_id))

    # -------------------------------------------------------------
    # 1. ANTI-FLOOD / SPAM NAZORATI
    # -------------------------------------------------------------
    if settings.get("anti_flood", True):
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

            flood_mute_minutes = int(settings.get("flood_mute_minutes", 10))
            until_date = datetime.now() + timedelta(minutes=flood_mute_minutes)
            try:
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date
                )
                asyncio.create_task(db.increment_stat("mutes_count"))
                warn_msg = await message.answer(
                    f"🔇 <a href=\"tg://user?id={user.id}\">{user.full_name}</a> spam/flood sababli "
                    f"<b>{flood_mute_minutes} daqiqaga</b> mute qilindi!",
                    parse_mode="HTML"
                )
                auto_delete(warn_msg, delay=10)
                asyncio.create_task(log_moderation(
                    bot=bot,
                    admin=None,
                    target_user=user,
                    action="Mute (Anti-Flood)",
                    reason=f"{FLOOD_TIME_WINDOW}s ichida {FLOOD_RATE_LIMIT}+ xabar",
                    details=f"{flood_mute_minutes} daqiqa"
                ))
            except Exception as e:
                logger.error(f"Anti-flood mute xatosi: {e}")
            return

    # -------------------------------------------------------------
    # 2. YANGI A'ZOLAR MEDIA SINOV MUDDATI
    # -------------------------------------------------------------
    if settings.get("newcomer_media_lock", True):
        if has_media(message):
            prob_mins = int(settings.get("probation_minutes", 60))
            if await db.is_in_probation(user.id, chat_id, probation_minutes=prob_mins):
                try:
                    await message.delete()
                except Exception:
                    pass
                asyncio.create_task(db.increment_stat("media_blocked"))
                warn_msg = await message.answer(
                    f"👶 <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, "
                    f"yangi a'zolarga dastlabki <b>{prob_mins} daqiqa</b> davomida rasm, video, stiker va ovozli xabar "
                    f"yuborish cheklangan. Guruhda faqat oddiy matn yoza olasiz!",
                    parse_mode="HTML"
                )
                auto_delete(warn_msg, delay=10)
                asyncio.create_task(send_log(
                    bot,
                    f"👶 <b>YANGI A'ZODAN MEDIA BLOKLANDI</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
                    f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                    f"💬 <b>Guruh:</b> {message.chat.title}\n"
                    f"ℹ️ <b>Holat:</b> Sinov davrida media yuborishga urindi",
                    category="spam"
                ))
                return

    # -------------------------------------------------------------
    # 3. 100% ANTI-FORWARD
    # -------------------------------------------------------------
    if settings.get("anti_forward", True):
        forwarded, source_info = is_forwarded(message)
        if forwarded:
            try:
                await message.delete()
            except Exception:
                pass
            asyncio.create_task(db.increment_stat("forwards_deleted"))
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda boshqa joydan xabar uzatish (forward) taqiqlangan!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)
            asyncio.create_task(log_anti_forward(bot=bot, user=user, chat=message.chat, source_info=source_info))
            return

    # -------------------------------------------------------------
    # 4. 100% ANTI-LINK VA BEGONA MENTION / KANAL REKLAMA NAZORATI
    # -------------------------------------------------------------
    if settings.get("anti_link", True):
        detected_link = await detect_link_or_illegal_mention(message, bot)
        if detected_link:
            try:
                await message.delete()
            except Exception:
                pass
            asyncio.create_task(db.increment_stat("links_deleted"))
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda havola (link), kanal yoki begona a'zolarni reklama qilish taqiqlangan!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)
            asyncio.create_task(log_anti_link(bot=bot, user=user, chat=message.chat, link=detected_link, message_text=text))
            return

    # -------------------------------------------------------------
    # 5. TAQIQLANGAN SO'ZLAR (BAD WORDS)
    # -------------------------------------------------------------
    if settings.get("anti_badwords", True):
        detected_word = await db.check_bad_words_in_text(text)
        if detected_word:
            try:
                await message.delete()
            except Exception:
                pass
            asyncio.create_task(db.increment_stat("badwords_deleted"))
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda taqiqlangan so'z yoki reklamalarni ishlatish mumkin emas!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)

            preview = (text[:120] + "...") if len(text) > 120 else text
            clean_preview = preview.replace("<", "&lt;").replace(">", "&gt;")
            asyncio.create_task(send_log(
                bot,
                f"🚫 <b>TAQIQLANGAN SO'Z ANIQLANDI</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"💬 <b>Guruh:</b> {message.chat.title}\n"
                f"🔍 <b>Ushlangan so'z:</b> <code>{detected_word}</code>\n"
                f"📝 <b>Matn:</b> <i>{clean_preview}</i>",
                category="badwords"
            ))
            return

    # -------------------------------------------------------------
    # 6. ARAB VA FORS SPAM YOZUVLARI
    # -------------------------------------------------------------
    if settings.get("anti_arabic", True):
        if text and ARABIC_PERSIAN_REGEX.search(text):
            try:
                await message.delete()
            except Exception:
                pass
            asyncio.create_task(db.increment_stat("arabic_deleted"))
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda arab yoki fors alifbosida xabar yozish taqiqlangan!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)

            preview = (text[:120] + "...") if len(text) > 120 else text
            clean_preview = preview.replace("<", "&lt;").replace(">", "&gt;")
            asyncio.create_task(send_log(
                bot,
                f"🛑 <b>ARAB/FORS SPAM USHLANDI</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"💬 <b>Guruh:</b> {message.chat.title}\n"
                f"📝 <b>Matn:</b> <i>{clean_preview}</i>",
                category="spam"
            ))
            return

    # -------------------------------------------------------------
    # 7. TELEGRAM PREMIUM (TASHQI/MAXSUS) EMOJILAR
    # -------------------------------------------------------------
    if settings.get("anti_custom_emoji", True):
        if has_custom_emoji(message):
            try:
                await message.delete()
            except Exception:
                pass
            asyncio.create_task(db.increment_stat("custom_emoji_deleted"))
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda Premium (tashqi/maxsus) emojilarni yuborish taqiqlangan!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)
            asyncio.create_task(send_log(
                bot,
                f"⭐️ <b>PREMIUM EMOJI O'CHIRILDI</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"💬 <b>Guruh:</b> {message.chat.title}\n"
                f"ℹ️ <b>Sabab:</b> Xabarda Telegram Premium (custom emoji) ishlatilgan",
                category="spam"
            ))
            return

    # -------------------------------------------------------------
    # 8. TELEGRAM LOKATSIYA (JOYLASHUV) NAZORATI
    # -------------------------------------------------------------
    if settings.get("anti_location", False):
        is_loc, loc_type = has_location(message)
        if is_loc:
            try:
                await message.delete()
            except Exception:
                pass
            asyncio.create_task(db.increment_stat("locations_deleted"))
            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda lokatsiya (joylashuv) yuborish taqiqlangan!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)
            asyncio.create_task(log_anti_location(bot=bot, user=user, chat=message.chat, loc_type=loc_type))
            return

    # -------------------------------------------------------------
    # 9. KUNLIK FOALLIK VA «ACTIVE» UNVONI HISOBI
    # -------------------------------------------------------------
    # Faqat yangi (tahrirlanmagan) va toza xabarlar faollik tizimi yoqilgan bo'lsa hisoblanadi
    if settings.get("active_tag_enabled", True) and not getattr(message, "edit_date", None):
        gmt_offset = int(settings.get("gmt_offset", 5))
        from bot.services.active_tag import process_user_activity_and_check_reward
        asyncio.create_task(process_user_activity_and_check_reward(bot, chat_id, user, message, gmt_offset))

