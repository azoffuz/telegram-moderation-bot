import html
import logging
from typing import Optional, List, Dict, Any

from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.cleaner import auto_delete
from bot.services.logger import send_log
from bot.services.active_tag import (
    grant_active_tag,
    revoke_active_tag,
    revoke_all_chat_tags,
    get_chat_today_date_str,
    get_chat_current_month_str,
    get_tier_info,
    get_next_tier_info,
    reward_monthly_top_chatters,
    clear_active_tag_caches,
    ACTIVITY_TIERS
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
        if arg.isdigit():
            user_id = int(arg)
            known = await db.get_known_user(user_id)
            if known:
                return user_id, known.get("full_name") or f"ID: {user_id}", known.get("username")
            return user_id, f"ID: {user_id}", None
        if arg.startswith("@"):
            uname = arg[1:].lower()
            known = await db.get_user_by_username(uname)
            if known:
                return known["user_id"], known.get("full_name") or arg, known.get("username")
    return None

def build_leaderboard_keyboard(active_mode: str = "daily") -> InlineKeyboardMarkup:
    """Kunlik va Oylik statistika o'rtasida almashtiruvchi inline tugmalar."""
    daily_label = "✅ 📅 Bugun" if active_mode == "daily" else "📅 Bugun"
    monthly_label = "✅ 🗓 Shu Oy" if active_mode == "monthly" else "🗓 Shu Oy"
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=daily_label, callback_data="act_board:daily"),
            InlineKeyboardButton(text=monthly_label, callback_data="act_board:monthly")
        ]]
    )

async def format_daily_leaderboard(chat_id: int, date_str: str) -> str:
    """Bugungi reyting matnini tayyorlaydi."""
    leaders = await db.get_daily_activity_leaderboard(chat_id, date_str, limit=10)
    if not leaders:
        return (
            f"🏆 <b>BUGUNGI FOALLIK RO'YXATI ({date_str})</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Bugun hali hech kim xabar yozmadi.\n\n"
            f"💡 <i>Har kuni 10 ta xabar yozgan a'zolarga avtomatik «Active» tegi beriladi!</i>"
        )

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
        tier_title, tier_emoji = get_tier_info(cnt)
        tag_status = f" {tier_emoji} <b>[{tier_title}]</b>" if tier_title else ""
        lines.append(f"{badge} {u_link} — <b>{cnt} ta</b> xabar{tag_status}")

    lines.append(
        f"\n🎯 <b>Darajalar (Tiers):</b>\n"
        f"🥉 10: <code>Active</code> | 🥈 30: <code>Active+</code>\n"
        f"🥇 70: <code>Master</code> | 💎 150+: <code>Legend</code>"
    )
    return "\n".join(lines)

async def format_monthly_leaderboard(chat_id: int, month_str: str) -> str:
    """Oylik reyting matnini tayyorlaydi."""
    leaders = await db.get_monthly_activity_leaderboard(chat_id, month_str, limit=10)
    if not leaders:
        return (
            f"🗓 <b>OYLIK FOALLIK RO'YXATI ({month_str})</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Bu oy hali yetarli xabarlar mavjud emas."
        )

    lines = [
        f"🗓 <b>SHU OYLIK ENG FAOL A'ZOLAR ({month_str})</b>",
        f"━━━━━━━━━━━━━━━━━━"
    ]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for idx, item in enumerate(leaders):
        badge = medals[idx] if idx < len(medals) else f"#{idx+1}"
        u_name = html.escape(item["full_name"])
        u_link = f"<a href=\"tg://user?id={item['user_id']}\">{u_name}</a>"
        cnt = item["message_count"]
        crown = " 👑 <b>[Top #1]</b>" if idx == 0 else (" 💎 <b>[Top #2]</b>" if idx == 1 else (" 🥇 <b>[Top #3]</b>" if idx == 2 else ""))
        lines.append(f"{badge} {u_link} — <b>{cnt} ta</b> xabar{crown}")

    lines.append(
        f"\n👑 <i>Oy yakunida eng ko'p yozgan Top-3 a'zoga maxsus «Top Chatter», «Legend» va «Master» unvonlari beriladi!</i>"
    )
    return "\n".join(lines)

@router.message(Command("giveactive"), IsGroupFilter())
async def cmd_give_active(message: Message, bot: Bot):
    """Admin tomonidan a'zoga qo'lda teg berish."""
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
            "• Yoki maxsus unvon bilan: <code>/giveactive @username Master</code>",
            parse_mode="HTML"
        )
        auto_delete(message, delay=10)
        auto_delete(msg, delay=15)
        return

    target_id, target_name, target_username = target_info

    # Unvon nomini aniqlash (sukut bo'yicha 'Active')
    parts = message.text.split()
    custom_title = "Active"
    if len(parts) >= 3 and not parts[1].isdigit() and not parts[1].startswith("@"):
        custom_title = parts[2]
    elif len(parts) >= 2 and not parts[1].isdigit() and not parts[1].startswith("@"):
        custom_title = parts[1]

    bot_info = await bot.get_me()
    if target_id == bot_info.id:
        msg = await message.reply("🤖 Botga teg berish shart emas.", parse_mode="HTML")
        auto_delete(msg, delay=10)
        return

    success, result_msg = await grant_active_tag(bot, chat_id, target_id, custom_title)
    if success:
        gmt_offset = await db.get_gmt_offset(chat_id)
        date_str = get_chat_today_date_str(gmt_offset)
        await db.mark_active_granted(chat_id, target_id, date_str)

        text = (
            f"🎖 <a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a> ga "
            f"muvaffaqiyatli <b>«{custom_title}»</b> tegi berildi!\n"
            f"👮‍♂️ <b>Admin:</b> {html.escape(message.from_user.full_name)}"
        )
        sent = await message.reply(text, parse_mode="HTML")
        auto_delete(message, delay=15)
        auto_delete(sent, delay=30)

        log_text = (
            f"🎖 <b>ADMIN TOMONIDAN TEG BERILDI</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>A'zo:</b> <a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a>\n"
            f"🆔 <b>ID:</b> <code>{target_id}</code>\n"
            f"🏆 <b>Teg:</b> «{custom_title}»\n"
            f"👮‍♂️ <b>Admin:</b> <a href=\"tg://user?id={message.from_user.id}\">{html.escape(message.from_user.full_name)}</a>"
        )
        await send_log(bot, log_text, category="members")
    else:
        sent = await message.reply(f"❌ <b>Xatolik:</b> {result_msg}", parse_mode="HTML")
        auto_delete(message, delay=15)
        auto_delete(sent, delay=20)

@router.message(Command("removeactive", "takeactive"), IsGroupFilter())
async def cmd_remove_active(message: Message, bot: Bot):
    """Admin tomonidan a'zodan tegni olib tashlash."""
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
            f"faollik tegi olib tashlandi.\n"
            f"👮‍♂️ <b>Admin:</b> {html.escape(message.from_user.full_name)}"
        )
        sent = await message.reply(text, parse_mode="HTML")
        auto_delete(message, delay=15)
        auto_delete(sent, delay=30)
    else:
        sent = await message.reply(f"❌ <b>Xatolik:</b> {result_msg}", parse_mode="HTML")
        auto_delete(message, delay=15)
        auto_delete(sent, delay=20)

@router.message(Command("active", "activestat", "top", "topactive"), IsGroupFilter())
async def cmd_active_stats(message: Message, bot: Bot):
    """Kunlik va oylik faollar reytingini ko'rish yoki admin tomonidan yoqish/o'chirish."""
    chat_id = message.chat.id
    parts = message.text.split()
    gmt_offset = await db.get_gmt_offset(chat_id)

    # 1. Admin tomonidan tizimni yoqish / o'chirish tekshiruvi:
    # Masalan: /active on, /active off, /active yoqish, /active ochirish
    if len(parts) > 1 and parts[1].lower() in ["on", "enable", "yoq", "yoqish", "och", "off", "disable", "ochirish"]:
        if not await IsAdminFilter()(message, bot):
            try:
                await message.delete()
            except Exception:
                pass
            return

        turn_on = parts[1].lower() in ["on", "enable", "yoq", "yoqish"]
        await db.set_chat_setting_bool(chat_id, "active_tag_enabled", turn_on)
        status_text = "yoqildi ✅" if turn_on else "o'chirildi ❌"
        resp = await message.reply(
            f"🎖 <b>Faollik va Darajalar (Active Tag) tizimi</b> guruhda <b>{status_text}</b>!",
            parse_mode="HTML"
        )
        auto_delete(message, delay=10)
        auto_delete(resp, delay=15)
        return

    # 2. Agar tizim o'chiq bo'lsa va admin bo'lmasa, ma'lumot beramiz
    settings = await db.get_all_chat_settings(chat_id)
    if not settings.get("active_tag_enabled", True):
        resp = await message.reply(
            "ℹ️ <i>Guruhda faollik va Active tegi tizimi admin tomonidan vaqtincha o'chirilgan.</i>\n\n"
            "💡 <i>Uni qayta yoqish uchun:</i> <code>/active on</code>",
            parse_mode="HTML"
        )
        auto_delete(message, delay=10)
        auto_delete(resp, delay=20)
        return

    # 3. Agar '/active month' yoki '/topmonth' yozilgan bo'lsa
    if (len(parts) > 1 and parts[1].lower() in ["month", "oy", "oylik"]) or "month" in parts[0].lower():
        month_str = get_chat_current_month_str(gmt_offset)
        text = await format_monthly_leaderboard(chat_id, month_str)
        kb = build_leaderboard_keyboard("monthly")
    else:
        date_str = get_chat_today_date_str(gmt_offset)
        text = await format_daily_leaderboard(chat_id, date_str)
        kb = build_leaderboard_keyboard("daily")

    sent = await message.reply(text, reply_markup=kb, parse_mode="HTML")
    auto_delete(message, delay=20)
    auto_delete(sent, delay=90)

@router.callback_query(F.data.startswith("act_board:"), IsGroupFilter())
async def callback_toggle_leaderboard(call: CallbackQuery, bot: Bot):
    """Kunlik va oylik reyting tugmasi bosilganda almashtirish."""
    chat_id = call.message.chat.id
    mode = call.data.split(":")[1]
    gmt_offset = await db.get_gmt_offset(chat_id)

    if mode == "monthly":
        month_str = get_chat_current_month_str(gmt_offset)
        text = await format_monthly_leaderboard(chat_id, month_str)
    else:
        date_str = get_chat_today_date_str(gmt_offset)
        text = await format_daily_leaderboard(chat_id, date_str)

    kb = build_leaderboard_keyboard(mode)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()

@router.message(Command("selfstats", "mystats", "stat", "mystat"), IsGroupFilter())
async def cmd_self_stats(message: Message, bot: Bot):
    """Foydalanuvchining shaxsiy ko'rsatkichlari (Bugungi va oylik xabarlari, unvoni, reytingi)."""
    chat_id = message.chat.id
    user = message.from_user
    gmt_offset = await db.get_gmt_offset(chat_id)
    today_str = get_chat_today_date_str(gmt_offset)
    month_str = get_chat_current_month_str(gmt_offset)

    stats = await db.get_user_activity_stats(chat_id, user.id, today_str, month_str)
    t_cnt = stats["today_messages"]
    m_cnt = stats["month_messages"]

    # Joriy daraja va keyingi daraja
    curr_tier, curr_emoji = get_tier_info(t_cnt)
    next_info = get_next_tier_info(t_cnt)

    curr_badge = f"{curr_emoji} <b>«{curr_tier}»</b>" if curr_tier else "<i>Unvon yo'q</i>"
    if next_info:
        req, n_title, n_emoji, remain = next_info
        progress_text = f"{n_emoji} <b>«{n_title}»</b> uchun yana <b>{remain} ta</b> xabar"
    else:
        progress_text = "💎 <b>Maksimal darajaga (Legend) erishilgan!</b>"

    t_rank = f"(Guruhda #{stats['today_rank']}-o'rin)" if stats["today_rank"] else ""
    m_rank = f"(Guruhda #{stats['month_rank']}-o'rin)" if stats["month_rank"] else ""

    text = (
        f"👤 <b>SHAXSIY FAOLLIK KO'RSATKICHLARI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{html.escape(user.full_name)}</a>\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n\n"
        f"📊 <b>Bugun:</b> <code>{t_cnt} ta</code> xabar {t_rank}\n"
        f"🏆 <b>Joriy Daraja:</b> {curr_badge}\n"
        f"🎯 <b>Keyingi marra:</b> {progress_text}\n\n"
        f"🗓 <b>Shu oylik jami:</b> <code>{m_cnt} ta</code> xabar {m_rank}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Guruhda faol bo'ling va yuqori darajalarga ko'tariling!</i>"
    )

    sent = await message.reply(text, parse_mode="HTML")
    auto_delete(message, delay=15)
    auto_delete(sent, delay=60)

@router.message(Command("rewardmonth"), IsGroupFilter())
async def cmd_reward_month(message: Message, bot: Bot):
    """Admin tomonidan oylik Top-3 g'oliblarga unvon topshirish."""
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    gmt_offset = await db.get_gmt_offset(chat_id)
    month_str = get_chat_current_month_str(gmt_offset)

    results = await reward_monthly_top_chatters(bot, chat_id, month_str)
    if not results:
        msg = await message.reply(f"ℹ️ {month_str} oyi uchun yetarli xabarlar topilmadi.", parse_mode="HTML")
        auto_delete(msg, delay=15)
        return

    lines = [
        f"🏆 <b>{month_str} OYI YAKUNI BO'YICHA G'OLIBLAR TAQDIRLANDI!</b>",
        f"━━━━━━━━━━━━━━━━━━"
    ]
    for r in results:
        u_link = f"<a href=\"tg://user?id={r['user_id']}\">{html.escape(r['full_name'])}</a>"
        status = "✅" if r["success"] else "⚠️"
        lines.append(f"{status} #{r['rank']} {u_link} — {r['messages']} ta xabar ➔ {r['emoji']} <b>«{r['title']}»</b>")

    lines.append(f"\n🎉 <i>Barcha g'oliblarni tabriklaymiz! Ular butun oy davomida ushbu unvonlar bilan yurishadi.</i>")
    text = "\n".join(lines)

    sent = await message.reply(text, parse_mode="HTML")
    auto_delete(message, delay=20)
    auto_delete(sent, delay=120)

    await send_log(
        bot,
        f"🏆 <b>OYLIK G'OLIBLAR TAQDIRLANDI ({month_str})</b>\n"
        f"Admin: {html.escape(message.from_user.full_name)}\n"
        f"Guruh: {message.chat.title}",
        category="members"
    )

# ==================== STATISTIKANI TOZALASH (RESET / CLEAR) ====================
@router.message(Command("resetactive", "clearactive", "reset_active", "clear_active"), IsGroupFilter())
async def cmd_reset_active(message: Message, bot: Bot):
    """Faollik statistikasini tozalash (Faqat adminlar uchun)."""
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    gmt_offset = await db.get_gmt_offset(chat_id)
    today_str = get_chat_today_date_str(gmt_offset)
    month_str = get_chat_current_month_str(gmt_offset)

    # 1. Muayyan foydalanuvchini tozalash (reply yoki @username / ID orqali)
    target_info = await extract_target_user(message, bot)
    if target_info:
        target_id, target_name, target_username = target_info
        deleted = await db.clear_activity_stats(chat_id, user_id=target_id)
        clear_active_tag_caches(chat_id)
        u_link = f"<a href=\"tg://user?id={target_id}\">{html.escape(target_name)}</a>"
        resp = await message.reply(
            f"🗑 {u_link} ning barcha faollik statistikasi tozalandi! ({deleted} ta yozuv o'chirildi)",
            parse_mode="HTML"
        )
        auto_delete(message, delay=10)
        auto_delete(resp, delay=20)
        return

    # 2. Argumentlar bo'yicha tozalash: today, month, all
    parts = message.text.split()
    if len(parts) > 1:
        arg = parts[1].lower()
        if arg in ["today", "bugun", "kun"]:
            deleted = await db.clear_activity_stats(chat_id, date_str=today_str)
            clear_active_tag_caches(chat_id)
            resp = await message.reply(
                f"📅 <b>Bugungi ({today_str}) barcha faollik statistikasi tozalandi!</b> ({deleted} ta yozuv o'chirildi)",
                parse_mode="HTML"
            )
            auto_delete(message, delay=10)
            auto_delete(resp, delay=20)
            return
        elif arg in ["month", "oy", "oylik"]:
            deleted = await db.clear_activity_stats(chat_id, month_str=month_str)
            clear_active_tag_caches(chat_id)
            resp = await message.reply(
                f"🗓 <b>Joriy ({month_str}) oylik barcha faollik statistikasi tozalandi!</b> ({deleted} ta yozuv o'chirildi)",
                parse_mode="HTML"
            )
            auto_delete(message, delay=10)
            auto_delete(resp, delay=20)
            return
        elif arg in ["all", "hamma", "barchasi", "toza"]:
            deleted = await db.clear_activity_stats(chat_id)
            clear_active_tag_caches(chat_id)
            resp = await message.reply(
                f"💥 <b>Guruhdagi butun faollik tarixi to'liq tozalandi!</b> ({deleted} ta yozuv o'chirildi)",
                parse_mode="HTML"
            )
            auto_delete(message, delay=10)
            auto_delete(resp, delay=20)
            return
        elif arg in ["tags", "teglar", "teglarni", "tag"]:
            wait_msg = await message.reply("⏳ <b>Barcha a'zolardan teglar olib tashlanmoqda, iltimos kuting...</b>", parse_mode="HTML")
            s_cnt, f_cnt = await revoke_all_chat_tags(bot, chat_id)
            text = (
                f"🧹 <b>Barcha a'zolardan teglar tozalandi!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>Olib tashlandi:</b> {s_cnt} nafar a'zodan\n"
                f"👤 <b>Admin:</b> {html.escape(message.from_user.full_name)}"
            )
            await wait_msg.edit_text(text, parse_mode="HTML")
            auto_delete(message, delay=10)
            auto_delete(wait_msg, delay=40)
            return

    # 3. Agar parametr ko'rsatilmagan bo'lsa: Interaktiv boshqaruv tugmalari
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"📅 Bugunni tozalash ({today_str})", callback_data="reset_act:today")
            ],
            [
                InlineKeyboardButton(text=f"🗓 Shu oyni tozalash ({month_str})", callback_data="reset_act:month")
            ],
            [
                InlineKeyboardButton(text="💥 Barchasini to'liq tozalash", callback_data="reset_act:all")
            ],
            [
                InlineKeyboardButton(text="🏷 Barcha teglarni olib tashlash (Clear Tags)", callback_data="reset_act:tags")
            ],
            [
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="reset_act:cancel")
            ]
        ]
    )
    resp = await message.reply(
        "🗑 <b>FAOLLIK VA TEGLARNI TOZALASH</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Qaysi ma'lumotlarni tozalamoqchisiz?\n\n"
        "• <b>Bugunni tozalash:</b> Faqat bugungi xabarlar hisobini 0 ga tushiradi.\n"
        "• <b>Shu oyni tozalash:</b> Joriy oylik reytingni tozalaydi.\n"
        "• <b>Barchasini tozalash:</b> Butun guruh arxivini o'chiradi.\n"
        "• <b>Teglarni olib tashlash:</b> Barcha a'zolarning Telegramdagi teglarini olib tashlaydi.\n\n"
        "💡 <i>Tezkor buyruqlar:</i>\n"
        "<code>/cleartags</code> — barcha teglarni darhol tozalash\n"
        "<code>/resetactive today</code> | <code>/resetactive all</code> | <code>/resetactive @username</code>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    auto_delete(message, delay=20)
    auto_delete(resp, delay=60)

@router.message(Command("cleartags", "clear_tags", "resettags", "reset_tags", "cleartag"), IsGroupFilter())
async def cmd_clear_tags(message: Message, bot: Bot):
    """Guruhdagi barcha a'zolardan berilgan teglarni to'liq olib tashlash."""
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    wait_msg = await message.reply("⏳ <b>Barcha a'zolardan teglar olib tashlanmoqda, iltimos kuting...</b>", parse_mode="HTML")
    s_cnt, f_cnt = await revoke_all_chat_tags(bot, chat_id)

    text = (
        f"🧹 <b>BARCHA TEGLAR TOZALANDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Olib tashlandi:</b> {s_cnt} nafar a'zodan\n"
        f"👤 <b>Admin:</b> {html.escape(message.from_user.full_name)}\n"
        f"⚡️ <i>Guruh a'zolari oddiy holatga qaytarildi.</i>"
    )
    await wait_msg.edit_text(text, parse_mode="HTML")
    auto_delete(message, delay=10)
    auto_delete(wait_msg, delay=60)

    await send_log(
        bot,
        f"🏷 <b>BARCHA TEGLAR TOZALANDI</b>\n"
        f"Admin: {html.escape(message.from_user.full_name)}\n"
        f"Guruh: {message.chat.title}\n"
        f"Muvaffaqiyatli: {s_cnt} ta",
        category="members"
    )

@router.callback_query(F.data.startswith("reset_act:"), IsGroupFilter())
async def cb_reset_activity_action(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    from bot.filters.admin import is_user_admin
    if not await is_user_admin(bot, chat_id, callback.from_user.id):
        await callback.answer("❌ Bu amal faqat adminlar uchun!", show_alert=True)
        return

    action = callback.data.split(":")[1]
    gmt_offset = await db.get_gmt_offset(chat_id)
    today_str = get_chat_today_date_str(gmt_offset)
    month_str = get_chat_current_month_str(gmt_offset)

    if action == "cancel":
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer("Bekor qilindi.")
        return

    deleted = 0
    title = ""
    if action == "today":
        deleted = await db.clear_activity_stats(chat_id, date_str=today_str)
        title = f"📅 <b>Bugungi ({today_str}) faollik statistikasi tozalandi!</b>"
    elif action == "month":
        deleted = await db.clear_activity_stats(chat_id, month_str=month_str)
        title = f"🗓 <b>Joriy ({month_str}) oylik faollik statistikasi tozalandi!</b>"
    elif action == "all":
        deleted = await db.clear_activity_stats(chat_id)
        title = "💥 <b>Barcha faollik tarixi to'liq tozalandi!</b>"
    elif action == "tags":
        try:
            await callback.message.edit_text("⏳ <b>Teglar olib tashlanmoqda...</b>", parse_mode="HTML")
        except Exception:
            pass
        s_cnt, f_cnt = await revoke_all_chat_tags(bot, chat_id)
        text = (
            f"🧹 <b>BARCHA TEGLAR TOZALANDI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Olib tashlandi:</b> {s_cnt} nafar a'zodan\n"
            f"👤 <b>Admin:</b> {html.escape(callback.from_user.full_name)}"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML")
        except Exception:
            pass
        await callback.answer(f"✅ {s_cnt} nafar a'zodan teglar tozalandi!")
        return

    clear_active_tag_caches(chat_id)
    text = (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Admin:</b> {html.escape(callback.from_user.full_name)}\n"
        f"🗑 <b>O'chirilgan yozuvlar:</b> {deleted} ta"
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("Muvaffaqiyatli tozalandi!")

