import asyncio
import logging
import sys
from aiogram import Bot
from bot.config import config
from bot.loader import bot, dp
from bot.database import db
from bot.handlers import register_routers
from bot.web import start_web_server
from bot.services.logger import send_log
from bot.services.scheduler import start_daily_report_scheduler

# Loglarni sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("main")

async def on_startup(bot: Bot):
    """Bot ishga tushganda bajariladigan amallar."""
    bot_info = await bot.get_me()
    logger.info(f"🤖 Bot muvaffaqiyatli ishga tushdi: @{bot_info.username} ({bot_info.full_name})")

    # Log kanalga xabar yuborish
    startup_text = (
        f"🟢 <b>BOT ISHGA TUSHDI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Bot:</b> @{bot_info.username}\n"
        f"🆔 <b>ID:</b> <code>{bot_info.id}</code>\n"
        f"⚡️ <b>Holat:</b> 24/7 Moderatsiya faol\n"
        f"🛡 <b>Himoyalar:</b> Captcha, Anti-Link, Anti-Forward, Anti-Flood"
    )
    await send_log(bot, startup_text)

async def main():
    # 1. BOT_TOKEN mavjudligini tekshirish
    if not config.BOT_TOKEN or "TEST_DUMMY" in config.BOT_TOKEN:
        logger.error(
            "❌ BOT_TOKEN topilmadi! Iltimos, '.env' fayliga yoki Render muhitiga "
            "BOT_TOKEN o'zgaruvchisini kiriting."
        )
        sys.exit(1)

    # 2. Ma'lumotlar bazasini ishga tushirish (Supabase / SQLite)
    await db.connect()

    # 3. Routerlarni ro'yxatdan o'tkazish
    register_routers(dp)

    # 4. Render & UptimeRobot uchun web serverni ishga tushirish
    web_runner = await start_web_server()

    # 5. Eski to'planib qolgan xabarlarni tozalash (drop_pending_updates)
    await bot.delete_webhook(drop_pending_updates=True)

    # 6. Ruxsat etilgan update turlarini aniqlash (chat_member yangi a'zolar uchun shart!)
    allowed_updates = dp.resolve_used_update_types()
    if "chat_member" not in allowed_updates:
        allowed_updates.append("chat_member")

    logger.info(f"Qabul qilinadigan update turlari: {allowed_updates}")

    # Startup hodisasi
    await on_startup(bot)

    # 7. Kunlik hisobot xizmatini ishga tushirish
    scheduler_task = start_daily_report_scheduler(bot)

    # 8. Polling rejimida botni ishga tushirish
    try:
        await dp.start_polling(bot, allowed_updates=allowed_updates)
    finally:
        logger.info("Bot to'xtatilmoqda...")
        scheduler_task.cancel()
        await db.close()
        await web_runner.cleanup()
        await bot.session.close()
        logger.info("Bot to'liq to'xtatildi.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Dastur foydalanuvchi tomonidan to'xtatildi.")
