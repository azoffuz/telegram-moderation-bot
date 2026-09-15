import re
import logging
from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.enums import MessageEntityType
from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.logger import send_log
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="badwords")

# Arab va Fors harflari diapazoni
ARABIC_PERSIAN_REGEX = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")

def has_custom_emoji(message: Message) -> bool:
    """Xabarda Telegram Premium (tashqi/maxsus) emojilar borligini 100% aniqlaydi."""
    entities = (message.entities or []) + (message.caption_entities or [])
    for entity in entities:
        if entity.type == MessageEntityType.CUSTOM_EMOJI:
            return True
    if message.sticker and getattr(message.sticker, "is_custom_emoji", False):
        return True
    return False

@router.message(IsGroupFilter())
async def bad_words_and_arabic_handler(message: Message, bot: Bot):
    """
    Taqiqlangan so'zlar (kazino, so'kinish va h.k.) hamda
    arab/fors yozuvidagi spam xabarlarni aniqlab o'chiradi.
    """
    if not message.from_user:
        return

    # Adminlarga tegmaymiz
    if await IsAdminFilter()(message, bot):
        return

    text = message.text or message.caption or ""
    if not text:
        return

    chat_id = message.chat.id
    user = message.from_user

    # 1. Taqiqlangan so'zlarni tekshirish
    if await db.get_chat_setting_bool(chat_id, "anti_badwords", default=True):
        detected_word = await db.check_bad_words_in_text(text)
        if detected_word:
            try:
                await message.delete()
            except Exception:
                pass

            await db.increment_stat("badwords_deleted")

            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, "
                f"guruhda taqiqlangan so'z yoki reklamalarni ishlatish mumkin emas!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)

            # Log kanalga yuborish
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

    # 2. Arab va Fors yozuvidagi spamlarni tekshirish
    if await db.get_chat_setting_bool(chat_id, "anti_arabic", default=True):
        if ARABIC_PERSIAN_REGEX.search(text):
            try:
                await message.delete()
            except Exception:
                pass

            await db.increment_stat("arabic_deleted")

            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, "
                f"guruhda arab yoki fors alifbosida xabar yozish taqiqlangan!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)

            # Log kanalga yuborish
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

    # 3. Telegram Premium (tashqi/maxsus) emojilarni tekshirish
    if await db.get_chat_setting_bool(chat_id, "anti_custom_emoji", default=True):
        if has_custom_emoji(message):
            try:
                await message.delete()
            except Exception:
                pass

            await db.increment_stat("custom_emoji_deleted")

            warn_msg = await message.answer(
                f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, "
                f"guruhda Premium (tashqi/maxsus) emojilarni yuborish taqiqlangan!",
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
