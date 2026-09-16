import asyncio
import time
import logging
from collections import deque
from typing import Dict, Optional
from aiogram import Bot
from bot.database import db
from bot.services.logger import send_log
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)

# Sozlanmalar (Yengil va qulay oraliqlar)
WINDOW_SECONDS = 15.0       # Kuzatuv oynasi: 15 soniya
THRESHOLD_10S = 8           # 15s ichida 8+ xabar bo'lsa -> 10 soniya
THRESHOLD_30S = 16          # 15s ichida 16+ xabar bo'lsa -> 30 soniya
COOLDOWN_CHANGE_SECONDS = 30.0  # Telegram API limitiga tushmaslik uchun minimal oraliq
CALM_DOWN_WAIT_SECONDS = 45.0   # Tinchiganidan so'ng pasaytirish uchun kutish vaqti

# Xotira keshlar
_chat_message_times: Dict[int, deque] = {}
_current_chat_delay: Dict[int, int] = {}
_last_change_ts: Dict[int, float] = {}
_last_busy_ts: Dict[int, float] = {}


def get_current_slowmode_delay(chat_id: int) -> int:
    """Guruhda hozirgi sozlangan slowmode soniyasini oladi."""
    return _current_chat_delay.get(chat_id, 0)


async def apply_chat_slowmode(bot: Bot, chat_id: int, delay: int, reason: str = "") -> bool:
    """Telegram API orqali guruhning slow_mode_delay sini o'zgartiradi."""
    old_delay = _current_chat_delay.get(chat_id, 0)
    if old_delay == delay:
        return True

    try:
        await bot.set_chat_slow_mode_delay(chat_id=chat_id, slow_mode_delay=delay)
        _current_chat_delay[chat_id] = delay
        _last_change_ts[chat_id] = time.time()

        # Guruhga qisqa, tez yo'qoluvchi bildirishnoma
        if delay > 0:
            msg_text = (
                f"⏳ <b>Guruhda xabarlar oqimi tezlashgani sababli yozish tezligi "
                f"vaqtincha {delay} soniyaga sekinlashtirildi.</b>"
            )
            try:
                sent = await bot.send_message(chat_id, msg_text, parse_mode="HTML")
                auto_delete(sent, delay=7)
            except Exception:
                pass

            # Log kanalga qayd qilish
            await send_log(
                bot,
                f"⚡️ <b>DINAMIK SLOWMODE ISHGA TUSHDI</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💬 <b>Guruh ID:</b> <code>{chat_id}</code>\n"
                f"⏱ <b>Yangi tezlik:</b> <code>{delay} soniya</code>\n"
                f"📊 <b>Sabab:</b> {reason or 'Faollik ko\'paydi'}\n"
                f"🕒 <b>Vaqt:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}",
                category="moderation"
            )
        else:
            msg_text = "🟢 <b>Guruhdagi sekinlashtirish olib tashlandi. Bemalol yozishingiz mumkin.</b>"
            try:
                sent = await bot.send_message(chat_id, msg_text, parse_mode="HTML")
                auto_delete(sent, delay=7)
            except Exception:
                pass

            await send_log(
                bot,
                f"🟢 <b>DINAMIK SLOWMODE BEKOR QILINDI</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💬 <b>Guruh ID:</b> <code>{chat_id}</code>\n"
                f"⏱ <b>Yangi tezlik:</b> <code>Cheklovsiz (0s)</code>\n"
                f"📊 <b>Holat:</b> Guruh tinchidi va normal holatga qaytdi\n"
                f"🕒 <b>Vaqt:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}",
                category="moderation"
            )

        logger.info(f"Guruh slowmode o'zgartirildi: {chat_id} -> {delay}s ({reason})")
        return True
    except Exception as e:
        logger.error(f"Slowmode o'zgartirishda xatolik ({chat_id} -> {delay}s): {e}")
        return False


async def record_message_and_evaluate_slowmode(bot: Bot, chat_id: int):
    """
    Guruhdagi har bir yangi xabar kelganda chaqiriladi (asinxron, 0ms yuklama).
    Xabarlar chastotasini tekshirib, kerak bo'lsa slowmodeni ko'taradi.
    """
    now = time.time()

    if chat_id not in _chat_message_times:
        _chat_message_times[chat_id] = deque()

    times = _chat_message_times[chat_id]
    times.append(now)

    # 15 soniyadan eski vaqtlarni tozalaymiz
    while times and now - times[0] > WINDOW_SECONDS:
        times.popleft()

    msg_count = len(times)
    current_delay = _current_chat_delay.get(chat_id, 0)
    last_change = _last_change_ts.get(chat_id, 0)

    # Faollik qayd qilindi
    if msg_count >= THRESHOLD_10S:
        _last_busy_ts[chat_id] = now

    # Cooldown tekshiruvi: 30 soniya ichida qayta-qayta almashtirmaymiz
    if now - last_change < COOLDOWN_CHANGE_SECONDS:
        return

    # Ko'tarish shartlari
    if msg_count >= THRESHOLD_30S and current_delay < 30:
        await apply_chat_slowmode(
            bot, chat_id, 30,
            reason=f"15 soniyada {msg_count} ta xabar (juda yuqori faollik)"
        )
    elif msg_count >= THRESHOLD_10S and current_delay < 10:
        await apply_chat_slowmode(
            bot, chat_id, 10,
            reason=f"15 soniyada {msg_count} ta xabar (o'rtacha faollik)"
        )


async def slowmode_recovery_worker(bot: Bot):
    """
    Har 20 soniyada bir marta guruh tinchiganini tekshiruvchi va
    sekinlashtirishni asta-sekin olib tashlovchi orqa fon xizmati.
    """
    logger.info("⏳ Dinamik slowmode tiklash xizmati ishga tushdi.")
    while True:
        try:
            await asyncio.sleep(20)
            now = time.time()

            for chat_id, delay in list(_current_chat_delay.items()):
                if delay <= 0:
                    continue

                # Guruhda auto_slowmode yoqilganmi?
                enabled = await db.get_chat_setting_bool(chat_id, "auto_slowmode", default=False)
                if not enabled:
                    # Agar sozlama o'chirilgan bo'lsa, mavjud cheklovni ham 0 qilamiz
                    await apply_chat_slowmode(bot, chat_id, 0, reason="Sozlama o'chirildi")
                    continue

                times = _chat_message_times.get(chat_id)
                if times:
                    while times and now - times[0] > WINDOW_SECONDS:
                        times.popleft()
                    recent_count = len(times)
                else:
                    recent_count = 0

                last_busy = _last_busy_ts.get(chat_id, 0)
                last_change = _last_change_ts.get(chat_id, 0)

                # Agar oxirgi o'zgarishdan keyin kamida 30s o'tgan bo'lsa va chat tinchigan bo'lsa
                if (now - last_busy >= CALM_DOWN_WAIT_SECONDS) and (now - last_change >= COOLDOWN_CHANGE_SECONDS):
                    if recent_count < 4:
                        if delay == 30:
                            # 30s dan 10s ga tushiramiz
                            await apply_chat_slowmode(bot, chat_id, 10, reason="Faollik pasaydi")
                        elif delay == 10:
                            # 10s dan 0s (normal) ga tushiramiz
                            await apply_chat_slowmode(bot, chat_id, 0, reason="Guruh to'liq tinchidi")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"slowmode_recovery_worker xatosi: {e}")
