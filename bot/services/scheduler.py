import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta, date
from aiogram import Bot
from bot.config import config
from bot.database import db
from bot.services.logger import send_log

logger = logging.getLogger(__name__)

async def generate_daily_report_text(target_date: Optional[date] = None) -> str:
    """Kunlik hisobot matnini shakllantiradi."""
    d = target_date or date.today()
    stats = await db.get_stats_for_date(d)
    
    total_cleaned = (
        stats.get("links_deleted", 0) +
        stats.get("forwards_deleted", 0) +
        stats.get("badwords_deleted", 0) +
        stats.get("arabic_deleted", 0) +
        stats.get("media_blocked", 0) +
        stats.get("custom_emoji_deleted", 0)
    )

    text = (
        f"📊 <b>KUNLIK MODERATSIYA HISOBOTI</b>\n"
        f"📅 <b>Sana:</b> {d.strftime('%Y-%m-%d')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>O'chirilgan havolalar:</b> {stats.get('links_deleted', 0)} ta\n"
        f"🔀 <b>To'xtatilgan forwardlar:</b> {stats.get('forwards_deleted', 0)} ta\n"
        f"🚫 <b>Taqiqlangan so'zlar:</b> {stats.get('badwords_deleted', 0)} ta\n"
        f"🛑 <b>Arab/Fors spamlari:</b> {stats.get('arabic_deleted', 0)} ta\n"
        f"⭐️ <b>O'chirilgan Premium emojilar:</b> {stats.get('custom_emoji_deleted', 0)} ta\n"
        f"👶 <b>Yangi a'zolardan bloklangan media:</b> {stats.get('media_blocked', 0)} ta\n"
        f"⚠️ <b>Berilgan ogohlantirishlar (Warn):</b> {stats.get('warns_count', 0)} ta\n"
        f"🔇 <b>Mute qilinganlar:</b> {stats.get('mutes_count', 0)} ta\n"
        f"👥 <b>Yangi qo'shilgan a'zolar:</b> {stats.get('joins_count', 0)} ta\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧹 <b>Jami zararsizlantirilgan spamlarlar:</b> {total_cleaned} ta\n\n"
        f"<i>🛡 Botingiz guruhni 24/7 xavfsiz va toza holatda saqlamoqda.</i>"
    )
    return text

async def daily_report_cron_worker(bot: Bot):
    """
    Har kecha soat 00:00 da (yoki har 24 soatda)
    kunlik hisobotni Maxfiy Log Kanalga avtomatik yuboruvchi orqa fon vazifasi.
    """
    logger.info("⏰ Kunlik hisobot xizmati ishga tushdi.")
    while True:
        try:
            now = datetime.now()
            # Ertangi kungi soat 00:00:05 gacha bo'lgan soniyani hisoblaymiz
            tomorrow = now.date() + timedelta(days=1)
            midnight = datetime.combine(tomorrow, datetime.min.time()) + timedelta(seconds=5)
            seconds_until_midnight = (midnight - now).total_seconds()

            logger.info(f"Keyingi kunlik hisobotgacha: {int(seconds_until_midnight)} soniya qoldi.")
            await asyncio.sleep(seconds_until_midnight)

            # Kechagi kunning to'liq statistikasini chiqaramiz
            yesterday = date.today() - timedelta(days=1)
            report_text = await generate_daily_report_text(yesterday)
            await send_log(bot, report_text)
            logger.info(f"Kunlik hisobot log kanalga muvaffaqiyatli yuborildi ({yesterday}).")

        except asyncio.CancelledError:
            logger.info("Kunlik hisobot xizmati to'xtatildi.")
            break
        except Exception as e:
            logger.error(f"Kunlik hisobot xizmatida xatolik: {e}")
            await asyncio.sleep(60)

def start_daily_report_scheduler(bot: Bot) -> asyncio.Task:
    """Kunlik hisobot vazifasini ishga tushiradi."""
    return asyncio.create_task(daily_report_cron_worker(bot))
