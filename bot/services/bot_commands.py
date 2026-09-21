import logging
from typing import List
from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllChatAdministrators,
)

logger = logging.getLogger(__name__)

# Guruh adminlari uchun to'liq buyruqlar menyusi
ADMIN_GROUP_COMMANDS: List[BotCommand] = [
    BotCommand(command="admin", description="Boshqaruv panelini ochish"),
    BotCommand(command="active", description="Faol a'zolar reytingi (Bugun / Oylik)"),
    BotCommand(command="selfstats", description="Shaxsiy statistika va darajangiz"),
    BotCommand(command="delwarn", description="Xabarni o'chirib warn berish"),
    BotCommand(command="delmute", description="Xabarni o'chirib mute qilish"),
    BotCommand(command="delban", description="Xabarni o'chirib ban qilish"),
    BotCommand(command="warn", description="Foydalanuvchini ogohlantirish"),
    BotCommand(command="unwarn", description="Ogohlantirishni bekor qilish"),
    BotCommand(command="warns", description="Ogohlantirishlar sonini ko'rish"),
    BotCommand(command="resetwarns", description="Barcha ogohlantirishlarni tozalash"),
    BotCommand(command="mute", description="Foydalanuvchini mute qilish"),
    BotCommand(command="unmute", description="Mutedan chiqarish (unmute)"),
    BotCommand(command="ban", description="Foydalanuvchini chetlatish (ban)"),
    BotCommand(command="unban", description="Bandan chiqarish"),
    BotCommand(command="kick", description="Guruhdan chiqarib yuborish"),
    BotCommand(command="cleartags", description="Barcha a'zolardan teglarni tozalash"),
    BotCommand(command="resetactive", description="Faollik statistikasini tozalash"),
    BotCommand(command="giveactive", description="A'zoga qo'lda teg berish"),
    BotCommand(command="removeactive", description="A'zodan tegni olib tashlash"),
    BotCommand(command="nightmode", description="Tungi rejim va vaqt sozlamalari"),
    BotCommand(command="slowmode", description="Yozish tezligini sozlash"),
    BotCommand(command="threads", description="Log mavzulari (topics) holati"),
    BotCommand(command="report", description="Adminga qoidabuzar ustidan shikoyat"),
    BotCommand(command="time", description="Guruhning real vaqti va GMT holati"),
    BotCommand(command="antilink", description="Anti-Link himoyasini sozlash"),
    BotCommand(command="antimention", description="Mention/kanal nazoratini sozlash"),
    BotCommand(command="sync_commands", description="Buyruqlar menyusini yangilash"),
]

# Guruhdagi oddiy a'zolar uchun buyruqlar
MEMBER_GROUP_COMMANDS: List[BotCommand] = [
    BotCommand(command="active", description="Faol a'zolar reytingi (Bugun / Oylik)"),
    BotCommand(command="selfstats", description="Shaxsiy statistika va darajangiz"),
    BotCommand(command="report", description="Adminga qoidabuzar ustidan shikoyat"),
    BotCommand(command="time", description="Guruhning real vaqti va GMT holati"),
]

# Standart / Shaxsiy chatlar uchun buyruqlar
DEFAULT_COMMANDS: List[BotCommand] = [
    BotCommand(command="start", description="Botni ishga tushirish"),
    BotCommand(command="admin", description="Boshqaruv panelini ochish"),
    BotCommand(command="active", description="Faol a'zolar reytingi"),
    BotCommand(command="selfstats", description="Shaxsiy ko'rsatkichlar"),
]

async def setup_bot_commands(bot: Bot) -> bool:
    """
    Telegram Bot API orqali bot buyruqlarini avtomatik o'rnatadi.
    BotFather ga qo'lda yuborish shart emas!
    """
    try:
        # 1. Guruh administratorlari uchun
        await bot.set_my_commands(
            commands=ADMIN_GROUP_COMMANDS,
            scope=BotCommandScopeAllChatAdministrators()
        )

        # 2. Guruhdagi barcha a'zolar uchun
        await bot.set_my_commands(
            commands=MEMBER_GROUP_COMMANDS,
            scope=BotCommandScopeAllGroupChats()
        )

        # 3. Sukut bo'yicha (Default & Private)
        await bot.set_my_commands(
            commands=DEFAULT_COMMANDS,
            scope=BotCommandScopeDefault()
        )

        logger.info("✅ Telegram bot buyruqlari muvaffaqiyatli o'rnatildi!")
        return True
    except Exception as e:
        logger.error(f"❌ Bot buyruqlarini o'rnatishda xatolik: {e}")
        return False
