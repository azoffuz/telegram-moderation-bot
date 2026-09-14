import logging
from aiohttp import web
from bot.config import config

logger = logging.getLogger(__name__)

async def handle_root(request: web.Request) -> web.Response:
    """Bosh sahifa - Render va UptimeRobot uchun."""
    return web.json_response({
        "status": "online",
        "service": "Telegram Moderation Bot",
        "description": "Bot muvaffaqiyatli ishlab turibdi",
        "features": [
            "Captcha",
            "100% Anti-Link",
            "100% Anti-Forward",
            "Anti-Flood",
            "Warn System",
            "Night Mode",
            "Auto Clean"
        ]
    })

async def handle_health(request: web.Request) -> web.Response:
    """UptimeRobot ping yuborishi uchun salomatlik tekshiruvi (Health Check)."""
    return web.json_response({
        "status": "healthy",
        "port": config.PORT
    })

def create_web_app() -> web.Application:
    """aiohttp web ilovasini tayyorlash."""
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    return app

async def start_web_server() -> web.AppRunner:
    """
    Render.com bepul Web Service da uxlab qolmasligi uchun
    $PORT da ishlaydigan yengil HTTP serverni ishga tushiradi.
    """
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, host="0.0.0.0", port=config.PORT)
    await site.start()
    logger.info(f"🌐 Render/Uptime HTTP web serveri ishga tushdi: http://0.0.0.0:{config.PORT}")
    return runner
