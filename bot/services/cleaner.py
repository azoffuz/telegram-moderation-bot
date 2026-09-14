import asyncio
import logging
from typing import List, Optional, Union
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from bot.config import config

logger = logging.getLogger(__name__)

async def _delayed_delete_task(msg: Message, delay: int):
    """Kechiktirilgan holda bitta xabarni o'chirish vazifasi."""
    try:
        await asyncio.sleep(delay)
        await msg.delete()
    except TelegramBadRequest as e:
        # Xabar allaqachon o'chirilgan yoki huquq yetarli emas
        logger.debug(f"Xabarni o'chirishda xatolik: {e}")
    except Exception as e:
        logger.debug(f"Kutilmagan xatolik: {e}")

def auto_delete(message: Optional[Message], delay: Optional[int] = None):
    """
    Xabarni ko'rsatilgan soniyadan so'ng (sukut bo'yicha AUTO_DELETE_DELAY)
    avtomatik o'chirish uchun orqa fonga vazifa (task) yuklaydi.
    """
    if not message:
        return
    wait_time = delay if delay is not None else config.AUTO_DELETE_DELAY
    asyncio.create_task(_delayed_delete_task(message, wait_time))

def auto_delete_many(messages: List[Optional[Message]], delay: Optional[int] = None):
    """Bir nechta xabarlarni belgilangan vaqtdan so'ng avtomatik o'chiradi."""
    for msg in messages:
        if msg:
            auto_delete(msg, delay)
