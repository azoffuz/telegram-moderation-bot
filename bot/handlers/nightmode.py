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

async def apply_night_mode_permissions(bot: Bot, chat_id: int, enable: bool):
    """
    Tungi rejimni yoqish yoki o'chirishda guruh huquqlarini to'g'ri o'zgartiradi.
    Kunduzgi media (rasm, video, gif, stiker) cheklovlarini aslo buzmaydi!
    """
    if enable:
        # 1. Hozirgi kunduzgi sozlamalarni saqlab olamiz (agar ochiq bo'lsa)
        try:
            chat_info = await bot.get_chat(chat_id)
            if chat_info.permissions and chat_info.permissions.can_send_messages:
                p_dict = chat_info.permissions.model_dump(exclude_none=True)
                await db.save_daytime_permissions(chat_id, p_dict)
        except Exception as e:
            logger.debug(f"Kunduzgi huquqlarni olishda xatolik: {e}")

        # 2. Guruhda xabar yozishni to'xtatamiz
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_send_polls=False,
                can_invite_users=False,
                can_pin_messages=False,
                can_change_info=False
            ),
            use_independent_chat_permissions=True
        )
        await db.set_night_mode(chat_id, True)
    else:
        # 3. Kunduzgi rejimga qaytish:
        saved_perms = await db.get_daytime_permissions(chat_id)
        if saved_perms:
            # Faqat xabar yozishni ochamiz, qolgan barcha rasm/gif cheklovlari o'z holicha qoladi!
            saved_perms["can_send_messages"] = True
            valid_fields = {
                'can_send_messages', 'can_send_audios', 'can_send_documents', 'can_send_photos',
                'can_send_videos', 'can_send_video_notes', 'can_send_voice_notes', 'can_send_polls',
                'can_send_other_messages', 'can_add_web_page_previews', 'can_invite_users',
                'can_pin_messages', 'can_change_info'
            }
            clean_perms = {k: v for k, v in saved_perms.items() if k in valid_fields}
            perms = ChatPermissions(**clean_perms)
        else:
            # Sukut bo'yicha: Faqat matn yozish ochiq, rasm, gif, video, fayllar esa 0/10 yopiq turadi!
            perms = ChatPermissions(
                can_send_messages=True,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_send_polls=False,
                can_invite_users=False,
                can_pin_messages=False,
                can_change_info=False
            )

        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=perms,
            use_independent_chat_permissions=True
        )
        await db.set_night_mode(chat_id, False)

@router.message(Command("nightmode"), IsGroupFilter())
async def cmd_nightmode(message: Message, bot: Bot):
    """
    Tungi rejimni yoqish yoki o'chirish:
    /nightmode on  -> Guruhni yopadi (faqat adminlar yoza oladi)
    /nightmode off -> Guruhni ochadi
    """
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
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
            await apply_night_mode_permissions(bot, message.chat.id, enable=True)

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
            await apply_night_mode_permissions(bot, message.chat.id, enable=False)

            notice_msg = await message.answer(
                "☀️ <b>TUNGI REJIM O'CHIRILDI!</b>\n\n"
                "Guruh ochildi. Hurmatli a'zolar, kuningiz xayrli o'tsin!",
                parse_mode="HTML"
            )
            auto_delete(notice_msg, delay=30)
            await log_night_mode(bot, user, enabled=False)
        except Exception as e:
            logger.error(f"Tungi rejimni o'chirishda xatolik: {e}")
            err = await message.reply("❌ Guruh huquqlarini qaytarishda xatolik yuz berdi.")
            auto_delete(err, 10)

    auto_delete(message, 10)
