import html
import logging
from typing import Optional, Tuple, List
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import MessageEntityType

from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="media_control")

# ==================== YORDAMCHI FOYDALANUVCHINI ANIQLASH ====================
async def resolve_target(message: Message, bot: Bot, tokens: List[str]) -> Tuple[Optional[int], str, Optional[str]]:
    """
    Reply, @username, text mention yoki ID orqali foydalanuvchini aniqlaydi.
    Qaytaradi: (target_id, target_name, target_username)
    """
    # 1. Reply qilingan bo'lsa
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        return u.id, u.full_name, u.username

    # 2. Text mention entity orqali
    for ent in (message.entities or []):
        if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
            return ent.user.id, ent.user.full_name, ent.user.username

    # 3. Agar tokens berilgan bo'lsa
    if tokens:
        first = tokens[0].strip()
        # @username
        if first.startswith("@"):
            uname = first.lstrip("@").lower()
            db_u = await db.get_user_by_username(uname)
            if db_u:
                return db_u["user_id"], db_u["full_name"], db_u["username"]
            try:
                chat = await bot.get_chat(first)
                return chat.id, chat.full_name or first, chat.username
            except Exception:
                return None, first, uname

        # Raqamli ID
        if first.lstrip("-").isdigit():
            uid = int(first)
            db_u = await db.get_user_by_id(uid)
            if db_u:
                return db_u["user_id"], db_u["full_name"], db_u["username"]
            return uid, f"ID: {uid}", None

    return None, "", None

# ==================== MATNLI BUYRUQLAR (ENABLE / DISABLE) ====================
TEXT_COMMANDS = {
    "enable stickers": ("stickers", True),
    "disable stickers": ("stickers", False),
    "enable sticker": ("stickers", True),
    "disable sticker": ("stickers", False),
    "enable gifs": ("gifs", True),
    "disable gifs": ("gifs", False),
    "enable gif": ("gifs", True),
    "disable gif": ("gifs", False),
    "enable animation": ("gifs", True),
    "disable animation": ("gifs", False),
}

@router.message(F.text.lower().in_(list(TEXT_COMMANDS.keys())), IsGroupFilter())
async def handle_text_media_toggle(message: Message, bot: Bot):
    """Adminlar uchun 'enable stickers' / 'disable stickers' kabi matnli buyruqlar."""
    if not await IsAdminFilter()(message, bot):
        return

    cmd = message.text.strip().lower()
    media_cat, enable = TEXT_COMMANDS[cmd]
    chat_id = message.chat.id

    if media_cat == "stickers":
        await db.set_chat_setting_bool(chat_id, "stickers_enabled", enable)
        if enable:
            text = (
                "🎭 <b>Stikerlar: YOQILDI ✅</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Endi guruhda barcha a'zolar stiker yuborishi mumkin."
            )
        else:
            text = (
                "🎭 <b>Stikerlar: O'CHIRILDI ❌</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Guruhda stiker yuborish butunlay taqiqlandi!\n"
                "⚠️ <i>Hatto adminlar ham tashlay olmaydi (faqat oq ro'yxatdagilardan tashqari).</i>"
            )
    else:
        await db.set_chat_setting_bool(chat_id, "gifs_enabled", enable)
        if enable:
            text = (
                "🎬 <b>GIFlar: YOQILDI ✅</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Endi guruhda barcha a'zolar GIF yuborishi mumkin."
            )
        else:
            text = (
                "🎬 <b>GIFlar: O'CHIRILDI ❌</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Guruhda GIF yuborish butunlay taqiqlandi!\n"
                "⚠️ <i>Hatto adminlar ham tashlay olmaydi (faqat oq ro'yxatdagilardan tashqari).</i>"
            )

    resp = await message.reply(text, parse_mode="HTML")
    auto_delete(message, delay=10)
    auto_delete(resp, delay=20)

# ==================== /STICKERS VA /GIFS BUYRUQLARI ====================
@router.message(Command("stickers", "sticker"), IsGroupFilter())
async def cmd_stickers(message: Message, bot: Bot):
    """Stikerlarni yoqish/o'chirish yoki holatini ko'rish."""
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    parts = message.text.split()
    if len(parts) > 1:
        arg = parts[1].lower()
        if arg in ["on", "enable", "yoq", "yoqish", "1"]:
            await db.set_chat_setting_bool(chat_id, "stickers_enabled", True)
            resp = await message.reply(
                "🎭 <b>Stikerlar: YOQILDI ✅</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Endi guruhda barcha a'zolar stiker yuborishi mumkin.",
                parse_mode="HTML"
            )
            auto_delete(message, delay=10)
            auto_delete(resp, delay=20)
            return
        elif arg in ["off", "disable", "och", "ochirish", "0"]:
            await db.set_chat_setting_bool(chat_id, "stickers_enabled", False)
            resp = await message.reply(
                "🎭 <b>Stikerlar: O'CHIRILDI ❌</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Guruhda stiker yuborish taqiqlandi!\n"
                "⚠️ <i>Hatto adminlar ham tashlay olmaydi (faqat oq ro'yxatdagilardan tashqari).</i>",
                parse_mode="HTML"
            )
            auto_delete(message, delay=10)
            auto_delete(resp, delay=20)
            return

    # Holat ma'lumotini chiqarish
    current = await db.get_chat_setting_bool(chat_id, "stickers_enabled", True)
    status_txt = "YOQILGAN ✅ (Erkin)" if current else "O'CHIRILGAN ❌ (Taqiqlangan)"
    whitelist = await db.get_media_whitelist(chat_id, "sticker")

    text = (
        f"🎭 <b>STIKERLAR SOZLAMASI:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ <b>Holat:</b> <code>{status_txt}</code>\n"
        f"⚪️ <b>Oq ro'yxatdagilar:</b> <code>{len(whitelist)} nafar</code>\n\n"
        f"💡 <b>Boshqarish buyruqlari:</b>\n"
        f"• <code>enable stickers</code> yoki <code>/stickers on</code> — Yoqish\n"
        f"• <code>disable stickers</code> yoki <code>/stickers off</code> — O'chirish\n"
        f"• <code>/stickerwhitelist add @user</code> — Oq ro'yxatga qo'shish\n"
        f"• <code>/stickerwhitelist del @user</code> — Oq ro'yxatdan o'chirish\n"
        f"• <code>/stickerwhitelist list</code> — Ro'yxatni ko'rish"
    )
    resp = await message.reply(text, parse_mode="HTML")
    auto_delete(message, delay=10)
    auto_delete(resp, delay=30)

@router.message(Command("gifs", "gif", "animation"), IsGroupFilter())
async def cmd_gifs(message: Message, bot: Bot):
    """GIFlarni yoqish/o'chirish yoki holatini ko'rish."""
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    parts = message.text.split()
    if len(parts) > 1:
        arg = parts[1].lower()
        if arg in ["on", "enable", "yoq", "yoqish", "1"]:
            await db.set_chat_setting_bool(chat_id, "gifs_enabled", True)
            resp = await message.reply(
                "🎬 <b>GIFlar: YOQILDI ✅</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Endi guruhda barcha a'zolar GIF yuborishi mumkin.",
                parse_mode="HTML"
            )
            auto_delete(message, delay=10)
            auto_delete(resp, delay=20)
            return
        elif arg in ["off", "disable", "och", "ochirish", "0"]:
            await db.set_chat_setting_bool(chat_id, "gifs_enabled", False)
            resp = await message.reply(
                "🎬 <b>GIFlar: O'CHIRILDI ❌</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Guruhda GIF yuborish taqiqlandi!\n"
                "⚠️ <i>Hatto adminlar ham tashlay olmaydi (faqat oq ro'yxatdagilardan tashqari).</i>",
                parse_mode="HTML"
            )
            auto_delete(message, delay=10)
            auto_delete(resp, delay=20)
            return

    # Holat ma'lumotini chiqarish
    current = await db.get_chat_setting_bool(chat_id, "gifs_enabled", True)
    status_txt = "YOQILGAN ✅ (Erkin)" if current else "O'CHIRILGAN ❌ (Taqiqlangan)"
    whitelist = await db.get_media_whitelist(chat_id, "gif")

    text = (
        f"🎬 <b>GIFLAR SOZLAMASI:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ <b>Holat:</b> <code>{status_txt}</code>\n"
        f"⚪️ <b>Oq ro'yxatdagilar:</b> <code>{len(whitelist)} nafar</code>\n\n"
        f"💡 <b>Boshqarish buyruqlari:</b>\n"
        f"• <code>enable gifs</code> yoki <code>/gifs on</code> — Yoqish\n"
        f"• <code>disable gifs</code> yoki <code>/gifs off</code> — O'chirish\n"
        f"• <code>/gifwhitelist add @user</code> — Oq ro'yxatga qo'shish\n"
        f"• <code>/gifwhitelist del @user</code> — Oq ro'yxatdan o'chirish\n"
        f"• <code>/gifwhitelist list</code> — Ro'yxatni ko'rish"
    )
    resp = await message.reply(text, parse_mode="HTML")
    auto_delete(message, delay=10)
    auto_delete(resp, delay=30)

# ==================== STIKER WHITELIST BUYRUQLARI ====================
@router.message(Command("stickerwhitelist", "swhitelist"), IsGroupFilter())
async def cmd_sticker_whitelist(message: Message, bot: Bot):
    """Stikerlar uchun oq ro'yxatni boshqarish."""
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    parts = message.text.split()
    action = parts[1].lower() if len(parts) > 1 else "list"
    tokens = parts[2:] if len(parts) > 2 else []

    if action in ["add", "qo'sh", "qosh"]:
        target_id, target_name, target_username = await resolve_target(message, bot, tokens)
        if not target_id:
            msg = await message.reply("⚠️ Foydalanuvchini ko'rsating: reply qiling, @username yoki ID yozing.")
            auto_delete(message, delay=10)
            auto_delete(msg, delay=15)
            return

        success = await db.add_to_media_whitelist(chat_id, "sticker", target_id, message.from_user.id)
        if success:
            u_link = f"<a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a>"
            msg = await message.reply(
                f"✅ {u_link} <b>Stikerlar oq ro'yxatiga (whitelist)</b> qo'shildi!\n\n"
                f"Endi u guruhda stikerlar o'chirilgan paytda ham stiker yubora oladi.",
                parse_mode="HTML"
            )
        else:
            msg = await message.reply("❌ Foydalanuvchini qo'shishda xatolik yuz berdi.")
        auto_delete(message, delay=10)
        auto_delete(msg, delay=20)
        return

    elif action in ["del", "delete", "remove", "rem", "ochir", "o'chir"]:
        target_id, target_name, target_username = await resolve_target(message, bot, tokens)
        if not target_id:
            msg = await message.reply("⚠️ Foydalanuvchini ko'rsating: reply qiling, @username yoki ID yozing.")
            auto_delete(message, delay=10)
            auto_delete(msg, delay=15)
            return

        success = await db.remove_from_media_whitelist(chat_id, "sticker", target_id)
        if success:
            u_link = f"<a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a>"
            msg = await message.reply(
                f"🗑 {u_link} stikerlar oq ro'yxatidan olib tashlandi.",
                parse_mode="HTML"
            )
        else:
            msg = await message.reply("❌ Olib tashlashda xatolik yuz berdi.")
        auto_delete(message, delay=10)
        auto_delete(msg, delay=20)
        return

    # list ko'rish
    whitelist = await db.get_media_whitelist(chat_id, "sticker")
    if not whitelist:
        msg = await message.reply(
            "ℹ️ <b>Stikerlar oq ro'yxati (whitelist) bo'sh.</b>\n\n"
            "💡 <i>Qo'shish uchun:</i> <code>/stickerwhitelist add @user</code> (yoki reply qiling)",
            parse_mode="HTML"
        )
    else:
        text = "⚪️ <b>STIKERLAR OQ RO'YXATI (WHITELIST):</b>\n━━━━━━━━━━━━━━━━━━\n"
        for idx, item in enumerate(whitelist, 1):
            name = item.get("full_name") or f"ID: {item['user_id']}"
            u_str = f"@{item['username']}" if item.get("username") else f"<code>{item['user_id']}</code>"
            text += f"{idx}. <a href=\"tg://user?id={item['user_id']}\">{html.escape(name)}</a> ({u_str})\n"
        text += (
            f"\n<i>Jami: {len(whitelist)} nafar a'zo stikerlar o'chirilgan bo'lsa ham stiker yubora oladi.</i>"
        )
        msg = await message.reply(text, parse_mode="HTML")

    auto_delete(message, delay=10)
    auto_delete(msg, delay=40)

# ==================== GIF WHITELIST BUYRUQLARI ====================
@router.message(Command("gifwhitelist", "gwhitelist"), IsGroupFilter())
async def cmd_gif_whitelist(message: Message, bot: Bot):
    """GIFlar uchun oq ro'yxatni boshqarish."""
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    parts = message.text.split()
    action = parts[1].lower() if len(parts) > 1 else "list"
    tokens = parts[2:] if len(parts) > 2 else []

    if action in ["add", "qo'sh", "qosh"]:
        target_id, target_name, target_username = await resolve_target(message, bot, tokens)
        if not target_id:
            msg = await message.reply("⚠️ Foydalanuvchini ko'rsating: reply qiling, @username yoki ID yozing.")
            auto_delete(message, delay=10)
            auto_delete(msg, delay=15)
            return

        success = await db.add_to_media_whitelist(chat_id, "gif", target_id, message.from_user.id)
        if success:
            u_link = f"<a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a>"
            msg = await message.reply(
                f"✅ {u_link} <b>GIFlar oq ro'yxatiga (whitelist)</b> qo'shildi!\n\n"
                f"Endi u guruhda GIFlar o'chirilgan paytda ham GIF yubora oladi.",
                parse_mode="HTML"
            )
        else:
            msg = await message.reply("❌ Foydalanuvchini qo'shishda xatolik yuz berdi.")
        auto_delete(message, delay=10)
        auto_delete(msg, delay=20)
        return

    elif action in ["del", "delete", "remove", "rem", "ochir", "o'chir"]:
        target_id, target_name, target_username = await resolve_target(message, bot, tokens)
        if not target_id:
            msg = await message.reply("⚠️ Foydalanuvchini ko'rsating: reply qiling, @username yoki ID yozing.")
            auto_delete(message, delay=10)
            auto_delete(msg, delay=15)
            return

        success = await db.remove_from_media_whitelist(chat_id, "gif", target_id)
        if success:
            u_link = f"<a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a>"
            msg = await message.reply(
                f"🗑 {u_link} GIFlar oq ro'yxatidan olib tashlandi.",
                parse_mode="HTML"
            )
        else:
            msg = await message.reply("❌ Olib tashlashda xatolik yuz berdi.")
        auto_delete(message, delay=10)
        auto_delete(msg, delay=20)
        return

    # list ko'rish
    whitelist = await db.get_media_whitelist(chat_id, "gif")
    if not whitelist:
        msg = await message.reply(
            "ℹ️ <b>GIFlar oq ro'yxati (whitelist) bo'sh.</b>\n\n"
            "💡 <i>Qo'shish uchun:</i> <code>/gifwhitelist add @user</code> (yoki reply qiling)",
            parse_mode="HTML"
        )
    else:
        text = "⚪️ <b>GIFLAR OQ RO'YXATI (WHITELIST):</b>\n━━━━━━━━━━━━━━━━━━\n"
        for idx, item in enumerate(whitelist, 1):
            name = item.get("full_name") or f"ID: {item['user_id']}"
            u_str = f"@{item['username']}" if item.get("username") else f"<code>{item['user_id']}</code>"
            text += f"{idx}. <a href=\"tg://user?id={item['user_id']}\">{html.escape(name)}</a> ({u_str})\n"
        text += (
            f"\n<i>Jami: {len(whitelist)} nafar a'zo GIFlar o'chirilgan bo'lsa ham GIF yubora oladi.</i>"
        )
        msg = await message.reply(text, parse_mode="HTML")

    auto_delete(message, delay=10)
    auto_delete(msg, delay=40)

# ==================== UNIFIED /WHITELIST BUYRUG'I ====================
@router.message(Command("whitelist"), IsGroupFilter())
async def cmd_unified_whitelist(message: Message, bot: Bot):
    """Stiker va GIF whitelist larini umumiy ko'rish va boshqarish."""
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    parts = message.text.split()
    if len(parts) > 1 and parts[1].lower() in ["sticker", "stickers"]:
        message.text = f"/stickerwhitelist {' '.join(parts[2:])}".strip()
        await cmd_sticker_whitelist(message, bot)
        return
    elif len(parts) > 1 and parts[1].lower() in ["gif", "gifs", "animation"]:
        message.text = f"/gifwhitelist {' '.join(parts[2:])}".strip()
        await cmd_gif_whitelist(message, bot)
        return

    # Ikkala ro'yxatni ham chiqarish
    s_list = await db.get_media_whitelist(chat_id, "sticker")
    g_list = await db.get_media_whitelist(chat_id, "gif")

    text = (
        f"⚪️ <b>GURUH OQ RO'YXATLARI (WHITELISTS):</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🎭 <b>Stikerlar Oq Ro'yxati:</b> <code>{len(s_list)} nafar</code>\n"
        f"🎬 <b>GIFlar Oq Ro'yxati:</b> <code>{len(g_list)} nafar</code>\n\n"
        f"💡 <b>Boshqarish:</b>\n"
        f"• <code>/stickerwhitelist list</code> — Stiker ruxsatlari\n"
        f"• <code>/stickerwhitelist add @user</code> — Stikerga ruxsat berish\n"
        f"• <code>/gifwhitelist list</code> — GIF ruxsatlari\n"
        f"• <code>/gifwhitelist add @user</code> — GIFga ruxsat berish"
    )
    msg = await message.reply(text, parse_mode="HTML")
    auto_delete(message, delay=10)
    auto_delete(msg, delay=40)
