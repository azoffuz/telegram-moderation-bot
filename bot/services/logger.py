import logging
from datetime import datetime
from typing import Optional
from aiogram import Bot
from aiogram.types import User, Chat
from bot.config import config

logger = logging.getLogger(__name__)

async def send_log(bot: Bot, html_content: str):
    """Maxfiy log kanalga xabar yuborish."""
    if not config.LOG_CHANNEL_ID:
        return

    try:
        await bot.send_message(
            chat_id=config.LOG_CHANNEL_ID,
            text=html_content,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.warning(f"Log kanalga xabar yuborishda xatolik yuz berdi ({config.LOG_CHANNEL_ID}): {e}")

async def log_captcha(bot: Bot, user: User, passed: bool, reason: str = ""):
    """Captcha natijalarini loglash."""
    status_icon = "✅" if passed else "❌"
    status_text = "Tasdiqlandi" if passed else "O'ta olmadi (Kick qilindi)"
    
    text = (
        f"{status_icon} <b>CAPTCHA HODISASI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"🏷 <b>Username:</b> @{user.username if user.username else 'yo\'q'}\n"
        f"📊 <b>Holat:</b> {status_text}\n"
    )
    if reason:
        text += f"ℹ️ <b>Izoh:</b> {reason}\n"
    text += f"🕒 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    await send_log(bot, text)

async def log_anti_link(bot: Bot, user: User, chat: Chat, link: str, message_text: str):
    """Havola o'chirilishi haqida log."""
    preview = (message_text[:120] + "...") if len(message_text) > 120 else message_text
    clean_preview = preview.replace("<", "&lt;").replace(">", "&gt;")
    
    text = (
        f"🔗 <b>ANTI-LINK (Havola o'chirildi)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"🏷 <b>Username:</b> @{user.username if user.username else 'yo\'q'}\n"
        f"💬 <b>Guruh:</b> {chat.title}\n"
        f"🔍 <b>Aniqlangan havola:</b> <code>{link}</code>\n"
        f"📝 <b>Xabar matni:</b> <i>{clean_preview}</i>\n"
        f"🕒 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await send_log(bot, text)

async def log_anti_forward(bot: Bot, user: User, chat: Chat, source_info: str):
    """Forward xabar o'chirilishi haqida log."""
    text = (
        f"🔀 <b>ANTI-FORWARD (Uzatilgan xabar o'chirildi)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Foydalanuvchi:</b> <a href=\"tg://user?id={user.id}\">{user.full_name}</a>\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"🏷 <b>Username:</b> @{user.username if user.username else 'yo\'q'}\n"
        f"💬 <b>Guruh:</b> {chat.title}\n"
        f"📦 <b>Manba:</b> {source_info}\n"
        f"🕒 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await send_log(bot, text)

async def log_moderation(
    bot: Bot,
    admin: Optional[User],
    target_user: User,
    action: str,
    reason: str = "Ko'rsatilmadi",
    details: str = ""
):
    """Moderatsiya harakati (Warn, Mute, Ban, Kick) logi."""
    admin_name = f"<a href=\"tg://user?id={admin.id}\">{admin.full_name}</a>" if admin else "🤖 Avtomatlashtirilgan Tizim"
    
    text = (
        f"🛡 <b>MODERATSIYA HARAKATI: {action.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮‍♂️ <b>Moderator:</b> {admin_name}\n"
        f"🎯 <b>Jazolangan:</b> <a href=\"tg://user?id={target_user.id}\">{target_user.full_name}</a>\n"
        f"🆔 <b>ID:</b> <code>{target_user.id}</code>\n"
        f"🏷 <b>Username:</b> @{target_user.username if target_user.username else 'yo\'q'}\n"
        f"⚡️ <b>Harakat:</b> {action}\n"
        f"📌 <b>Sabab:</b> {reason}\n"
    )
    if details:
        text += f"ℹ️ <b>Qo'shimcha:</b> {details}\n"
    text += f"🕒 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    await send_log(bot, text)

async def log_night_mode(bot: Bot, admin: User, enabled: bool):
    """Tungi rejim holati logi."""
    status = "🌙 YOQILDI (Guruh yopildi)" if enabled else "☀️ O'CHIRILDI (Guruh ochildi)"
    text = (
        f"🌓 <b>TUNGI REJIM O'ZGARDI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮‍♂️ <b>Admin:</b> <a href=\"tg://user?id={admin.id}\">{admin.full_name}</a>\n"
        f"📊 <b>Yangi holat:</b> {status}\n"
        f"🕒 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await send_log(bot, text)

async def log_report(bot: Bot, reporter: User, reported_user: User, message_link: str, reason: str):
    """Foydalanuvchi shikoyati (Report) logi."""
    text = (
        f"🚨 <b>YANGI SHIKOYAT (/report)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Shikoyat qiluvchi:</b> <a href=\"tg://user?id={reporter.id}\">{reporter.full_name}</a> (<code>{reporter.id}</code>)\n"
        f"🎯 <b>Shikoyat qilingan:</b> <a href=\"tg://user?id={reported_user.id}\">{reported_user.full_name}</a> (<code>{reported_user.id}</code>)\n"
        f"📌 <b>Sabab:</b> {reason}\n"
    )
    if message_link:
        text += f"🔗 <b>Xabar havolasi:</b> <a href=\"{message_link}\">Xabarga o'tish</a>\n"
    text += f"🕒 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    await send_log(bot, text)
