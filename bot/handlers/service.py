import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ContentType
from bot.filters.chat_type import IsGroupFilter
from bot.database import db

logger = logging.getLogger(__name__)
router = Router(name="service_cleaner")

@router.message(
    IsGroupFilter(),
    F.content_type.in_([
        ContentType.NEW_CHAT_MEMBERS,
        ContentType.LEFT_CHAT_MEMBER,
        ContentType.PINNED_MESSAGE,
        ContentType.NEW_CHAT_TITLE,
        ContentType.NEW_CHAT_PHOTO,
        ContentType.DELETE_CHAT_PHOTO,
        ContentType.VIDEO_CHAT_SCHEDULED,
        ContentType.VIDEO_CHAT_STARTED,
        ContentType.VIDEO_CHAT_ENDED
    ])
)
async def delete_service_messages(message: Message):
    """
    Guruhdagi barcha xizmat xabarlarini (kirdi, chiqdi, qadaldi va h.k.) darhol o'chiradi.
    Chat har doim toza va tartibli turadi.
    """
    # Admin paneldan xizmat xabarlarini o'chirish o'chirilgan bo'lsa
    if not await db.get_chat_setting_bool(message.chat.id, "service_cleaner", default=True):
        return

    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Xizmat xabarini o'chirishda xatolik: {e}")
