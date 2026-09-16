import time
from typing import Union, Dict, Tuple, Set
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus, ChatType
from bot.config import config
from bot.database import db

# Guruh adminlari keshi: {chat_id: (timestamp, {admin_user_id, ...})}
# Har bir oddiy foydalanuvchi xabari uchun Telegram API ga qayta-qayta HTTP so'rov yubormaslik uchun!
_chat_admins_cache: Dict[int, Tuple[float, Set[int]]] = {}

def invalidate_chat_admins_cache(chat_id: int):
    """Guruh adminlari o'zgarganda keshni darhol tozalash."""
    _chat_admins_cache.pop(chat_id, None)

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
    Umumiy moderatsiya uchun yuqori tezlikdagi adminlik tekshiruvi:
    1. Owner (0ms)
    2. Bot Admini (RAM kesh: 0ms)
    3. Telegram guruhining administratori (RAM kesh: 0ms)
    """
    async def __call__(self, event: Union[Message, CallbackQuery, ChatMemberUpdated], bot) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False

        # 1. Owner yoki Bot Admini bo'lsa (0ms RAM kesh)
        if await db.is_bot_admin(user.id):
            return True

        # 2. Guruh admini ekanligini tekshirish (Kesh orqali)
        chat = getattr(event, "chat", None)
        if not chat and hasattr(event, "message") and event.message:
            chat = event.message.chat

        if chat and chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            now = time.time()
            cached = _chat_admins_cache.get(chat.id)
            if cached and (now - cached[0] < 120):
                return user.id in cached[1]

            try:
                admins = await bot.get_chat_administrators(chat.id)
                admin_set = {a.user.id for a in admins}
                _chat_admins_cache[chat.id] = (now, admin_set)
                return user.id in admin_set
            except Exception:
                try:
                    member = await bot.get_chat_member(chat.id, user.id)
                    return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
                except Exception:
                    return False

        return False
