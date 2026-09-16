import asyncio
import logging
from typing import Optional, List
from datetime import datetime, timedelta, date, timezone
from aiogram import Bot
from bot.config import config
from bot.database import db
from bot.services.logger import send_log
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)

def is_hour_in_night_window(start_hour: int, end_hour: int, current_hour: int) -> bool:
    """
    Joriy soat tungi rejim oralig'iga to'g'ri kelishini hisoblaydi.
    Masalan:
      start=23, end=7: 23, 0, 1, 2, 3, 4, 5, 6 -> True (Night)
      start=1, end=5: 1, 2, 3, 4 -> True (Night)
    """
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= current_hour < end_hour
    else:
        # Tun yarmi orqali o'tuvchi vaqt (masalan 23:00 dan 07:00 gacha)
        return current_hour >= start_hour or current_hour < end_hour

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
        stats.get("custom_emoji_deleted", 0) +
        stats.get("locations_deleted", 0)
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
        f"📍 <b>O'chirilgan lokatsiyalar:</b> {stats.get('locations_deleted', 0)} ta\n"
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
    Har kecha mahalliy vaqt bo'yicha soat 00:00 da
    kunlik hisobotni Maxfiy Log Kanalga avtomatik yuboruvchi orqa fon vazifasi.
    """
    logger.info("⏰ Kunlik hisobot xizmati ishga tushdi.")
    while True:
        try:
            target_chat = config.GROUP_ID
            gmt_offset = await db.get_gmt_offset(target_chat) if target_chat else 5
            tz = timezone(timedelta(hours=gmt_offset))
            now = datetime.now(tz)

            # Mahalliy ertangi kungi soat 00:00:05 gacha bo'lgan soniyani hisoblaymiz
            tomorrow = now.date() + timedelta(days=1)
            midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=tz) + timedelta(seconds=5)
            seconds_until_midnight = max(5, (midnight - now).total_seconds())

            logger.info(f"Keyingi kunlik hisobotgacha: {int(seconds_until_midnight)} soniya qoldi (GMT{'+' if gmt_offset>=0 else ''}{gmt_offset}).")
            await asyncio.sleep(seconds_until_midnight)

            # Kechagi kunning to'liq statistikasini chiqaramiz
            yesterday = now.date()
            report_text = await generate_daily_report_text(yesterday)
            await send_log(bot, report_text)
            logger.info(f"Kunlik hisobot log kanalga muvaffaqiyatli yuborildi ({yesterday}).")

        except asyncio.CancelledError:
            logger.info("Kunlik hisobot xizmati to'xtatildi.")
            break
        except Exception as e:
            logger.error(f"Kunlik hisobot xizmatida xatolik: {e}")
            await asyncio.sleep(60)

async def auto_nightmode_worker(bot: Bot):
    """
    Guruhda Avtomatik Tungi Rejimni sozlangan GMT va soatlarga qarab
    belgilangan vaqtda o'zi yoqadigan va tongda ochadigan orqa fon xizmati.
    Kunduzgi media (0/10) cheklovlarini aslo buzmaydi!
    """
    logger.info("🌙 Avtomatik tungi rejim orqa fon xizmati ishga tushdi.")
    while True:
        try:
            target_chat = config.GROUP_ID
            if not target_chat:
                await asyncio.sleep(30)
                continue

            conf = await db.get_auto_nightmode_settings(target_chat)
            if not conf["auto_enabled"]:
                await asyncio.sleep(30)
                continue

            gmt_offset = conf["gmt_offset"]
            start_h = conf["start_hour"]
            end_h = conf["end_hour"]
            is_currently_night = conf["is_night"]

            tz = timezone(timedelta(hours=gmt_offset))
            now = datetime.now(tz)
            gmt_str = f"{'+' if gmt_offset >= 0 else ''}{gmt_offset}"

            in_night = is_hour_in_night_window(start_h, end_h, now.hour)
            last_action = await db.get_chat_setting_str(target_chat, "last_auto_nightmode_action", "")

            # 1. TUNGI VAQT KELDI -> Guruhni yopish kerak
            if in_night:
                cycle_key = f"ON_{now.strftime('%Y-%m-%d')}_{start_h}"
                if not is_currently_night and last_action != cycle_key:
                    from bot.handlers.nightmode import apply_night_mode_permissions
                    await apply_night_mode_permissions(bot, target_chat, enable=True)
                    await db.set_chat_setting_str(target_chat, "last_auto_nightmode_action", cycle_key)

                    try:
                        await bot.send_message(
                            chat_id=target_chat,
                            text=(
                                f"🌙 <b>AVTOMATIK TUNGI REJIM YOQILDI!</b>\n\n"
                                f"🕒 Rejali vaqt keldi (Soat <b>{start_h:02d}:00</b>).\n"
                                f"Guruhda xabar yozish ertalab soat <b>{end_h:02d}:00</b> gacha vaqtincha cheklandi.\n\n"
                                f"<i>Ertalabgacha barchaga xayrli tun!</i>"
                            ),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Avto tungi rejim guruhga xabar yuborishda xatolik: {e}")

                    await send_log(
                        bot,
                        f"🌙 <b>AVTO TUNGI REJIM ISHGA TUSHDI</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"💬 <b>Guruh ID:</b> <code>{target_chat}</code>\n"
                        f"🕒 <b>Vaqt:</b> {now.strftime('%Y-%m-%d %H:%M:%S')} (GMT{gmt_str})\n"
                        f"🌙 <b>Holat:</b> Guruh yopildi ({start_h:02d}:00 -> {end_h:02d}:00)"
                    )
                    logger.info(f"Avto tungi rejim guruhni yopdi ({target_chat}, {start_h}:00).")

            # 2. TONGGI VAQT KELDI -> Guruhni ochish kerak
            else:
                cycle_key = f"OFF_{now.strftime('%Y-%m-%d')}_{end_h}"
                if is_currently_night and last_action != cycle_key:
                    from bot.handlers.nightmode import apply_night_mode_permissions
                    await apply_night_mode_permissions(bot, target_chat, enable=False)
                    await db.set_chat_setting_str(target_chat, "last_auto_nightmode_action", cycle_key)

                    try:
                        notice_msg = await bot.send_message(
                            chat_id=target_chat,
                            text=(
                                f"☀️ <b>AVTOMATIK TUNGI REJIM O'CHIRILDI!</b>\n\n"
                                f"🕒 Tonggi vaqt keldi (Soat <b>{end_h:02d}:00</b>).\n"
                                f"Guruh ochildi. Hurmatli a'zolar, kuningiz xayrli va barakali o'tsin!"
                            ),
                            parse_mode="HTML"
                        )
                        auto_delete(notice_msg, delay=60)
                    except Exception as e:
                        logger.error(f"Avto tungi rejim guruhga xabar yuborishda xatolik: {e}")

                    await send_log(
                        bot,
                        f"☀️ <b>AVTO TUNGI REJIM YAKUNLANDI</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"💬 <b>Guruh ID:</b> <code>{target_chat}</code>\n"
                        f"🕒 <b>Vaqt:</b> {now.strftime('%Y-%m-%d %H:%M:%S')} (GMT{gmt_str})\n"
                        f"☀️ <b>Holat:</b> Guruh ochildi (kunduzgi media cheklovlari saqlangan)"
                    )
                    logger.info(f"Avto tungi rejim guruhni ochdi ({target_chat}, {end_h}:00).")

        except asyncio.CancelledError:
            logger.info("Avto tungi rejim xizmati to'xtatildi.")
            break
        except Exception as e:
            logger.error(f"Avto tungi rejim xizmatida xatolik: {e}")

        await asyncio.sleep(25)

def start_schedulers(bot: Bot) -> List[asyncio.Task]:
    """Barcha fon rejalashtiruvchilarini ishga tushiradi."""
    t1 = asyncio.create_task(daily_report_cron_worker(bot))
    t2 = asyncio.create_task(auto_nightmode_worker(bot))
    return [t1, t2]

def start_daily_report_scheduler(bot: Bot) -> asyncio.Task:
    """Eski chaqiruvlar uchun moslik funksiyasi."""
    return asyncio.create_task(daily_report_cron_worker(bot))
