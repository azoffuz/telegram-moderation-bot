import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions, User
from aiogram.enums import MessageEntityType
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

TIME_PATTERN = re.compile(r"^(\d+)([mhdws])$", re.IGNORECASE)

def is_time_string(s: str) -> bool:
    """Satr vaqt formati (masalan 10h, 30m, 1d, 1w) ekanligini tekshiradi."""
    return bool(TIME_PATTERN.match(s.strip()))

async def parse_target_and_arguments(
    message: Message,
    bot: Bot
) -> Tuple[Optional[int], Optional[str], Optional[str], timedelta, str, str]:
    """
    Moderatsiya buyruqlari (/mute, /ban, /warn, /unmute, /unban) uchun
    foydalanuvchi, vaqt va sababni eng moslashuvchan tarzda aniqlaydi.
    
    Qo'llab-quvvatlaydi:
    • /mute @username 10h [sabab]
    • /mute @username 10h
    • /mute @username [sabab]
    • /mute @username
    • /mute 123456789 10h [sabab]
    • Reply qilib: /mute 10h [sabab]
    • Reply qilib: /mute 10h
    • Reply qilib: /mute [sabab]
    • Reply qilib: /mute
    
    Qaytaradi: (target_id, target_name, target_username, delta, duration_str, reason)
    """
    tokens = message.text.split()[1:] if message.text else []

    target_id: Optional[int] = None
    target_name: Optional[str] = None
    target_username: Optional[str] = None
    time_str: Optional[str] = None
    reason_tokens: list = []

    # 1. Agar biror xabarga reply qilingan bo'lsa
    if message.reply_to_message and message.reply_to_message.from_user:
        replied_user = message.reply_to_message.from_user
        target_id = replied_user.id
        target_name = replied_user.full_name
        target_username = replied_user.username

        if tokens:
            if is_time_string(tokens[0]):
                time_str = tokens[0]
                reason_tokens = tokens[1:]
            else:
                reason_tokens = tokens

    # 2. Agar argumentlar orqali ko'rsatilgan bo'lsa
    elif tokens:
        first = tokens[0]
        rest = tokens[1:]

        # a) Text mention entity tekshirish
        for ent in (message.entities or []):
            if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
                target_id = ent.user.id
                target_name = ent.user.full_name
                target_username = ent.user.username
                break

        # b) Agar @username bo'lsa
        if not target_id and first.startswith("@"):
            uname = first[1:].strip()
            target_username = uname
            db_user = await db.get_user_by_username(uname)
            if db_user:
                target_id = db_user["user_id"]
                target_name = db_user["full_name"]
                target_username = db_user["username"]
            else:
                try:
                    chat = await bot.get_chat(first)
                    target_id = chat.id
                    target_name = chat.full_name or first
                    target_username = chat.username or uname
                except Exception:
                    target_name = first

        # c) Agar to'g'ridan-to'g'ri raqamli ID bo'lsa
        elif not target_id and first.lstrip("-").isdigit():
            target_id = int(first)
            db_user = await db.get_user_by_id(target_id)
            if db_user:
                target_name = db_user["full_name"]
                target_username = db_user["username"]
            else:
                try:
                    chat_member = await bot.get_chat_member(message.chat.id, target_id)
                    target_name = chat_member.user.full_name
                    target_username = chat_member.user.username
                except Exception:
                    target_name = f"ID: {target_id}"

        # Agar target aniqlangan bo'lsa, qolgan tokenlarni vaqt va sababga ajratamiz
        if target_id or first.startswith("@") or first.lstrip("-").isdigit():
            if rest:
                if is_time_string(rest[0]):
                    time_str = rest[0]
                    reason_tokens = rest[1:]
                else:
                    reason_tokens = rest

    delta, duration_str = parse_time_duration(time_str)
    reason = " ".join(reason_tokens).strip() or "Admin qarori"

    return target_id, target_name, target_username, delta, duration_str, reason

# ==================== /warn ====================
@router.message(Command("warn"), IsGroupFilter())
async def cmd_warn(message: Message, bot: Bot):
    """Foydalanuvchiga ogohlantirish berish (/warn @username [sabab] yoki reply)."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target_id, target_name, target_username, _, _, reason = await parse_target_and_arguments(message, bot)
    if not target_id:
        msg = await message.reply("ℹ️ Ogohlantirish berish uchun reply qilib <code>/warn [sabab]</code> yoki <code>/warn @username [sabab]</code> deb yozing.", parse_mode="HTML")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    if target_id == bot.id or target_id in config.ADMIN_IDS:
        msg = await message.reply("❌ Bot yoki adminlarga jazo qo'llab bo'lmaydi!")
        auto_delete(message, 5)
        auto_delete(msg, 5)
        return

    new_count = await db.add_warn(target_id, message.chat.id, reason)
    target_dummy = User(id=target_id, is_bot=False, first_name=target_name or "Foydalanuvchi", username=target_username)
    max_warns = await db.get_chat_setting_int(message.chat.id, "max_warns", default=config.MAX_WARNS)

    # Agar limitga yetsa
    if new_count >= max_warns:
        await db.reset_warns(target_id, message.chat.id)
        
        # 24 soatga mute qilamiz
        until = datetime.now() + timedelta(hours=24)
        try:
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            
            resp = await message.reply(
                f"🚫 <a href=\"tg://user?id={target_id}\">{target_name}</a> <b>{max_warns} ta</b> "
                f"ogohlantirish oldi va <b>24 soatga mute</b> qilindi!\n"
                f"📌 <b>So'nggi sabab:</b> {reason}",
                parse_mode="HTML"
            )
            auto_delete(resp, 20)

            await log_moderation(
                bot=bot,
                admin=message.from_user,
                target_user=target_dummy,
                action=f"Mute ({max_warns} warn)",
                reason=reason,
                details="24 soatga cheklandi"
            )
        except Exception as e:
            logger.error(f"Warn limit mute xatosi: {e}")
    else:
        resp = await message.reply(
            f"⚠️ <a href=\"tg://user?id={target_id}\">{target_name}</a> ogohlantirildi! "
            f"(<b>{new_count}/{max_warns}</b>)\n"
            f"📌 <b>Sabab:</b> {reason}",
            parse_mode="HTML"
        )
        auto_delete(resp, 20)

        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=target_dummy,
            action=f"Warn ({new_count}/{max_warns})",
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

    target_id, target_name, _, _, _, _ = await parse_target_and_arguments(message, bot)
    if not target_id:
        msg = await message.reply("ℹ️ Ogohlantirishni bekor qilish uchun reply qiling yoki <code>/unwarn @username</code> deb yozing.", parse_mode="HTML")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    new_count = await db.remove_warn(target_id, message.chat.id)
    max_warns = await db.get_chat_setting_int(message.chat.id, "max_warns", default=config.MAX_WARNS)
    resp = await message.reply(
        f"✅ <a href=\"tg://user?id={target_id}\">{target_name}</a> dan bitta ogohlantirish olib tashlandi.\n"
        f"📊 Joriy ogohlantirishlar: <b>{new_count}/{max_warns}</b>",
        parse_mode="HTML"
    )
    auto_delete(message, 15)
    auto_delete(resp, 15)

# ==================== /warns ====================
@router.message(Command("warns"), IsGroupFilter())
async def cmd_warns(message: Message, bot: Bot):
    """Foydalanuvchining ogohlantirishlar sonini ko'rish."""
    target_id, target_name, _, _, _, _ = await parse_target_and_arguments(message, bot)
    if not target_id:
        target_id = message.from_user.id
        target_name = message.from_user.full_name

    count = await db.get_warn_count(target_id, message.chat.id)
    max_warns = await db.get_chat_setting_int(message.chat.id, "max_warns", default=config.MAX_WARNS)
    
    resp = await message.reply(
        f"📊 <a href=\"tg://user?id={target_id}\">{target_name}</a> hisobidagi ogohlantirishlar: "
        f"<b>{count}/{max_warns}</b> ta.",
        parse_mode="HTML"
    )
    auto_delete(message, 15)
    auto_delete(resp, 15)

# ==================== /mute ====================
@router.message(Command("mute"), IsGroupFilter())
async def cmd_mute(message: Message, bot: Bot):
    """
    Foydalanuvchini vaqtincha yoki doimiy mute qilish.
    Formatlar:
    • /mute @username 10h [sabab]
    • /mute @username 10h
    • /mute @username [sabab]
    • /mute @username
    • /mute 123456789 10h [sabab]
    • Reply qilib: /mute 10h [sabab]
    """
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target_id, target_name, target_username, delta, duration_str, reason = await parse_target_and_arguments(message, bot)

    if not target_id:
        msg = await message.reply(
            "ℹ️ <b>Mute qilish usullari:</b>\n"
            "• <code>/mute @username 10h [sabab]</code> (sababi ixtiyoriy)\n"
            "• <code>/mute 10h [sabab]</code> (xabarga reply qilib)\n"
            "• <code>/mute 123456789 10h</code>\n\n"
            "<i>Eslatma: Agar @username topilmasa, xabariga reply qilib yoki ID raqami orqali yozing.</i>",
            parse_mode="HTML"
        )
        auto_delete(message, 15)
        auto_delete(msg, 15)
        return

    if target_id == bot.id or target_id in config.ADMIN_IDS:
        msg = await message.reply("❌ Bot yoki adminlarga jazo qo'llab bo'lmaydi!")
        auto_delete(message, 5)
        auto_delete(msg, 5)
        return

    until = datetime.now() + delta

    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )

        resp = await message.reply(
            f"🔇 <a href=\"tg://user?id={target_id}\">{target_name}</a> <b>{duration_str}</b> muddatga mute qilindi.\n"
            f"📌 <b>Sabab:</b> {reason}",
            parse_mode="HTML"
        )
        auto_delete(resp, 20)

        target_dummy = User(id=target_id, is_bot=False, first_name=target_name or "Foydalanuvchi", username=target_username)
        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=target_dummy,
            action="Mute",
            reason=reason,
            details=f"Muddat: {duration_str}"
        )
    except Exception as e:
        logger.error(f"Mute qilishda xatolik: {e}")
        err_msg = await message.reply(f"❌ Mute qilishda xatolik yuz berdi: {e}")
        auto_delete(err_msg, 10)

    auto_delete(message, 15)

# ==================== /unmute ====================
@router.message(Command("unmute"), IsGroupFilter())
async def cmd_unmute(message: Message, bot: Bot):
    """Mutedan chiqarish (/unmute @username yoki reply)."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target_id, target_name, target_username, _, _, _ = await parse_target_and_arguments(message, bot)

    if not target_id:
        msg = await message.reply("ℹ️ Reply qiling yoki <code>/unmute @username</code> / <code>/unmute 12345678</code> deb yozing.", parse_mode="HTML")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        resp = await message.reply(
            f"🔊 <a href=\"tg://user?id={target_id}\">{target_name}</a> dan barcha cheklovlar olib tashlandi.",
            parse_mode="HTML"
        )
        auto_delete(resp, 15)

        target_dummy = User(id=target_id, is_bot=False, first_name=target_name or "Foydalanuvchi", username=target_username)
        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=target_dummy,
            action="Unmute",
            reason="Admin cheklovni bekor qildi"
        )
    except Exception as e:
        logger.error(f"Unmute qilishda xatolik: {e}")

    auto_delete(message, 15)

# ==================== /ban ====================
@router.message(Command("ban"), IsGroupFilter())
async def cmd_ban(message: Message, bot: Bot):
    """Foydalanuvchini guruhdan butunlay ban qilish (/ban @username [sabab] yoki reply)."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target_id, target_name, target_username, _, _, reason = await parse_target_and_arguments(message, bot)

    if not target_id:
        msg = await message.reply("ℹ️ Ban qilish uchun reply qiling yoki <code>/ban @username [sabab]</code> deb yozing.", parse_mode="HTML")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    if target_id == bot.id or target_id in config.ADMIN_IDS:
        msg = await message.reply("❌ Bot yoki adminlarga jazo qo'llab bo'lmaydi!")
        auto_delete(message, 5)
        auto_delete(msg, 5)
        return

    try:
        await bot.ban_chat_member(chat_id=message.chat.id, user_id=target_id)
        resp = await message.reply(
            f"🔨 <a href=\"tg://user?id={target_id}\">{target_name}</a> guruhdan <b>BAN</b> qilindi!\n"
            f"📌 <b>Sabab:</b> {reason}",
            parse_mode="HTML"
        )
        auto_delete(resp, 20)

        target_dummy = User(id=target_id, is_bot=False, first_name=target_name or "Foydalanuvchi", username=target_username)
        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=target_dummy,
            action="Ban",
            reason=reason
        )
    except Exception as e:
        logger.error(f"Ban qilishda xatolik: {e}")

    auto_delete(message, 15)

# ==================== /unban ====================
@router.message(Command("unban"), IsGroupFilter())
async def cmd_unban(message: Message, bot: Bot):
    """Foydalanuvchini bandan chiqarish (/unban @username yoki /unban 12345)."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target_id, target_name, _, _, _, _ = await parse_target_and_arguments(message, bot)

    if not target_id:
        msg = await message.reply("ℹ️ Bandan chiqarish uchun reply qiling yoki ID/username kiriting: <code>/unban @username</code>", parse_mode="HTML")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    try:
        await bot.unban_chat_member(chat_id=message.chat.id, user_id=target_id)
        resp = await message.reply(f"✅ <code>{target_name or target_id}</code> hisobidagi ban bekor qilindi.", parse_mode="HTML")
        auto_delete(resp, 15)
    except Exception as e:
        logger.error(f"Unban xatolik: {e}")

    auto_delete(message, 15)

# ==================== /kick ====================
@router.message(Command("kick"), IsGroupFilter())
async def cmd_kick(message: Message, bot: Bot):
    """Foydalanuvchini guruhdan chiqarib yuborish (/kick @username [sabab] yoki reply)."""
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    target_id, target_name, target_username, _, _, reason = await parse_target_and_arguments(message, bot)
    if not target_id:
        msg = await message.reply("ℹ️ Kick qilish uchun reply qiling yoki <code>/kick @username [sabab]</code> deb yozing.", parse_mode="HTML")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    if target_id == bot.id or target_id in config.ADMIN_IDS:
        msg = await message.reply("❌ Bot yoki adminlarga jazo qo'llab bo'lmaydi!")
        auto_delete(message, 5)
        auto_delete(msg, 5)
        return

    try:
        await bot.ban_chat_member(chat_id=message.chat.id, user_id=target_id)
        await bot.unban_chat_member(chat_id=message.chat.id, user_id=target_id)
        
        resp = await message.reply(
            f"👢 <a href=\"tg://user?id={target_id}\">{target_name}</a> guruhdan chiqarildi.\n"
            f"📌 <b>Sabab:</b> {reason}",
            parse_mode="HTML"
        )
        auto_delete(resp, 20)

        target_dummy = User(id=target_id, is_bot=False, first_name=target_name or "Foydalanuvchi", username=target_username)
        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=target_dummy,
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

# ==================== /cleandeleted (O'CHIRILGAN AKKAUNTLARNI TOZALASH) ====================
@router.message(Command("cleandeleted", "kickdeleted", "delacc"), IsGroupFilter())
async def cmd_clean_deleted(message: Message, bot: Bot):
    """
    Guruhdagi o'chirilgan (Deleted Account) a'zolarni aniqlab, guruhdan chiqarib yuboradi.
    """
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    chat_id = message.chat.id

    # Botning guruhda a'zolarni cheklash/chiqarish huquqini tekshiramiz
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if not getattr(bot_member, "can_restrict_members", False) and bot_member.status != "creator":
            msg = await message.reply("❌ <b>Xatolik:</b> Botda a'zolarni chiqarish (Ban/Kick) huquqi yo'q!", parse_mode="HTML")
            auto_delete(message, 5)
            auto_delete(msg, 10)
            return
    except Exception as e:
        logger.error(f"Bot huquqini tekshirishda xatolik: {e}")

    status_msg = await message.reply(
        "🔍 <b>O'chirilgan akkauntlar (Deleted Accounts) tekshirilmoqda...</b>\n"
        "<i>Iltimos kuting, bot ma'lumotlar bazasi va guruh a'zolarini tahlil qilmoqda...</i>",
        parse_mode="HTML"
    )

    candidate_ids = set()

    # 1. Guruh adminlarini tekshiramiz (adminlar ro'yxatida qolib ketgan deleted acc larni topish)
    try:
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.status != "creator" and admin.user.id != bot.id:
                candidate_ids.add(admin.user.id)
    except Exception as e:
        logger.debug(f"Adminlarni olishda xatolik: {e}")

    # 2. Bazadagi ushbu guruhga oid barcha a'zolarni qo'shamiz
    group_ids = await db.get_chat_member_ids(chat_id)
    candidate_ids.update(group_ids)

    # 3. Tizimda mavjud barcha ma'lum foydalanuvchilar ID larini ham qo'shamiz
    known_ids = await db.get_all_known_user_ids()
    candidate_ids.update(known_ids)

    # Botning o'zini va buyruq bergan adminni ro'yxatdan chiqaramiz
    candidate_ids.discard(bot.id)
    candidate_ids.discard(message.from_user.id)

    deleted_count = 0
    checked_count = 0

    for uid in candidate_ids:
        try:
            member = await bot.get_chat_member(chat_id, uid)
            checked_count += 1

            if member.status in ["member", "restricted", "administrator"] and member.status != "creator":
                fname = (member.user.first_name or "").strip().lower()
                is_deleted = (
                    fname == "deleted account" or
                    "deleted account" in fname or
                    "удален" in fname
                )
                if is_deleted:
                    try:
                        await bot.ban_chat_member(chat_id=chat_id, user_id=uid)
                        await bot.unban_chat_member(chat_id=chat_id, user_id=uid)
                        await db.remove_chat_member(chat_id, uid)
                        deleted_count += 1
                    except Exception as kick_err:
                        logger.debug(f"Deleted account {uid} ni chiqarishda xatolik: {kick_err}")
            elif member.status in ["left", "kicked"]:
                await db.remove_chat_member(chat_id, uid)
        except Exception:
            # Agar foydalanuvchi umuman topilmasa yoki chatda bo'lmasa
            pass

        # Telegram FloodLimit ga tushmaslik uchun tanaffus
        if checked_count % 10 == 0:
            await asyncio.sleep(0.05)

    result_text = (
        f"✅ <b>O'chirilgan akkauntlarni tozalash yakunlandi!</b>\n\n"
        f"🗑 <b>Chiqarib yuborilgan 'Deleted Account'lar:</b> <code>{deleted_count}</code> ta\n"
        f"👥 <b>Tekshirilgan a'zolar:</b> <code>{checked_count}</code> ta\n\n"
        f"💡 <i>Eslatma: Telegram qoidalariga ko'ra bot faqat o'zi ko'rgan va faol a'zolarni tekshira oladi.\n"
        f"Agar guruhda qadimdan qolgan o'chirilgan akkauntlar ko'p bo'lsa, ularni 100% tozalash uchun:\n"
        f"Guruh profili ➡️ Tahrirlash (✏️) ➡️ <b>A'zolar (Members)</b> ➡️ Qidiruvga <code>Deleted</code> deb yozib bir zumda o'chirishingiz mumkin.</i>"
    )

    try:
        await status_msg.edit_text(result_text, parse_mode="HTML")
    except Exception:
        await message.reply(result_text, parse_mode="HTML")

    if deleted_count > 0:
        await log_moderation(
            bot=bot,
            admin=message.from_user,
            target_user=User(id=0, is_bot=False, first_name="Deleted Accounts"),
            action="Clean Deleted",
            reason=f"{deleted_count} ta o'chirilgan akkaunt guruhdan chiqarildi"
        )

