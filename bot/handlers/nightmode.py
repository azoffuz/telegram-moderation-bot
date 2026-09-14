import logging
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions
from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.logger import log_night_mode
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="nightmode")

@router.message(Command("nightmode"), IsGroupFilter())
async def cmd_nightmode(message: Message, bot: Bot):
    """
    Tungi rejimni yoqish yoki o'chirish:
    /nightmode on  -> Guruhni yopadi (faqat adminlar yoza oladi)
    /nightmode off -> Guruhni ochadi
    """
    if not await IsAdminFilter()(message, bot):
        auto_delete(message, 5)
        return

    parts = message.text.split()
    action = parts[1].lower() if len(parts) > 1 else None

    # Agar argument berilmagan bo'lsa, joriy holatni ko'rsatamiz
    if not action or action not in ["on", "off"]:
        current = await db.get_night_mode(message.chat.id)
        status_text = "🌙 Yoqilgan (Guruh yopiq)" if current else "☀️ O'chirilgan (Guruh ochiq)"
        info_msg = await message.reply(
            f"ℹ️ <b>Tungi rejim holati:</b> {status_text}\n\n"
            f"Boshqarish uchun:\n"
            f"• <code>/nightmode on</code> - Guruhni yopish (faqat adminlar yoza oladi)\n"
            f"• <code>/nightmode off</code> - Guruhni ochish",
            parse_mode="HTML"
        )
        auto_delete(message, 15)
        auto_delete(info_msg, 15)
        return

    user = message.from_user

    if action == "on":
        try:
            # Oddiy foydalanuvchilar uchun xabar yozishni o'chiramiz
            await bot.set_chat_permissions(
                chat_id=message.chat.id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                )
            )
            await db.set_night_mode(message.chat.id, True)

            notice_msg = await message.answer(
                "🌙 <b>TUNGI REJIM YOQILDI!</b>\n\n"
                "Guruhda xabar yozish vaqtincha cheklandi (faqat adminlar yoza oladi).\n"
                "Ertalabgacha xayrli tun!",
                parse_mode="HTML"
            )
            await log_night_mode(bot, user, enabled=True)
        except Exception as e:
            logger.error(f"Tungi rejimni yoqishda xatolik: {e}")
            err = await message.reply("❌ Guruh huquqlarini o'zgartirishda xatolik yuz berdi. Botga 'Change Group Info' huquqini berganingizni tekshiring.")
            auto_delete(err, 10)

    elif action == "off":
        try:
            # Oddiy foydalanuvchilarga xabar yozishni ochamiz
            await bot.set_chat_permissions(
                chat_id=message.chat.id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )
            await db.set_night_mode(message.chat.id, False)

            notice_msg = await message.answer(
                "☀️ <b>TUNGI REJIM O'CHIRILDI!</b>\n\n"
                "Guruh barcha a'zolar uchun ochildi. Hurmatli a'zolar, kuningiz xayrli o'tsin!",
                parse_mode="HTML"
            )
            auto_delete(notice_msg, delay=30)
            await log_night_mode(bot, user, enabled=False)
        except Exception as e:
            logger.error(f"Tungi rejimni o'chirishda xatolik: {e}")
            err = await message.reply("❌ Guruh huquqlarini qaytarishda xatolik yuz berdi.")
            auto_delete(err, 10)

    auto_delete(message, 10)
