from aiogram import Dispatcher
from bot.handlers.admin_panel import router as admin_panel_router
from bot.handlers.service import router as service_router
from bot.handlers.captcha import router as captcha_router
from bot.handlers.moderation import router as moderation_router
from bot.handlers.nightmode import router as nightmode_router
from bot.handlers.slowmode import router as slowmode_router
from bot.handlers.user_commands import router as user_commands_router
from bot.handlers.log_threads import router as log_threads_router
from bot.handlers.chat_guard import router as chat_guard_router

def register_routers(dp: Dispatcher):
    """Barcha routerlarni to'g'ri tartibda dispatcherga ro'yxatdan o'tkazish."""
    dp.include_router(admin_panel_router)
    dp.include_router(service_router)
    dp.include_router(captcha_router)
    dp.include_router(moderation_router)
    dp.include_router(nightmode_router)
    dp.include_router(slowmode_router)
    dp.include_router(log_threads_router)
    dp.include_router(user_commands_router)
    dp.include_router(chat_guard_router)

__all__ = ["register_routers"]
