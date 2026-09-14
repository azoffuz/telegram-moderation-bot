import logging
from aiogram import Router, Bot, F
from aiogram.types import Message
from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.logger import send_log
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="newcomer_guard")

def has_media(message: Message) -> bool:
    """Xabarda media (rasm, video, stiker, ovozli xabar va h.k.) borligini aniqlaydi."""
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

@router.message(IsGroupFilter())
async def newcomer_media_guard_handler(message: Message, bot: Bot):
    """
    Yangi a'zolarning dastlabki 60 daqiqada rasm/video/stiker/audio
    tashlashini bloklaydi. Faqat oddiy matn yozishga ruxsat beradi.
    """
    if not message.from_user:
        return

    # Adminlarga tegmaymiz
    if await IsAdminFilter()(message, bot):
        return

    # Media cheklovi o'chirilgan bo'lsa
    if not await db.get_chat_setting_bool(message.chat.id, "newcomer_media_lock", default=True):
        return

    # Agar xabarda media bo'lmasa (oddiy matn bo'lsa), o'tkazib yuboramiz
    if not has_media(message):
        return

    user = message.from_user
    chat_id = message.chat.id

    # Foydalanuvchi sinov davridaligini tekshiramiz (masalan, 60 daqiqa)
    in_probation = await db.is_in_probation(user.id, chat_id, probation_minutes=60)
    if in_probation:
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
        auto_delete(warn_msg, delay=12)

        # Log kanalga yuborish
        await send_log(
            bot,
            f"👶 <b>YANGI A'ZODAN MEDIA BLOKLANDI</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"💬 <b>Guruh:</b> {message.chat.title}\n"
            f"ℹ️ <b>Holat:</b> Sinov davrida media yuborishga urindi"
        )
