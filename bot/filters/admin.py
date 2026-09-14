from typing import Union
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus, ChatType
from bot.config import config

class IsAdminFilter(Filter):
    """
    Foydalanuvchi asosiy admin (ADMIN_IDS) yoki guruh administratori ekanligini tekshiradi.
    """
    async def __call__(self, event: Union[Message, CallbackQuery, ChatMemberUpdated], bot) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False

        # 1. Configdagi asosiy adminlar ro'yxatida bo'lsa
        if user.id in config.ADMIN_IDS:
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
