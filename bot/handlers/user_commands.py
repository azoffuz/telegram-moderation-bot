import logging
from aiogram import Router, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import config
from bot.filters.chat_type import IsGroupFilter
from bot.services.logger import log_report
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="user_commands")

# ==================== /rules ====================
@router.message(Command("rules"), IsGroupFilter())
async def cmd_rules(message: Message):
    """Guruh qoidalarini ko'rsatish."""
    rules_msg = await message.reply(
        config.RULES_TEXT,
        parse_mode="HTML"
    )
    auto_delete(message, delay=30)
    auto_delete(rules_msg, delay=45)

# ==================== /discord ====================
@router.message(Command("discord"), IsGroupFilter())
async def cmd_discord(message: Message):
    """Discord server havolasini tugma ko'rinishida berish."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎮 Discord serverimizga qo'shiling",
                    url=config.DISCORD_URL
                )
            ]
        ]
    )
    
    discord_msg = await message.reply(
        "👋 Bizning rasmiy <b>Discord serverimizga</b> marhamat!\n"
        "Quyidagi tugma orqali serverimizga qo'shilishingiz mumkin:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    auto_delete(message, delay=20)
    auto_delete(discord_msg, delay=35)

# ==================== /report ====================
@router.message(Command("report"), IsGroupFilter())
async def cmd_report(message: Message, bot: Bot):
    """Foydalanuvchilar spamlarni adminga xabar berishi uchun."""
    if not message.reply_to_message:
        msg = await message.reply("ℹ️ Qoidabuzar xabarga reply qilib <code>/report [sabab]</code> deb yozing.")
        auto_delete(message, 10)
        auto_delete(msg, 10)
        return

    reported_msg = message.reply_to_message
    reported_user = reported_msg.from_user
    reporter = message.from_user

    if not reported_user:
        return

    parts = message.text.split(maxsplit=1)
    reason = parts[1] if len(parts) > 1 else "Spam / Qoidabuzarlik"

    # Xabar havolasini yasash (Superguruhlar uchun)
    clean_chat_id = str(message.chat.id).replace("-100", "")
    message_link = f"https://t.me/c/{clean_chat_id}/{reported_msg.message_id}"

    # Log kanalga yuborish
    await log_report(
        bot=bot,
        reporter=reporter,
        reported_user=reported_user,
        message_link=message_link,
        reason=reason
    )

    confirm_msg = await message.reply(
        "✅ <b>Rahmat!</b> Sizning shikoyatingiz guruh moderatorlariga va log kanalga yetkazildi.",
        parse_mode="HTML"
    )
    auto_delete(message, 10)
    auto_delete(confirm_msg, 10)

# ==================== /start (Lichkada) ====================
@router.message(CommandStart())
async def cmd_start_private(message: Message):
    """Botning shaxsiy xabarlarida start bosilganda."""
    if message.chat.type == "private":
        await message.answer(
            "👋 <b>Assalomu alaykum!</b>\n\n"
            "Men Telegram guruhlarni nazorat qiluvchi, 100% spamsiz va toza saqlovchi moderatsiya botiman.\n\n"
            "<b>Mening imkoniyatlarim:</b>\n"
            "• ✅ Tugmali kirish captchasi (Robotlardan himoya)\n"
            "• 🔗 100% Anti-Link (Barcha havola va reklamalarni o'chirish)\n"
            "• 🔀 100% Anti-Forward (Uzatilgan xabarlarni o'chirish)\n"
            "• ⚡️ Anti-Flood / Anti-Spam tezkor mute\n"
            "• ⚠️ Warn tizimi (3 ta ogohlantirishda 24 soat mute)\n"
            "• 🌙 Tungi rejim (/nightmode on/off)\n"
            "• 📜 /rules va 🎮 /discord buyruqlari\n"
            "• 📋 Maxfiy log kanalga to'liq hisobotlar\n"
            "• 🧹 Guruhni toza saqlash (kirdi-chiqdilarni va bot javoblarini avto-o'chirish)\n\n"
            "<i>Meni guruhingizga admin qilib qo'shing va to'liq huquqlarni bering!</i>",
            parse_mode="HTML"
        )
