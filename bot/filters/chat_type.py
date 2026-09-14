from typing import Union
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.enums import ChatType

class IsGroupFilter(Filter):
    """
    Xabar yoki hodisa guruh / superguruhda sodir bo'lganini tekshiradi.
    """
    async def __call__(self, event: Union[Message, CallbackQuery, ChatMemberUpdated]) -> bool:
        chat = getattr(event, "chat", None)
        if not chat and hasattr(event, "message") and event.message:
            chat = event.message.chat

        if chat and chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            return True
        return False
