import logging
from aiogram import Router, Bot
from aiogram.types import Message
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.logger import log_anti_forward
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="antiforward")

def is_forwarded(message: Message) -> tuple[bool, str]:
    """
    Xabar har qanday manbadan uzatilgan (forward) ekanligini 100% aniqlaydi.
    Telegram 7.0+ forward_origin hamda eski API forward maydonlarini tekshiradi.
    """
    # 1. Telegram Bot API 7.0+ forward_origin tekshiruvi
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

    # 2. Legacy / Eski API tekshiruvi
    if message.forward_date or message.forward_from or message.forward_from_chat or message.forward_sender_name:
        if message.forward_from_chat:
            return True, f"Chat/Kanal: {message.forward_from_chat.title}"
        elif message.forward_from:
            return True, f"Foydalanuvchi: {message.forward_from.full_name}"
        elif message.forward_sender_name:
            return True, f"Shaxs: {message.forward_sender_name}"
        return True, "Uzatilgan xabar"

    return False, ""

@router.message(IsGroupFilter())
async def anti_forward_handler(message: Message, bot: Bot):
    """
    Oddiy foydalanuvchilar tomonidan uzatilgan barcha xabarlarni 100% o'chiradi va loglaydi.
    """
    if not message.from_user:
        return

    # Adminlarga ruxsat
    is_admin = await IsAdminFilter()(message, bot)
    if is_admin:
        return

    forwarded, source_info = is_forwarded(message)
    if not forwarded:
        return

    # Forward topildi: Darhol o'chiramiz!
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Forward xabarni o'chirishda xatolik: {e}")

    # Guruhga qisqa ogohlantirish (chat toza bo'lishi uchun 10 soniyada o'chiriladi)
    user = message.from_user
    warn_msg = await message.answer(
        f"⚠️ <a href=\"tg://user?id={user.id}\">{user.full_name}</a>, guruhda boshqa joydan xabar uzatish (forward) taqiqlangan!",
        parse_mode="HTML"
    )
    auto_delete(warn_msg, delay=10)

    # Maxfiy log kanalga yuborish
    await log_anti_forward(
        bot=bot,
        user=user,
        chat=message.chat,
        source_info=source_info
    )
