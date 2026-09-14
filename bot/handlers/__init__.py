from aiogram import Dispatcher
from bot.handlers.admin_panel import router as admin_panel_router
from bot.handlers.service import router as service_router
from bot.handlers.captcha import router as captcha_router
from bot.handlers.moderation import router as moderation_router
from bot.handlers.nightmode import router as nightmode_router
from bot.handlers.user_commands import router as user_commands_router
from bot.handlers.antiflood import router as antiflood_router
from bot.handlers.newcomer_guard import router as newcomer_guard_router
from bot.handlers.antiforward import router as antiforward_router
from bot.handlers.antilink import router as antilink_router
from bot.handlers.badwords import router as badwords_router

def register_routers(dp: Dispatcher):
    """Barcha routerlarni to'g'ri tartibda dispatcherga ro'yxatdan o'tkazish."""
    dp.include_router(admin_panel_router)
    dp.include_router(service_router)
    dp.include_router(captcha_router)
    dp.include_router(moderation_router)
    dp.include_router(nightmode_router)
    dp.include_router(user_commands_router)
    dp.include_router(antiflood_router)
    dp.include_router(newcomer_guard_router)
    dp.include_router(antiforward_router)
    dp.include_router(antilink_router)
    dp.include_router(badwords_router)

__all__ = ["register_routers"]
