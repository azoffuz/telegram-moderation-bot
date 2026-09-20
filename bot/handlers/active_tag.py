import html
import logging
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message

from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.cleaner import auto_delete
from bot.services.logger import send_log
from bot.services.active_tag import (
    grant_active_tag,
    revoke_active_tag,
    get_chat_today_date_str
)

logger = logging.getLogger(__name__)
router = Router(name="active_tag_commands")

async def extract_target_user(message: Message, bot: Bot) -> Optional[tuple]:
    """
    Xabarga reply qilingan foydalanuvchini yoki parametr orqali yuborilgan (@username / ID) ni aniqlaydi.
    Qaytaradi: (user_id, full_name, username) yoki None
    """
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        return target.id, target.full_name, target.username

    parts = message.text.split()
    if len(parts) > 1:
        arg = parts[1].strip()
        # Agar user_id kiritilgan bo'lsa
        if arg.isdigit():
            user_id = int(arg)
            known = await db.get_known_user(user_id)
            if known:
                return user_id, known.get("full_name") or f"ID: {user_id}", known.get("username")
            return user_id, f"ID: {user_id}", None
        # Agar @username kiritilgan bo'lsa
        if arg.startswith("@"):
            uname = arg[1:].lower()
            known = await db.get_user_by_username(uname)
            if known:
                return known["user_id"], known.get("full_name") or arg, known.get("username")
    return None

@router.message(Command("giveactive"), IsGroupFilter())
async def cmd_give_active(message: Message, bot: Bot):
    """Admin tomonidan a'zoga qo'lda 'Active' unvonini berish."""
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    target_info = await extract_target_user(message, bot)

    if not target_info:
        msg = await message.reply(
            "ℹ️ <b>Foydalanish:</b>\n"
            "• Foydalanuvchi xabariga reply qilib: <code>/giveactive</code>\n"
            "• Yoki: <code>/giveactive @username</code> yoki <code>/giveactive ID</code>",
            parse_mode="HTML"
        )
        auto_delete(message, delay=10)
        auto_delete(msg, delay=15)
        return

    target_id, target_name, target_username = target_info

    # Botga yoki o'ziga berishni oldini olish
    bot_info = await bot.get_me()
    if target_id == bot_info.id:
        msg = await message.reply("🤖 Botga unvon berish shart emas.", parse_mode="HTML")
        auto_delete(msg, delay=10)
        return

    success, result_msg = await grant_active_tag(bot, chat_id, target_id, "Active")
    if success:
        # Bazada ham qayd etamiz
        gmt_offset = await db.get_gmt_offset(chat_id)
        date_str = get_chat_today_date_str(gmt_offset)
        await db.mark_active_granted(chat_id, target_id, date_str)

        text = (
            f"🎖 <a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a> ga "
            f"muvaffaqiyatli <b>«Active»</b> unvoni (tag) berildi!\n"
            f"👤 <b>Admin:</b> {html.escape(message.from_user.full_name)}"
        )
        sent = await message.reply(text, parse_mode="HTML")
        auto_delete(message, delay=15)
        auto_delete(sent, delay=30)

        log_text = (
            f"🎖 <b>ADMIN TOMONIDAN «ACTIVE» UNVONI BERILDI</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>A'zo:</b> <a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a>\n"
            f"🆔 <b>ID:</b> <code>{target_id}</code>\n"
            f"👮‍♂️ <b>Admin:</b> <a href=\"tg://user?id={message.from_user.id}\">{html.escape(message.from_user.full_name)}</a>"
        )
        await send_log(bot, log_text, category="members")
    else:
        sent = await message.reply(f"❌ <b>Xatolik:</b> {result_msg}", parse_mode="HTML")
        auto_delete(message, delay=15)
        auto_delete(sent, delay=20)

@router.message(Command("removeactive", "takeactive"), IsGroupFilter())
async def cmd_remove_active(message: Message, bot: Bot):
    """Admin tomonidan a'zodan 'Active' unvonini qaytarib olish."""
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    target_info = await extract_target_user(message, bot)

    if not target_info:
        msg = await message.reply(
            "ℹ️ <b>Foydalanish:</b>\n"
            "• Foydalanuvchi xabariga reply qilib: <code>/removeactive</code>\n"
            "• Yoki: <code>/removeactive @username</code> yoki <code>/removeactive ID</code>",
            parse_mode="HTML"
        )
        auto_delete(message, delay=10)
        auto_delete(msg, delay=15)
        return

    target_id, target_name, target_username = target_info

    success, result_msg = await revoke_active_tag(bot, chat_id, target_id)
    if success:
        text = (
            f"ℹ️ <a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a> dan "
            f"<b>«Active»</b> unvoni olib tashlandi va oddiy a'zo holatiga qaytarildi.\n"
            f"👮‍♂️ <b>Admin:</b> {html.escape(message.from_user.full_name)}"
        )
        sent = await message.reply(text, parse_mode="HTML")
        auto_delete(message, delay=15)
        auto_delete(sent, delay=30)

        log_text = (
            f"⚠️ <b>«ACTIVE» UNVONI BEKOR QILINDI</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>A'zo:</b> <a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a>\n"
            f"🆔 <b>ID:</b> <code>{target_id}</code>\n"
            f"👮‍♂️ <b>Admin:</b> <a href=\"tg://user?id={message.from_user.id}\">{html.escape(message.from_user.full_name)}</a>"
        )
        await send_log(bot, log_text, category="members")
    else:
        sent = await message.reply(f"❌ <b>Xatolik:</b> {result_msg}", parse_mode="HTML")
        auto_delete(message, delay=15)
        auto_delete(sent, delay=20)

@router.message(Command("active", "activestat", "topactive"), IsGroupFilter())
async def cmd_active_stats(message: Message, bot: Bot):
    """Bugungi kunlik eng faol a'zolar reytingini ko'rish."""
    chat_id = message.chat.id
    gmt_offset = await db.get_gmt_offset(chat_id)
    date_str = get_chat_today_date_str(gmt_offset)

    leaders = await db.get_daily_activity_leaderboard(chat_id, date_str, limit=10)

    settings = await db.get_all_chat_settings(chat_id)
    threshold = int(settings.get("active_tag_threshold", 10))

    if not leaders:
        text = (
            f"🏆 <b>BUGUNGI FOALLIK RO'YXATI ({date_str})</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Bugun hali hech kim xabar yozmadi.\n\n"
            f"💡 <i>Guruhda kuniga kamida <b>{threshold} ta</b> xabar yozganlarga bot avtomatik ravishda «Active» unvonini beradi!</i>"
        )
    else:
        lines = [
            f"🏆 <b>BUGUNGI ENG FAOL A'ZOLAR ({date_str})</b>",
            f"━━━━━━━━━━━━━━━━━━"
        ]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for idx, item in enumerate(leaders):
            badge = medals[idx] if idx < len(medals) else f"#{idx+1}"
            u_name = html.escape(item["full_name"])
            u_link = f"<a href=\"tg://user?id={item['user_id']}\">{u_name}</a>"
            cnt = item["message_count"]
            tag_status = " 🎖 <b>[Active]</b>" if item["is_active_granted"] else ""

            if not item["is_active_granted"] and cnt < threshold:
                remain = threshold - cnt
                lines.append(f"{badge} {u_link} — <b>{cnt} ta</b> xabar (Active uchun yana {remain} ta)")
            else:
                lines.append(f"{badge} {u_link} — <b>{cnt} ta</b> xabar{tag_status}")

        lines.append(f"\n💡 <i>Har kuni <b>{threshold} ta</b> xabar yozgan a'zolarga avtomatik «Active» unvoni beriladi!</i>")
        text = "\n".join(lines)

    sent = await message.reply(text, parse_mode="HTML")
    auto_delete(message, delay=20)
    auto_delete(sent, delay=60)
