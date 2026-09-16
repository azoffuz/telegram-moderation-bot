import logging
from aiogram import Router, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import config
from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.services.logger import log_report
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="user_commands")

# ==================== /rules ====================
@router.message(Command("rules"), IsGroupFilter())
async def cmd_rules(message: Message, bot: Bot):
    """Guruh qoidalarini ko'rsatish."""
    try:
        await message.delete()
    except Exception:
        pass

    rules_msg = await bot.send_message(
        chat_id=message.chat.id,
        text=config.RULES_TEXT,
        parse_mode="HTML"
    )
    auto_delete(rules_msg, delay=45)

# ==================== /discord ====================
@router.message(Command("discord"), IsGroupFilter())
async def cmd_discord(message: Message, bot: Bot):
    """
    Discord server havolasini yuboradi.
    Eski Discord xabari va foydalanuvchi yozgan /discord xabari avtomatik o'chiriladi,
    lekin yangi yuborilgan Discord xabari guruhda o'chmasdan qoladi.
    """
    chat_id = message.chat.id

    # 1. Guruhda oldin yuborilgan Discord xabari bo'lsa, uni avtomatik o'chiramiz
    old_msg_id = await db.get_chat_setting_int(chat_id, "last_discord_message_id", default=0)
    if old_msg_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except Exception:
            pass

    # 2. Foydalanuvchining /discord deb yozgan buyruq xabarini darhol o'chiramiz
    try:
        await message.delete()
    except Exception:
        pass

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
    
    # 3. Yangi Discord xabarini yuboramiz (lekin uni O'CHIRMAYMIZ)
    discord_msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            "👋 Bizning rasmiy <b>Discord serverimizga</b> marhamat!\n"
            "Quyidagi tugma orqali serverimizga qo'shilishingiz mumkin:"
        ),
        reply_markup=keyboard,
        parse_mode="HTML"
    )

    # Yangi xabar ID sini bazada saqlaymiz (keyingi safar /discord chaqirilganda buni o'chirish uchun)
    await db.set_chat_setting_int(chat_id, "last_discord_message_id", discord_msg.message_id)

# ==================== /report ====================
@router.message(Command("report"), IsGroupFilter())
async def cmd_report(message: Message, bot: Bot):
    """Foydalanuvchilar spamlarni adminga xabar berishi uchun."""
    if not message.reply_to_message:
        try:
            await message.delete()
        except Exception:
            pass
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

    try:
        await message.delete()
    except Exception:
        pass

    confirm_msg = await bot.send_message(
        chat_id=message.chat.id,
        text="✅ <b>Rahmat!</b> Sizning shikoyatingiz guruh moderatorlariga yetkazildi.",
        parse_mode="HTML"
    )
    auto_delete(confirm_msg, 5)

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
