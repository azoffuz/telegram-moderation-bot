from typing import Union
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus, ChatType
from bot.config import config
from bot.database import db

class IsOwnerFilter(Filter):
    """
    Faqatgina .env da belgilangan Asosiy Bosh Admin (Owner) larni tekshiradi.
    Yangi admin qo'shish, o'chirish faqat Owner huquqida bo'ladi.
    """
    async def __call__(self, event: Union[Message, CallbackQuery, ChatMemberUpdated]) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False
        return db.is_owner(user.id)

class IsBotAdminFilter(Filter):
    """
    Owner yoki bot ichida qo'shilgan rasmiy Bot Adminlarini tekshiradi.
    Admin panelni ochish va sozlamalarni o'zgartirish uchun ishlatiladi.
    """
    async def __call__(self, event: Union[Message, CallbackQuery, ChatMemberUpdated]) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False
        return await db.is_bot_admin(user.id)

class IsAdminFilter(Filter):
    """
    Umumiy moderatsiya uchun adminlik tekshiruvi:
    1. Owner
    2. Bot Admini (baza)
    3. Telegram guruhining administratori
    """
    async def __call__(self, event: Union[Message, CallbackQuery, ChatMemberUpdated], bot) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False

        # 1. Owner yoki Bot Admini bo'lsa
        if await db.is_bot_admin(user.id):
            return True

        # 2. Guruh admini ekanligini tekshirish
        chat = getattr(event, "chat", None)
        if not chat and hasattr(event, "message") and event.message:
            chat = event.message.chat

        if chat and chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            try:
                member = await bot.get_chat_member(chat.id, user.id)
                return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
            except Exception:
                return False

        return False
