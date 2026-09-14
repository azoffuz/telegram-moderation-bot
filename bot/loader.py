from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from bot.config import config

# Agar BOT_TOKEN bo'sh bo'lsa (import vaqtida test xatoligi chiqmasligi uchun)
token = config.BOT_TOKEN if config.BOT_TOKEN else "123456789:TEST_DUMMY_TOKEN_FOR_IMPORT_CHECK"

bot = Bot(
    token=token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
