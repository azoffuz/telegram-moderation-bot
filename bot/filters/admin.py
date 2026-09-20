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

# Guruhning biriktirilgan kanali keshi: {chat_id: (timestamp, linked_chat_id)}
_chat_linked_cache: Dict[int, Tuple[float, Optional[int]]] = {}

def invalidate_chat_admins_cache(chat_id: int):
    """Guruh adminlari o'zgarganda keshni darhol tozalash."""
    _chat_admins_cache.pop(chat_id, None)
    _chat_linked_cache.pop(chat_id, None)

async def get_linked_chat_id(bot, chat_id: int) -> Optional[int]:
    """Guruhga ulangan kanal ID sini keshlab qaytaradi."""
    now = time.time()
    cached = _chat_linked_cache.get(chat_id)
    if cached and (now - cached[0] < 3600):
        return cached[1]
    try:
        chat_info = await bot.get_chat(chat_id)
        linked_id = getattr(chat_info, "linked_chat_id", None)
        _chat_linked_cache[chat_id] = (now, linked_id)
        return linked_id
    except Exception:
        return None

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
    1. Telegram avtomatik uzatmasi (Linked Channel xabarlari: 0ms)
    2. Telegram xizmat akkaunti (777000: 0ms)
    3. Anonim admin yoki biriktirilgan kanal (@Reker_UZ: 0ms)
    4. Owner (0ms)
    5. Bot Admini (RAM kesh: 0ms)
    6. Telegram guruhining administratori (RAM kesh: 0ms)
    """
    async def __call__(self, event: Union[Message, CallbackQuery, ChatMemberUpdated], bot) -> bool:
        # 1. Telegram tomonidan kanaldan avtomatik uzatilgan xabarlar (Linked Channel)
        if getattr(event, "is_automatic_forward", False):
            return True

        user = getattr(event, "from_user", None)
        # 2. Telegram rasmiy xizmat akkaunti (777000 - kanal xabarlari avtomatik forward qilinganda)
        if user and user.id == 777000:
            return True

        # 3. Guruh yoki kanal nomidan yuborilgan xabarlar
        sender_chat = getattr(event, "sender_chat", None)
        chat = getattr(event, "chat", None)
        if not chat and hasattr(event, "message") and event.message:
            chat = event.message.chat

        if sender_chat:
            # Anonim admin (guruh nomidan yozish)
            if chat and sender_chat.id == chat.id:
                return True

            # Foydalanuvchining rasmiy kanali (@Reker_UZ)
            sender_username = (sender_chat.username or "").lower()
            if sender_username in ["reker_uz", "rekeruz"]:
                return True

            # Guruhga ulangan rasmiy kanal (linked_chat_id)
            if chat:
                linked_id = await get_linked_chat_id(bot, chat.id)
                if linked_id and sender_chat.id == linked_id:
                    return True

        if not user:
            return False

        # 4. Owner yoki Bot Admini bo'lsa (0ms RAM kesh)
        if await db.is_bot_admin(user.id):
            return True

        # 5. Guruh admini ekanligini tekshirish (Kesh orqali)
        if chat and chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            now = time.time()
            cached = _chat_admins_cache.get(chat.id)
            if cached and (now - cached[0] < 120):
                return user.id in cached[1]

            try:
                admins = await bot.get_chat_administrators(chat.id)
                admin_set = set()
                for a in admins:
                    # Faqat haqiqiy boshqaruv huquqiga ega adminlarni olamiz:
                    # Agar a'zoda faqat "Active" unvoni bo'lsa va xabarlarni o'chirish huquqi bo'lmasa, uni admin deb hisoblamaymiz!
                    if getattr(a, "custom_title", "") == "Active" and not getattr(a, "can_delete_messages", False):
                        continue
                    admin_set.add(a.user.id)
                _chat_admins_cache[chat.id] = (now, admin_set)
                return user.id in admin_set
            except Exception:
                try:
                    member = await bot.get_chat_member(chat.id, user.id)
                    if getattr(member, "custom_title", "") == "Active" and not getattr(member, "can_delete_messages", False):
                        return False
                    return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
                except Exception:
                    return False

        return False
