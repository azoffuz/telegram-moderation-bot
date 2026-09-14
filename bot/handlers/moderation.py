import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions
from bot.config import config
from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.logger import log_moderation
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="moderation")

def parse_time_duration(time_arg: Optional[str]) -> Tuple[timedelta, str]:
    """
    Vaqt satrini (30m, 2h, 1d, 1w) timedelta va o'zbekcha matnga aylantiradi.
    Sukut bo'yicha: 1 soat.
    """
    if not time_arg:
        return timedelta(hours=1), "1 soat"

    pattern = re.compile(r"^(\d+)([mhdws])$", re.IGNORECASE)
    match = pattern.match(time_arg.strip())
    if not match:
        return timedelta(hours=1), "1 soat"

    val = int(match.group(1))
    unit = match.group(2).lower()

    if unit == "m":
        return timedelta(minutes=val), f"{val} daqiqa"
    elif unit == "h":
        return timedelta(hours=val), f"{val} soat"
    elif unit == "d":
        return timedelta(days=val), f"{val} kun"
    elif unit == "w":
        return timedelta(weeks=val), f"{val} hafta"
    elif unit == "s":
        return timedelta(seconds=val), f"{val} soniya"

    return timedelta(hours=1), "1 soat"

def get_target_user(message: Message) -> Optional[tuple]:
    """
    Xabarning reply qilingan qismidan yoki argumentidan foydalanuvchini oladi.
    """
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    return None

# ==================== /warn ====================
@router.message(Command("warn"), IsGroupFilter())
async def cmd_warn(message: Message, bot: Bot):
    """Foydalanuvchiga ogohlantirish berish."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target = get_target_user(message)
    if not target:
        msg = await message.reply("ℹ️ Ogohlantirish berish uchun biror xabarga reply qilib <code>/warn [sabab]</code> deb yozing.")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    if target.id == bot.id or target.id in config.ADMIN_IDS:
        msg = await message.reply("❌ Bot yoki adminlarga jazo qo'llab bo'lmaydi!")
        auto_delete(message, 5)
        auto_delete(msg, 5)
        return

    # Sababni ajratib olish
    args = message.text.split(maxsplit=1)
    reason = args[1] if len(args) > 1 else "Qoidabuzarlik"

    new_count = await db.add_warn(target.id, message.chat.id, reason)

    # Agar limitga yetsa (masalan, 3 ta bo'lsa)
    if new_count >= config.MAX_WARNS:
        await db.reset_warns(target.id, message.chat.id)
        
        # 24 soatga mute qilamiz
        until = datetime.now() + timedelta(hours=24)
        try:
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=target.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            
            resp = await message.reply(
                f"🚫 <a href=\"tg://user?id={target.id}\">{target.full_name}</a> <b>{config.MAX_WARNS} ta</b> "
                f"ogohlantirish oldi va <b>24 soatga mute</b> qilindi!\n"
                f"📌 <b>So'nggi sabab:</b> {reason}",
                parse_mode="HTML"
            )
            auto_delete(resp, 20)

            await log_moderation(
                bot=bot,
                admin=message.from_user,
                target_user=target,
                action=f"Mute ({config.MAX_WARNS} warn)",
                reason=reason,
                details="24 soatga cheklandi"
            )
        except Exception as e:
            logger.error(f"Warn limit mute xatosi: {e}")
    else:
        resp = await message.reply(
            f"⚠️ <a href=\"tg://user?id={target.id}\">{target.full_name}</a> ogohlantirildi! "
            f"(<b>{new_count}/{config.MAX_WARNS}</b>)\n"
            f"📌 <b>Sabab:</b> {reason}",
            parse_mode="HTML"
        )
        auto_delete(resp, 20)

        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=target,
            action=f"Warn ({new_count}/{config.MAX_WARNS})",
            reason=reason
        )

    auto_delete(message, 15)

# ==================== /unwarn ====================
@router.message(Command("unwarn"), IsGroupFilter())
async def cmd_unwarn(message: Message, bot: Bot):
    """Ogohlantirishni kamaytirish."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target = get_target_user(message)
    if not target:
        msg = await message.reply("ℹ️ Ogohlantirishni bekor qilish uchun biror xabarga reply qilib <code>/unwarn</code> deb yozing.")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    new_count = await db.remove_warn(target.id, message.chat.id)
    resp = await message.reply(
        f"✅ <a href=\"tg://user?id={target.id}\">{target.full_name}</a> dan bitta ogohlantirish olib tashlandi.\n"
        f"📊 Joriy ogohlantirishlar: <b>{new_count}/{config.MAX_WARNS}</b>",
        parse_mode="HTML"
    )
    auto_delete(message, 15)
    auto_delete(resp, 15)

# ==================== /warns ====================
@router.message(Command("warns"), IsGroupFilter())
async def cmd_warns(message: Message, bot: Bot):
    """Foydalanuvchining ogohlantirishlar sonini ko'rish."""
    target = get_target_user(message) or message.from_user
    count = await db.get_warn_count(target.id, message.chat.id)
    
    resp = await message.reply(
        f"📊 <a href=\"tg://user?id={target.id}\">{target.full_name}</a> hisobidagi ogohlantirishlar: "
        f"<b>{count}/{config.MAX_WARNS}</b> ta.",
        parse_mode="HTML"
    )
    auto_delete(message, 15)
    auto_delete(resp, 15)

# ==================== /mute ====================
@router.message(Command("mute"), IsGroupFilter())
async def cmd_mute(message: Message, bot: Bot):
    """Foydalanuvchini vaqtincha yoki doimiy mute qilish."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target = get_target_user(message)
    if not target:
        msg = await message.reply("ℹ️ Foydalanuvchini mute qilish uchun reply qilib <code>/mute [vaqt] [sabab]</code> deb yozing.\nMisol: <code>/mute 30m Haqorat</code>")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    if target.id == bot.id or target.id in config.ADMIN_IDS:
        msg = await message.reply("❌ Bot yoki adminlarga jazo qo'llab bo'lmaydi!")
        auto_delete(message, 5)
        auto_delete(msg, 5)
        return

    # Argumentlarni tekshirish (/mute 30m Sabab)
    parts = message.text.split(maxsplit=2)
    time_arg = parts[1] if len(parts) > 1 else None
    reason = parts[2] if len(parts) > 2 else "Admin qarori"

    delta, duration_str = parse_time_duration(time_arg)
    until = datetime.now() + delta

    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )

        resp = await message.reply(
            f"🔇 <a href=\"tg://user?id={target.id}\">{target.full_name}</a> <b>{duration_str}</b> muddatga mute qilindi.\n"
            f"📌 <b>Sabab:</b> {reason}",
            parse_mode="HTML"
        )
        auto_delete(resp, 20)

        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=target,
            action="Mute",
            reason=reason,
            details=f"Muddat: {duration_str}"
        )
    except Exception as e:
        logger.error(f"Mute qilishda xatolik: {e}")

    auto_delete(message, 15)

# ==================== /unmute ====================
@router.message(Command("unmute"), IsGroupFilter())
async def cmd_unmute(message: Message, bot: Bot):
    """Mutedan chiqarish."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target = get_target_user(message)
    if not target:
        msg = await message.reply("ℹ️ Reply qilib <code>/unmute</code> deb yozing.")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        resp = await message.reply(
            f"🔊 <a href=\"tg://user?id={target.id}\">{target.full_name}</a> dan barcha cheklovlar olib tashlandi.",
            parse_mode="HTML"
        )
        auto_delete(resp, 15)

        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=target,
            action="Unmute",
            reason="Admin cheklovni bekor qildi"
        )
    except Exception as e:
        logger.error(f"Unmute qilishda xatolik: {e}")

    auto_delete(message, 15)

# ==================== /ban ====================
@router.message(Command("ban"), IsGroupFilter())
async def cmd_ban(message: Message, bot: Bot):
    """Foydalanuvchini guruhdan butunlay ban qilish."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target = get_target_user(message)
    if not target:
        msg = await message.reply("ℹ️ Ban qilish uchun biror xabarga reply qilib <code>/ban [sabab]</code> deb yozing.")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    if target.id == bot.id or target.id in config.ADMIN_IDS:
        msg = await message.reply("❌ Bot yoki adminlarga jazo qo'llab bo'lmaydi!")
        auto_delete(message, 5)
        auto_delete(msg, 5)
        return

    parts = message.text.split(maxsplit=1)
    reason = parts[1] if len(parts) > 1 else "Guruh qoidalarini buzish"

    try:
        await bot.ban_chat_member(chat_id=message.chat.id, user_id=target.id)
        resp = await message.reply(
            f"🔨 <a href=\"tg://user?id={target.id}\">{target.full_name}</a> guruhdan <b>BAN</b> qilindi!\n"
            f"📌 <b>Sabab:</b> {reason}",
            parse_mode="HTML"
        )
        auto_delete(resp, 20)

        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=target,
            action="Ban",
            reason=reason
        )
    except Exception as e:
        logger.error(f"Ban qilishda xatolik: {e}")

    auto_delete(message, 15)

# ==================== /unban ====================
@router.message(Command("unban"), IsGroupFilter())
async def cmd_unban(message: Message, bot: Bot):
    """Foydalanuvchini bandan chiqarish."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    parts = message.text.split(maxsplit=1)
    target_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif len(parts) > 1 and parts[1].strip().isdigit():
        target_id = int(parts[1].strip())

    if not target_id:
        msg = await message.reply("ℹ️ Bandan chiqarish uchun reply qiling yoki ID kiriting: <code>/unban 12345678</code>")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    try:
        await bot.unban_chat_member(chat_id=message.chat.id, user_id=target_id)
        resp = await message.reply(f"✅ <code>{target_id}</code> hisobidagi ban bekor qilindi.", parse_mode="HTML")
        auto_delete(resp, 15)
    except Exception as e:
        logger.error(f"Unban xatolik: {e}")

    auto_delete(message, 15)

# ==================== /kick ====================
@router.message(Command("kick"), IsGroupFilter())
async def cmd_kick(message: Message, bot: Bot):
    """Foydalanuvchini guruhdan chiqarib yuborish (lekin qayta kirishi mumkin)."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target = get_target_user(message)
    if not target:
        msg = await message.reply("ℹ️ Kick qilish uchun reply qilib <code>/kick [sabab]</code> deb yozing.")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    if target.id == bot.id or target.id in config.ADMIN_IDS:
        msg = await message.reply("❌ Bot yoki adminlarga jazo qo'llab bo'lmaydi!")
        auto_delete(message, 5)
        auto_delete(msg, 5)
        return

    parts = message.text.split(maxsplit=1)
    reason = parts[1] if len(parts) > 1 else "Guruhdan chiqarildi"

    try:
        await bot.ban_chat_member(chat_id=message.chat.id, user_id=target.id)
        await bot.unban_chat_member(chat_id=message.chat.id, user_id=target.id)
        
        resp = await message.reply(
            f"👢 <a href=\"tg://user?id={target.id}\">{target.full_name}</a> guruhdan chiqarildi.\n"
            f"📌 <b>Sabab:</b> {reason}",
            parse_mode="HTML"
        )
        auto_delete(resp, 20)

        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=target,
            action="Kick",
            reason=reason
        )
    except Exception as e:
        logger.error(f"Kick qilishda xatolik: {e}")

    auto_delete(message, 15)

# ==================== /clean ====================
@router.message(Command("clean"), IsGroupFilter())
async def cmd_clean(message: Message, bot: Bot):
    """Chatdagi oxirgi X ta xabarni tozalash (/clean 20)."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    parts = message.text.split()
    amount = 10
    if len(parts) > 1 and parts[1].isdigit():
        amount = min(int(parts[1]), 100)  # Chegara: bir vaqtda maks 100 ta

    current_id = message.message_id
    deleted_count = 0

    for i in range(amount + 1):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=current_id - i)
            deleted_count += 1
        except Exception:
            pass

    confirm_msg = await bot.send_message(
        chat_id=message.chat.id,
        text=f"🧹 <b>{deleted_count} ta</b> xabar muvaffaqiyatli tozalandi.",
        parse_mode="HTML"
    )
    auto_delete(confirm_msg, delay=5)
