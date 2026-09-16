import logging
from datetime import datetime
from typing import Optional
from aiogram import Router, Bot, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPermissions
)
from bot.config import config
from bot.database import db
from bot.filters.admin import IsOwnerFilter, IsBotAdminFilter
from bot.services.logger import send_log, log_night_mode
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="admin_panel")

def get_group_target_id() -> int:
    """Sozlamalar saqlanadigan asosiy guruh ID sini oladi."""
    return config.GROUP_ID or 0

# ==================== KLAWIATURALAR ====================
def main_panel_keyboard() -> InlineKeyboardMarkup:
    """Asosiy admin panel boshqaruv menyusi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚙️ Guruh Himoya Qatlamlari", callback_data="panel:settings")
            ],
            [
                InlineKeyboardButton(text="⏱ Vaqt & Muddat Sozlamalari", callback_data="panel:time_settings")
            ],
            [
                InlineKeyboardButton(text="📝 Taqiqlangan So'zlar", callback_data="panel:badwords:page:1"),
                InlineKeyboardButton(text="👥 Bot Adminlari", callback_data="panel:admins")
            ],
            [
                InlineKeyboardButton(text="📊 Jonli Hisobot", callback_data="panel:today_report"),
                InlineKeyboardButton(text="📖 Buyruqlar Qo'llanmasi", callback_data="panel:commands_guide")
            ],
            [
                InlineKeyboardButton(text="📢 Guruhga E'lon Yuborish", callback_data="panel:broadcast")
            ],
            [
                InlineKeyboardButton(text="🔄 Yangilash", callback_data="panel:main")
            ]
        ]
    )

async def settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Guruh sozlamalarini bitta tugma bilan yoqish/o'chirish menyusi."""
    settings = await db.get_all_chat_settings(chat_id)

    def status_icon(val: bool) -> str:
        return "✅ YOQILGAN" if val else "❌ O'CHIK"

    def night_icon(val: bool) -> str:
        return "🌙 YOQILGAN (Yopiq)" if val else "☀️ O'CHIK (Ochiq)"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🛡 Captcha: {status_icon(settings.get('captcha_enabled', True))}",
                    callback_data="toggle:captcha_enabled"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔗 Anti-Link: {status_icon(settings.get('anti_link', True))}",
                    callback_data="toggle:anti_link"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔀 Anti-Forward: {status_icon(settings.get('anti_forward', True))}",
                    callback_data="toggle:anti_forward"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⚡️ Anti-Flood: {status_icon(settings.get('anti_flood', True))}",
                    callback_data="toggle:anti_flood"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🚫 Taqiqlangan So'zlar: {status_icon(settings.get('anti_badwords', True))}",
                    callback_data="toggle:anti_badwords"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🛑 Arab/Fors Spam: {status_icon(settings.get('anti_arabic', True))}",
                    callback_data="toggle:anti_arabic"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"👶 Yangilar Media Cheklovi: {status_icon(settings.get('newcomer_media_lock', True))}",
                    callback_data="toggle:newcomer_media_lock"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⭐️ Premium Emojilar: {status_icon(settings.get('anti_custom_emoji', True))}",
                    callback_data="toggle:anti_custom_emoji"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🌙 Tungi Rejim: {night_icon(settings.get('night_mode', False))}",
                    callback_data="toggle:night_mode"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🧹 Xizmat xabarlari: {status_icon(settings.get('service_cleaner', True))}",
                    callback_data="toggle:service_cleaner"
                )
            ],
            [
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="panel:main")
            ]
        ]
    )

# ==================== /admin va /panel BUYRUQLARI ====================
@router.message(Command("admin", "panel"))
async def cmd_admin_panel(message: Message, bot: Bot):
    """Admin panelni ochish."""
    # 1. Adminlik tekshiruvi
    if not await db.is_bot_admin(message.from_user.id):
        if message.chat.type != "private":
            auto_delete(message, 5)
        else:
            await message.reply("❌ Siz bot administratori emassiz!")
        return

    # 2. Agar guruhda yozilgan bo'lsa: lichkaga havola beramiz (xavfsizlik va qulaylik uchun)
    if message.chat.type in ["group", "supergroup"]:
        bot_info = await bot.get_me()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎛 Admin Panelni ochish",
                        url=f"https://t.me/{bot_info.username}?start=panel"
                    )
                ]
            ]
        )
        resp = await message.reply("ℹ️ Qulaylik va xavfsizlik uchun Admin Panelni shaxsiy chatda oching:", reply_markup=kb)
        auto_delete(message, 15)
        auto_delete(resp, 20)
        return

    # 3. Lichkada bo'lsa: to'g'ridan-to'g'ri panelni ochamiz
    is_owner = db.is_owner(message.from_user.id)
    role_text = "👑 Bosh Admin (Owner)" if is_owner else "👮‍♂️ Bot Admini"
    
    text = (
        f"🎛 <b>ADMIN BOSHQARUV PANELI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Admin:</b> {message.from_user.full_name}\n"
        f"🎖 <b>Darajangiz:</b> {role_text}\n"
        f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n\n"
        f"Guruh himoyalarini sozlash, adminlarni boshqarish yoki e'lon yuborish uchun quyidagi bo'limlardan birini tanlang:"
    )
    await message.answer(text, reply_markup=main_panel_keyboard(), parse_mode="HTML")

# Lichkada /start panel bosilganda
@router.message(CommandStart(deep_link=True), F.text.endswith("panel"))
async def cmd_start_deep_link_panel(message: Message):
    if not await db.is_bot_admin(message.from_user.id):
        await message.answer("❌ Siz bot administratori emassiz!")
        return

    is_owner = db.is_owner(message.from_user.id)
    role_text = "👑 Bosh Admin (Owner)" if is_owner else "👮‍♂️ Bot Admini"

    text = (
        f"🎛 <b>ADMIN BOSHQARUV PANELI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Admin:</b> {message.from_user.full_name}\n"
        f"🎖 <b>Darajangiz:</b> {role_text}\n"
        f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n\n"
        f"Kerakli bo'limni tanlang:"
    )
    await message.answer(text, reply_markup=main_panel_keyboard(), parse_mode="HTML")

# ==================== CALLBACK LAR (PANEL NAVIGATION) ====================
@router.callback_query(F.data == "panel:main")
async def cb_panel_main(callback: CallbackQuery):
    """Asosiy panel menyusiga qaytish."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    is_owner = db.is_owner(callback.from_user.id)
    role_text = "👑 Bosh Admin (Owner)" if is_owner else "👮‍♂️ Bot Admini"

    text = (
        f"🎛 <b>ADMIN BOSHQARUV PANELI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Admin:</b> {callback.from_user.full_name}\n"
        f"🎖 <b>Darajangiz:</b> {role_text}\n"
        f"🆔 <b>ID:</b> <code>{callback.from_user.id}</code>\n\n"
        f"Kerakli bo'limni tanlang:"
    )
    await callback.message.edit_text(text, reply_markup=main_panel_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "panel:settings")
async def cb_panel_settings(callback: CallbackQuery):
    """Guruh sozlamalari sahifasi."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    chat_id = get_group_target_id()
    kb = await settings_keyboard(chat_id)

    text = (
        f"⚙️ <b>GURUH HIMOYA SOZLAMALARI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💬 <b>Guruh ID:</b> <code>{chat_id}</code>\n\n"
        f"Tugmalarni bosish orqali kerakli himoyani darhol <b>yoqishingiz</b> yoki <b>o'chirishingiz</b> mumkin:"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("toggle:"))
async def cb_toggle_setting(callback: CallbackQuery, bot: Bot):
    """Sozlamani ON / OFF qilish."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    setting_name = callback.data.split(":")[1]
    chat_id = get_group_target_id()

    new_val = await db.toggle_chat_setting(chat_id, setting_name)

    # Agar tungi rejim o'zgargan bo'lsa, Telegram guruh huquqlarini ham o'zgartiramiz!
    if setting_name == "night_mode" and chat_id:
        try:
            if new_val:
                # Guruhni yopish
                await bot.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=ChatPermissions(
                        can_send_messages=False,
                        can_send_media_messages=False,
                        can_send_other_messages=False,
                        can_add_web_page_previews=False
                    )
                )
                await log_night_mode(bot, callback.from_user, enabled=True)
            else:
                # Guruhni ochish
                await bot.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=ChatPermissions(
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_other_messages=True,
                        can_add_web_page_previews=True
                    )
                )
                await log_night_mode(bot, callback.from_user, enabled=False)
        except Exception as e:
            logger.error(f"Guruh huquqlarini o'zgartirishda xatolik: {e}")

    # Klaviaturani yangilaymiz
    kb = await settings_keyboard(chat_id)
    await callback.message.edit_reply_markup(reply_markup=kb)

    status_str = "YOQILDI ✅" if new_val else "O'CHIRILDI ❌"
    await callback.answer(f"Sozlama o'zgardi: {status_str}")

@router.callback_query(F.data == "panel:admins")
async def cb_panel_admins(callback: CallbackQuery):
    """Adminlar ro'yxati va boshqaruvi."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    is_owner = db.is_owner(callback.from_user.id)
    bot_admins = await db.get_all_bot_admins()

    text = "👥 <b>BOT ADMINISTRATORLARI:</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    text += "👑 <b>Asosiy Adminlar (Owner):</b>\n"
    for o_id in config.ADMIN_IDS:
        text += f"• <code>{o_id}</code>\n"

    text += "\n👮‍♂️ <b>Qo'shilgan Moderatorlar:</b>\n"
    if not bot_admins:
        text += "<i>(Hozircha qo'shimcha adminlar yo'q)</i>\n"
    else:
        for a in bot_admins:
            added_date = str(a['added_at'])[:10]
            text += f"• <code>{a['user_id']}</code> - {a['title']} (Qo'shilgan: {added_date})\n"

    # Klaviatura
    buttons = []
    # Agar Owner bo'lsa, adminlarni o'chirish tugmalarini chiqaramiz
    if is_owner and bot_admins:
        for a in bot_admins:
            buttons.append([
                InlineKeyboardButton(
                    text=f"❌ O'chirish: {a['user_id']} ({a['title']})",
                    callback_data=f"del_admin:{a['user_id']}"
                )
            ])

    if is_owner:
        text += (
            "\n💡 <b>Yangi admin qo'shish uchun:</b>\n"
            "<code>/addadmin &lt;Telegram ID&gt; [Izoh/Lavozim]</code>\n"
            "<i>Masalan:</i> <code>/addadmin 123456789 Moderator</code>\n\n"
            "💡 <b>Adminni o'chirish uchun:</b>\n"
            "<code>/deladmin &lt;Telegram ID&gt;</code> yoki pastdagi tugmani bosing."
        )

    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="panel:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("del_admin:"))
async def cb_del_admin(callback: CallbackQuery, bot: Bot):
    """Adminni inline tugma orqali o'chirish (faqat Owner)."""
    if not db.is_owner(callback.from_user.id):
        await callback.answer("❌ Faqat Bosh Admin (Owner) adminlarni o'chira oladi!", show_alert=True)
        return

    target_id = int(callback.data.split(":")[1])
    success = await db.remove_bot_admin(target_id)
    if success:
        await callback.answer(f"✅ Admin ({target_id}) muvaffaqiyatli o'chirildi!", show_alert=True)
        await send_log(
            bot,
            f"🗑 <b>BOT ADMINI O'CHIRILDI</b>\n"
            f"👑 <b>Bosh admin:</b> {callback.from_user.full_name}\n"
            f"🆔 <b>O'chirilgan ID:</b> <code>{target_id}</code>"
        )
        # Sahifani qayta ochamiz
        await cb_panel_admins(callback)
    else:
        await callback.answer("❌ Admin topilmadi!", show_alert=True)

@router.callback_query(F.data == "panel:stats")
async def cb_panel_stats(callback: CallbackQuery):
    """Statistika oynasi."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    chat_id = get_group_target_id()
    total_warns = await db.get_total_warns_count()
    bot_admins = await db.get_all_bot_admins()

    text = (
        f"📊 <b>GURUH VA BOT STATISTIKASI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💬 <b>Asosiy Guruh ID:</b> <code>{chat_id}</code>\n"
        f"📋 <b>Log Kanal ID:</b> <code>{config.LOG_CHANNEL_ID}</code>\n"
        f"👑 <b>Bosh Adminlar:</b> {len(config.ADMIN_IDS)} ta\n"
        f"👮‍♂️ <b>Bot Adminlari:</b> {len(bot_admins)} ta\n"
        f"⚠️ <b>Jami berilgan ogohlantirishlar (Warn):</b> {total_warns} ta\n"
        f"🎮 <b>Discord Havola:</b> {config.DISCORD_URL}\n"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="panel:main")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "panel:broadcast")
async def cb_panel_broadcast_help(callback: CallbackQuery):
    """E'lon yuborish bo'yicha ko'rsatma."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    text = (
        f"📢 <b>GURUHGA E'LON YUBORISH:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Guruhga rasmiy e'lon yuborish uchun quyidagi buyruqdan foydalaning:\n\n"
        f"<code>/broadcast Sizning e'loningiz matni...</code>\n\n"
        f"<i>Bot ushbu xabarni guruhga chiroyli formatda va administratsiya nomidan yuboradi.</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="panel:main")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ==================== ADMINLARNI QO'SHISH / O'CHIRISH BUYRUQLARI ====================
@router.message(Command("addadmin"))
async def cmd_add_admin(message: Message, bot: Bot):
    """Yangi admin qo'shish (Faqat Owner uchun)."""
    if not db.is_owner(message.from_user.id):
        await message.reply("❌ Faqat Bosh Admin (Owner) yangi admin qo'sha oladi!")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.reply(
            "ℹ️ <b>Foydalanish:</b>\n"
            "<code>/addadmin &lt;Telegram ID&gt; [Izoh]</code>\n\n"
            "<i>Misol:</i> <code>/addadmin 123456789 Moderator</code>",
            parse_mode="HTML"
        )
        return

    target_id = int(parts[1].strip())
    title = parts[2].strip() if len(parts) > 2 else "Moderator"

    await db.add_bot_admin(target_id, added_by=message.from_user.id, title=title)
    await message.reply(
        f"✅ <b>Muvaffaqiyatli!</b>\n"
        f"Yangi admin qo'shildi:\n"
        f"🆔 <b>ID:</b> <code>{target_id}</code>\n"
        f"🏷 <b>Lavozim/Izoh:</b> {title}",
        parse_mode="HTML"
    )

    await send_log(
        bot,
        f"👮‍♂️ <b>YANGI BOT ADMINI TAYINLANDI</b>\n"
        f"👑 <b>Bosh admin:</b> {message.from_user.full_name}\n"
        f"🎯 <b>Yangi admin ID:</b> <code>{target_id}</code>\n"
        f"📌 <b>Lavozim:</b> {title}"
    )

@router.message(Command("deladmin"))
async def cmd_del_admin(message: Message, bot: Bot):
    """Adminni o'chirish (Faqat Owner uchun)."""
    if not db.is_owner(message.from_user.id):
        await message.reply("❌ Faqat Bosh Admin (Owner) adminlarni o'chira oladi!")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.reply("ℹ️ <b>Foydalanish:</b> <code>/deladmin &lt;Telegram ID&gt;</code>", parse_mode="HTML")
        return

    target_id = int(parts[1].strip())
    success = await db.remove_bot_admin(target_id)
    if success:
        await message.reply(f"✅ <code>{target_id}</code> hisobidagi adminlik olib tashlandi.", parse_mode="HTML")
        await send_log(
            bot,
            f"🗑 <b>BOT ADMINI O'CHIRILDI</b>\n"
            f"👑 <b>Bosh admin:</b> {message.from_user.full_name}\n"
            f"🆔 <b>O'chirilgan ID:</b> <code>{target_id}</code>"
        )
    else:
        await message.reply("❌ Bunday admin topilmadi.")

@router.message(Command("admins"))
async def cmd_admins_list(message: Message):
    """Adminlar ro'yxatini matn ko'rinishida ko'rish."""
    if not await db.is_bot_admin(message.from_user.id):
        return

    bot_admins = await db.get_all_bot_admins()
    text = "👥 <b>BOT ADMINISTRATORLARI RO'YXATI:</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    text += "👑 <b>Bosh Adminlar (Owner):</b>\n"
    for o_id in config.ADMIN_IDS:
        text += f"• <code>{o_id}</code>\n"

    text += "\n👮‍♂️ <b>Qo'shilgan Moderatorlar:</b>\n"
    if not bot_admins:
        text += "<i>(Qo'shimcha adminlar yo'q)</i>\n"
    else:
        for a in bot_admins:
            text += f"• <code>{a['user_id']}</code> - {a['title']}\n"

    await message.reply(text, parse_mode="HTML")

# ==================== /broadcast BUYRUG'I ====================
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot):
    """Guruhga e'lon yuborish."""
    if not await db.is_bot_admin(message.from_user.id):
        await message.reply("❌ Siz bot administratori emassiz!")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("ℹ️ <b>Foydalanish:</b> <code>/broadcast E'lon matni</code>", parse_mode="HTML")
        return

    announcement_text = parts[1].strip()
    target_chat = config.GROUP_ID

    if not target_chat:
        await message.reply("❌ Asosiy guruh ID si (GROUP_ID) sozlanmagan!")
        return

    try:
        sent_msg = await bot.send_message(
            chat_id=target_chat,
            text=(
                f"📢 <b>ADMINISTRATSIYA E'LONI:</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"{announcement_text}\n\n"
                f"<i>Hurmat bilan, Guruh Ma'muriyati.</i>"
            ),
            parse_mode="HTML"
        )
        await message.reply(f"✅ E'lon guruhga muvaffaqiyatli yuborildi! (Xabar ID: {sent_msg.message_id})")
    except Exception as e:
        logger.error(f"E'lon yuborishda xatolik: {e}")
        await message.reply(f"❌ Xatolik yuz berdi: {e}")

# ==================== TAQIQLANGAN SO'ZLAR (PAGINATSIYA BILAN) ====================
WORDS_PER_PAGE = 6

async def render_badwords_page(page: int = 1) -> Tuple[str, InlineKeyboardMarkup]:
    """Taqiqlangan so'zlar ro'yxatini sahifalarga bo'lib (Pagination) chiqaradi."""
    words = await db.get_all_bad_words()
    total_words = len(words)
    total_pages = max(1, (total_words + WORDS_PER_PAGE - 1) // WORDS_PER_PAGE)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * WORDS_PER_PAGE
    end_idx = start_idx + WORDS_PER_PAGE
    page_words = words[start_idx:end_idx]

    text = (
        f"📝 <b>TAQIQLANGAN SO'ZLAR (Blacklist)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📄 <b>Sahifa:</b> <code>{page}/{total_pages}</code> | 📊 <b>Jami:</b> <code>{total_words} ta so'z</code>\n\n"
    )

    if not words:
        text += "<i>(Hozircha taqiqlangan so'zlar kiritilmagan)</i>\n"
    else:
        for idx, w in enumerate(page_words, start=start_idx + 1):
            text += f"<b>{idx}.</b> <code>{w}</code>\n"

    text += (
        "\n💡 <b>Yangi so'z qo'shish:</b> <code>/addword &lt;so'z&gt;</code>\n"
        "💡 <b>O'chirish:</b> pastdagi tugmani bosing yoki <code>/delword &lt;so'z&gt;</code>"
    )

    buttons = []
    # 2 ustunli o'chirish tugmalari
    row = []
    for w in page_words:
        row.append(InlineKeyboardButton(text=f"❌ {w}", callback_data=f"del_w:{w}:{page}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Sahifalash navigatsiyasi
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"panel:badwords:page:{page - 1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="⏹", callback_data="noop"))

    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"panel:badwords:page:{page + 1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="⏹", callback_data="noop"))

    buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="🔄 Yangilash", callback_data=f"panel:badwords:page:{page}"),
        InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="panel:main")
    ])

    return text, InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    """Faol bo'lmagan axborot tugmalari uchun."""
    await callback.answer()

@router.callback_query(F.data == "panel:badwords")
@router.callback_query(F.data.startswith("panel:badwords:page:"))
async def cb_panel_badwords(callback: CallbackQuery):
    """Taqiqlangan so'zlar paginatsiya menyusi."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    page = 1
    if ":" in callback.data:
        parts = callback.data.split(":")
        if len(parts) >= 4 and parts[3].isdigit():
            page = int(parts[3])

    text, kb = await render_badwords_page(page)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("del_w:"))
@router.callback_query(F.data.startswith("del_word:"))
async def cb_del_badword(callback: CallbackQuery, bot: Bot):
    """Taqiqlangan so'zni inline tugma orqali o'chirish."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    parts = callback.data.split(":")
    word_to_del = parts[1]
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

    success = await db.remove_bad_word(word_to_del)
    if success:
        await callback.answer(f"✅ '{word_to_del}' o'chirildi!", show_alert=False)
        text, kb = await render_badwords_page(page)
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

        admin_user = callback.from_user
        await send_log(
            bot,
            f"🗑 <b>TAQIQLANGAN SO'Z O'CHIRILDI</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Admin:</b> <a href=\"tg://user?id={admin_user.id}\">{admin_user.full_name}</a>\n"
            f"🆔 <b>Admin ID:</b> <code>{admin_user.id}</code>\n"
            f"⭕️ <b>O'chirilgan so'z:</b> <code>{word_to_del}</code>\n"
            f"🕒 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    else:
        await callback.answer("❌ So'z topilmadi!", show_alert=True)

# ==================== VAQT VA MUDDAT SOZLAMALARI MENYUSI ====================
TIME_OPTIONS = {
    "captcha_timeout": {
        "title": "🛡 Captcha kutish vaqtini tanlang:",
        "unit": "soniya",
        "key": "captcha_timeout",
        "values": [30, 60, 90, 120, 180, 300]
    },
    "probation_minutes": {
        "title": "👶 Yangi a'zolar media cheklovi muddatini tanlang:",
        "unit": "daqiqa",
        "key": "probation_minutes",
        "values": [15, 30, 60, 120, 360, 1440]
    },
    "flood_mute_minutes": {
        "title": "⚡️ Spam/Flood uchun mute muddatini tanlang:",
        "unit": "daqiqa",
        "key": "flood_mute_minutes",
        "values": [5, 10, 30, 60, 1440]
    },
    "auto_delete_seconds": {
        "title": "🧹 Xabarlar avtomatik o'chish vaqtini tanlang:",
        "unit": "soniya",
        "key": "auto_delete_seconds",
        "values": [5, 10, 15, 20, 30, 60]
    },
    "max_warns": {
        "title": "⚠️ Maksimal ogohlantirish (warn) sonini tanlang:",
        "unit": "ta",
        "key": "max_warns",
        "values": [2, 3, 5, 10]
    }
}

async def render_time_settings_menu(chat_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    captcha_timeout = await db.get_chat_setting_int(chat_id, "captcha_timeout", default=90)
    probation_minutes = await db.get_chat_setting_int(chat_id, "probation_minutes", default=60)
    flood_mute_minutes = await db.get_chat_setting_int(chat_id, "flood_mute_minutes", default=10)
    auto_delete_seconds = await db.get_chat_setting_int(chat_id, "auto_delete_seconds", default=20)
    max_warns = await db.get_chat_setting_int(chat_id, "max_warns", default=3)

    text = (
        f"⏱ <b>GURUH VAQT VA MUDDAT SOZLAMALARI:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🛡 <b>Captcha kutish vaqti:</b> <code>{captcha_timeout} soniya</code>\n"
        f"👶 <b>Yangi a'zolar media cheklovi:</b> <code>{probation_minutes} daqiqa</code>\n"
        f"⚡️ <b>Spam/Flood uchun mute:</b> <code>{flood_mute_minutes} daqiqa</code>\n"
        f"🧹 <b>Xabarlar avto-o'chishi:</b> <code>{auto_delete_seconds} soniya</code>\n"
        f"⚠️ <b>Maksimal warnlar soni:</b> <code>{max_warns} ta</code>\n\n"
        f"<i>O'zgartirmoqchi bo'lgan sozlamangiz tugmasini bosing:</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🛡 Captcha Vaqti: {captcha_timeout}s", callback_data="time_menu:captcha_timeout")],
            [InlineKeyboardButton(text=f"👶 Yangilar Media Cheklovi: {probation_minutes}m", callback_data="time_menu:probation_minutes")],
            [InlineKeyboardButton(text=f"⚡️ Flood Mute Vaqti: {flood_mute_minutes}m", callback_data="time_menu:flood_mute_minutes")],
            [InlineKeyboardButton(text=f"🧹 Avto-o'chirish: {auto_delete_seconds}s", callback_data="time_menu:auto_delete_seconds")],
            [InlineKeyboardButton(text=f"⚠️ Max Warn: {max_warns} ta", callback_data="time_menu:max_warns")],
            [InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="panel:main")]
        ]
    )
    return text, kb

@router.callback_query(F.data == "panel:time_settings")
async def cb_panel_time_settings(callback: CallbackQuery):
    """Vaqt sozlamalari asosiy menyusi."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    chat_id = get_group_target_id()
    text, kb = await render_time_settings_menu(chat_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("time_menu:"))
async def cb_time_menu(callback: CallbackQuery):
    """Muayyan vaqt parametri uchun variantlar menyusi."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    param = callback.data.split(":")[1]
    conf = TIME_OPTIONS.get(param)
    if not conf:
        await callback.answer("Noma'lum parametr!")
        return

    chat_id = get_group_target_id()
    current_val = await db.get_chat_setting_int(chat_id, param)

    buttons = []
    row = []
    for v in conf["values"]:
        label = f"🔘 {v} {conf['unit']}" if v == current_val else f"{v} {conf['unit']}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"set_time:{param}:{v}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="panel:time_settings")])

    text = (
        f"⏱ <b>{conf['title']}</b>\n\n"
        f"Joriy qiymat: <b>{current_val} {conf['unit']}</b>\n"
        f"<i>Yangi qiymatni tanlang:</i>"
    )
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("set_time:"))
async def cb_set_time(callback: CallbackQuery, bot: Bot):
    """Vaqt sozlamasini o'zgartirish."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    parts = callback.data.split(":")
    param = parts[1]
    val = int(parts[2])
    chat_id = get_group_target_id()

    await db.set_chat_setting_int(chat_id, param, val)
    conf = TIME_OPTIONS.get(param, {"unit": ""})
    await callback.answer(f"✅ {val} {conf['unit']} qilib belgilandi!", show_alert=True)

    text, kb = await render_time_settings_menu(chat_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

    admin_user = callback.from_user
    await send_log(
        bot,
        f"⏱ <b>VAQT SOZLAMASI O'ZGARTIRILDI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Admin:</b> <a href=\"tg://user?id={admin_user.id}\">{admin_user.full_name}</a>\n"
        f"🆔 <b>Admin ID:</b> <code>{admin_user.id}</code>\n"
        f"⚙️ <b>Parametr:</b> <code>{param}</code>\n"
        f"📊 <b>Yangi qiymat:</b> <code>{val} {conf.get('unit', '')}</code>\n"
        f"🕒 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

# ==================== BARCHA BUYRUQLAR QO'LLANMASI ====================
COMMANDS_GUIDE_TEXT = (
    "📖 <b>BOTNING BARCHA BUYRUQLARI VA QO'LLANMASI:</b>\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "👮‍♂️ <b>MODERATSIYA BUYRUQLARI (Adminlar uchun):</b>\n"
    "• <code>/mute @username 10h [sabab]</code> — Foydalanuvchini vaqtincha yozishdan cheklash (sababi ixtiyoriy).\n"
    "• <code>/mute 10h [sabab]</code> — Xabarga reply qilib mute qilish.\n"
    "• <code>/unmute @username</code> yoki reply — Mutedan chiqarish.\n"
    "• <code>/warn @username [sabab]</code> yoki reply — Ogohlantirish berish (limitga yetsa avto-mute).\n"
    "• <code>/unwarn @username</code> yoki reply — Ogohlantirishni kamaytirish.\n"
    "• <code>/warns</code> — Foydalanuvchi ogohlantirishlarini ko'rish.\n"
    "• <code>/ban @username [sabab]</code> yoki reply — Guruhdan butunlay ban qilish.\n"
    "• <code>/unban @username</code> yoki <code>/unban &lt;ID&gt;</code> — Bandan chiqarish.\n"
    "• <code>/kick @username [sabab]</code> yoki reply — Guruhdan chiqarish (qayta kira oladi).\n"
    "• <code>/cleandeleted</code> (yoki <code>/kickdeleted</code>) — O'chirilgan akkauntlarni (Deleted Accounts) chiqarib yuborish.\n"
    "• <code>/clean &lt;soni&gt;</code> — Guruhdagi oxirgi X ta xabarni tozalash (masalan: <code>/clean 20</code>).\n\n"
    "⚙️ <b>ADMIN PANEL VA SOZLAMALAR:</b>\n"
    "• <code>/admin</code> yoki <code>/panel</code> — Interaktiv boshqaruv paneli (shaxsiy chatda).\n"
    "• <code>/addword &lt;so'z&gt;</code> — Taqiqlangan so'z qo'shish (guruhda avto-o'chiriladi).\n"
    "• <code>/delword &lt;so'z&gt;</code> — Taqiqlangan so'zni o'chirish.\n"
    "• <code>/words</code> — Barcha taqiqlangan so'zlarni ko'rish.\n"
    "• <code>/nightmode on/off</code> — Tungi rejimni yoqish/o'chirish.\n"
    "• <code>/dailyreport</code> — Bugungi jonli moderatsiya hisoboti.\n"
    "• <code>/addadmin &lt;ID&gt;</code> — Botga yangi admin qo'shish (faqat Bot Egasi).\n"
    "• <code>/deladmin &lt;ID&gt;</code> — Adminni olib tashlash.\n"
    "• <code>/admins</code> — Barcha bot adminlari ro'yxati.\n\n"
    "👥 <b>ODDIY FOYDALANUVCHILAR UCHUN:</b>\n"
    "• <code>/start</code> — Botni ishga tushirish.\n"
    "• <code>/rules</code> — Guruh qoidalarini ko'rish.\n"
    "• <code>/report [sabab]</code> — Qoidabuzar xabariga reply qilib adminlarga shikoyat qilish.\n"
    "• <code>/help</code> yoki <code>/commands</code> — Barcha buyruqlar ro'yxati.\n"
)

@router.callback_query(F.data == "panel:commands_guide")
async def cb_panel_commands_guide(callback: CallbackQuery):
    """Barcha buyruqlar qo'llanmasi."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Bosh Menyu", callback_data="panel:main")]]
    )
    await callback.message.edit_text(COMMANDS_GUIDE_TEXT, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.message(Command("commands"))
@router.message(Command("help"))
async def cmd_all_commands(message: Message):
    """Barcha buyruqlarni ko'rish."""
    is_group = message.chat.type in ["group", "supergroup"]
    msg = await message.reply(COMMANDS_GUIDE_TEXT, parse_mode="HTML")
    if is_group:
        auto_delete(message, delay=15)
        auto_delete(msg, delay=60)

@router.callback_query(F.data == "panel:today_report")
async def cb_panel_today_report(callback: CallbackQuery):
    """Bugungi jonli moderatsiya hisoboti."""
    if not await db.is_bot_admin(callback.from_user.id):
        await callback.answer("❌ Huquqingiz yetarli emas!", show_alert=True)
        return

    from bot.services.scheduler import generate_daily_report_text
    report_text = await generate_daily_report_text()
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Yangilash", callback_data="panel:today_report")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="panel:main")]
        ]
    )
    await callback.message.edit_text(report_text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ==================== SO'ZLARNI QO'SHISH / O'CHIRISH BUYRUQLARI ====================
@router.message(Command("addword"))
async def cmd_add_word(message: Message, bot: Bot):
    """Taqiqlangan so'z qo'shish."""
    if not await db.is_bot_admin(message.from_user.id):
        return

    is_group = message.chat.type in ["group", "supergroup"]
    if is_group:
        try:
            await message.delete()
        except Exception:
            pass

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        if is_group:
            err_msg = await message.answer("ℹ️ <b>Foydalanish:</b> <code>/addword so'z</code>", parse_mode="HTML")
            auto_delete(err_msg, delay=3)
        else:
            await message.reply("ℹ️ <b>Foydalanish:</b> <code>/addword so'z</code>", parse_mode="HTML")
        return

    new_word = parts[1].strip()
    await db.add_bad_word(new_word, added_by=message.from_user.id)

    if is_group:
        conf_msg = await message.answer("✅ Taqiqlangan so'zlar ro'yxatiga qo'shildi.", parse_mode="HTML")
        auto_delete(conf_msg, delay=2)
    else:
        await message.reply(f"✅ <code>{new_word}</code> taqiqlangan so'zlar ro'yxatiga qo'shildi.", parse_mode="HTML")

    admin_user = message.from_user
    await send_log(
        bot,
        f"📝 <b>YANGI TAQIQLANGAN SO'Z QO'SHILDI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Admin:</b> <a href=\"tg://user?id={admin_user.id}\">{admin_user.full_name}</a>\n"
        f"🆔 <b>Admin ID:</b> <code>{admin_user.id}</code>\n"
        f"🚫 <b>Qo'shilgan so'z:</b> <code>{new_word}</code>\n"
        f"📍 <b>Manzil:</b> {message.chat.title if is_group else 'Shaxsiy chat'}\n"
        f"🕒 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

@router.message(Command("delword"))
async def cmd_del_word(message: Message, bot: Bot):
    """Taqiqlangan so'zni o'chirish."""
    if not await db.is_bot_admin(message.from_user.id):
        return

    is_group = message.chat.type in ["group", "supergroup"]
    if is_group:
        try:
            await message.delete()
        except Exception:
            pass

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        if is_group:
            err_msg = await message.answer("ℹ️ <b>Foydalanish:</b> <code>/delword so'z</code>", parse_mode="HTML")
            auto_delete(err_msg, delay=3)
        else:
            await message.reply("ℹ️ <b>Foydalanish:</b> <code>/delword so'z</code>", parse_mode="HTML")
        return

    del_w = parts[1].strip()
    success = await db.remove_bad_word(del_w)
    if success:
        if is_group:
            conf_msg = await message.answer("✅ So'z taqiqlanganlar ro'yxatidan olib tashlandi.", parse_mode="HTML")
            auto_delete(conf_msg, delay=2)
        else:
            await message.reply(f"✅ <code>{del_w}</code> ro'yxatdan olib tashlandi.", parse_mode="HTML")

        admin_user = message.from_user
        await send_log(
            bot,
            f"🗑 <b>TAQIQLANGAN SO'Z O'CHIRILDI</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Admin:</b> <a href=\"tg://user?id={admin_user.id}\">{admin_user.full_name}</a>\n"
            f"🆔 <b>Admin ID:</b> <code>{admin_user.id}</code>\n"
            f"⭕️ <b>O'chirilgan so'z:</b> <code>{del_w}</code>\n"
            f"📍 <b>Manzil:</b> {message.chat.title if is_group else 'Shaxsiy chat'}\n"
            f"🕒 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    else:
        if is_group:
            err_msg = await message.answer("❌ Bunday so'z topilmadi.")
            auto_delete(err_msg, delay=2)
        else:
            await message.reply("❌ Bunday so'z topilmadi.")

@router.message(Command("words"))
async def cmd_words(message: Message):
    """Taqiqlangan so'zlar ro'yxatini ko'rish."""
    if not await db.is_bot_admin(message.from_user.id):
        return

    is_group = message.chat.type in ["group", "supergroup"]
    if is_group:
        try:
            await message.delete()
        except Exception:
            pass

    words = await db.get_all_bad_words()
    if not words:
        msg = await message.reply("ℹ️ Taqiqlangan so'zlar ro'yxati bo'sh.")
        if is_group:
            auto_delete(msg, delay=3)
        return

    text = "📝 <b>TAQIQLANGAN SO'ZLAR:</b>\n\n"
    for idx, w in enumerate(words, 1):
        text += f"{idx}. <code>{w}</code>\n"
    msg = await message.reply(text, parse_mode="HTML")
    if is_group:
        auto_delete(msg, delay=10)

@router.message(Command("dailyreport"))
async def cmd_daily_report(message: Message):
    """Bugungi jonli hisobotni ko'rish."""
    if not await db.is_bot_admin(message.from_user.id):
        return

    from bot.services.scheduler import generate_daily_report_text
    report_text = await generate_daily_report_text()
    await message.reply(report_text, parse_mode="HTML")
