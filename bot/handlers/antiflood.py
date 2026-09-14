import time
import logging
from typing import Dict, List
from datetime import datetime, timedelta
from aiogram import Router, Bot
from aiogram.types import Message, ChatPermissions
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.database import db
from bot.services.logger import log_moderation
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="antiflood")

# Har bir foydalanuvchining so'nggi xabarlar vaqti: user_id -> [timestamp, ...]
user_message_times: Dict[int, List[float]] = {}

FLOOD_RATE_LIMIT = 5  # Maksimal ruxsat etilgan xabarlar soni
FLOOD_TIME_WINDOW = 4.0  # Vaqt oralig'i (soniyalarda)
MUTE_DURATION_MINUTES = 10  # Qoidabuzarni mute qilish vaqti

@router.message(IsGroupFilter())
async def anti_flood_handler(message: Message, bot: Bot):
    """
    Tezkor spam va floodni aniqlaydi va qoidabuzarni 10 daqiqaga mute qiladi.
    """
    if not message.from_user:
        return

    # Adminlarni cheklamaymiz
    is_admin = await IsAdminFilter()(message, bot)
    if is_admin:
        return

    # Admin paneldan Anti-Flood o'chirilgan bo'lsa
    if not await db.get_chat_setting_bool(message.chat.id, "anti_flood", default=True):
        return

    user_id = message.from_user.id
    now = time.time()

    if user_id not in user_message_times:
        user_message_times[user_id] = []

    # Eski vaqtlarni tozalaymiz
    user_message_times[user_id] = [
        t for t in user_message_times[user_id] if now - t < FLOOD_TIME_WINDOW
    ]
    user_message_times[user_id].append(now)

    # Agar limitdan oshib ketsa
    if len(user_message_times[user_id]) > FLOOD_RATE_LIMIT:
        user_message_times[user_id].clear()
        
        try:
            # Xabarni o'chirish
            await message.delete()
        except Exception:
            pass

        until_date = datetime.now() + timedelta(minutes=MUTE_DURATION_MINUTES)
        user = message.from_user

        try:
            # 10 daqiqaga mute qilish
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )

            warn_msg = await message.answer(
                f"🔇 <a href=\"tg://user?id={user.id}\">{user.full_name}</a> spam/flood sababli "
                f"<b>{MUTE_DURATION_MINUTES} daqiqaga</b> mute qilindi!",
                parse_mode="HTML"
            )
            auto_delete(warn_msg, delay=10)

            # Log kanalga yozish
            await log_moderation(
                bot=bot,
                admin=None,
                target_user=user,
                action="Mute (Anti-Flood)",
                reason=f"{FLOOD_TIME_WINDOW} soniyada {FLOOD_RATE_LIMIT}+ ta xabar yozdi",
                details=f"{MUTE_DURATION_MINUTES} daqiqaga cheklandi"
            )
        except Exception as e:
            logger.error(f"Anti-flood mute qilishda xatolik ({user.id}): {e}")
