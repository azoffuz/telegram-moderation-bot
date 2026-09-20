import logging
from datetime import datetime, timezone, timedelta
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions
from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.logger import log_night_mode, send_log
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

        # 3. Tungi rejim boshlanganda barcha a'zolardan Active teglarini tozalash
        try:
            from bot.services.active_tag import revoke_all_chat_tags
            asyncio.create_task(revoke_all_chat_tags(bot, chat_id))
        except Exception as e:
            logger.error(f"Tungi rejimda teglarni tozalash xatosi: {e}")
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
    Tungi rejim va Avto Rejim buyruqlari:
    • /nightmode          -> Joriy holat va jonli vaqt
    • /nightmode on/off   -> Qo'lda yoqish/o'chirish
    • /nightmode auto on/off -> Avto rejimni yoqish/o'chirish
    • /nightmode time 23 7   -> Avto yopilish va ochilish soatini sozlash
    • /nightmode gmt +5      -> GMT mintaqani sozlash
    """
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    parts = message.text.split()
    action = parts[1].lower() if len(parts) > 1 else None

    # 1. Avto rejim boshqaruvi: /nightmode auto on | /nightmode auto off
    if action == "auto":
        sub_action = parts[2].lower() if len(parts) > 2 else ""
        if sub_action in ["on", "yoqish", "1", "true"]:
            await db.set_chat_setting_bool(message.chat.id, "nightmode_auto", True)
            resp = await message.reply("✅ <b>Avtomatik tungi rejim YOQILDI!</b>\nBot har kuni belgilangan soatda guruhni o'zi yopadi va tongda ochadi.", parse_mode="HTML")
            auto_delete(message, 15)
            auto_delete(resp, 15)
            return
        elif sub_action in ["off", "ochirish", "0", "false"]:
            await db.set_chat_setting_bool(message.chat.id, "nightmode_auto", False)
            resp = await message.reply("⭕️ <b>Avtomatik tungi rejim O'CHIRILDI!</b>", parse_mode="HTML")
            auto_delete(message, 15)
            auto_delete(resp, 15)
            return
        else:
            resp = await message.reply("ℹ️ <b>Foydalanish:</b> <code>/nightmode auto on</code> yoki <code>/nightmode auto off</code>", parse_mode="HTML")
            auto_delete(message, 10)
            auto_delete(resp, 15)
            return

    # 2. Vaqtni sozlash: /nightmode time <boshlanish> <tugash> (masalan /nightmode time 23 7)
    if action == "time":
        if len(parts) >= 4:
            try:
                s_str = parts[2].split(":")[0]
                e_str = parts[3].split(":")[0]
                start_h = int(s_str)
                end_h = int(e_str)
                if 0 <= start_h <= 23 and 0 <= end_h <= 23:
                    await db.set_chat_setting_int(message.chat.id, "nightmode_start_hour", start_h)
                    await db.set_chat_setting_int(message.chat.id, "nightmode_end_hour", end_h)
                    resp = await message.reply(
                        f"✅ <b>Avto Tungi Rejim vaqti yangilandi!</b>\n\n"
                        f"🌙 <b>Yopilish:</b> <code>{start_h:02d}:00</code>\n"
                        f"☀️ <b>Ochilish:</b> <code>{end_h:02d}:00</code>",
                        parse_mode="HTML"
                    )
                    auto_delete(message, 15)
                    auto_delete(resp, 15)
                    return
            except Exception:
                pass
        resp = await message.reply("ℹ️ <b>Foydalanish:</b> <code>/nightmode time 23 7</code> (23:00 da yopiladi, 07:00 da ochiladi)", parse_mode="HTML")
        auto_delete(message, 10)
        auto_delete(resp, 15)
        return

    # 3. GMT sozlash: /nightmode gmt +5 yoki /nightmode gmt 5
    if action == "gmt":
        if len(parts) >= 3:
            try:
                val = int(parts[2].replace("+", "").strip())
                if -12 <= val <= 14:
                    await db.set_gmt_offset(message.chat.id, val)
                    sign = "+" if val >= 0 else ""
                    resp = await message.reply(f"✅ <b>Vaqt mintaqasi saqlandi:</b> <code>GMT{sign}{val}</code>", parse_mode="HTML")
                    auto_delete(message, 15)
                    auto_delete(resp, 15)
                    return
            except Exception:
                pass
        resp = await message.reply("ℹ️ <b>Foydalanish:</b> <code>/nightmode gmt +5</code> (O'zbekiston/Toshkent)", parse_mode="HTML")
        auto_delete(message, 10)
        auto_delete(resp, 15)
        return

    # 4. Agar argument berilmagan bo'lsa: to'liq holat va jonli soatni ko'rsatamiz
    if not action or action not in ["on", "off"]:
        conf = await db.get_auto_nightmode_settings(message.chat.id)
        gmt_offset = conf["gmt_offset"]
        sign = "+" if gmt_offset >= 0 else ""
        tz = timezone(timedelta(hours=gmt_offset))
        now_dt = datetime.now(tz)
        dt_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        status_text = "🌙 Yoqilgan (Guruh yopiq)" if conf["is_night"] else "☀️ O'chirilgan (Guruh ochiq)"
        auto_text = "✅ Yoqilgan" if conf["auto_enabled"] else "❌ O'chirilgan"

        info_msg = await message.reply(
            f"ℹ️ <b>TUNGI REJIM VA VAQT SOZLAMALARI:</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <b>Jonli vaqt:</b> <code>{dt_str} (GMT{sign}{gmt_offset})</code>\n"
            f"🔒 <b>Hozirgi holat:</b> {status_text}\n"
            f"🤖 <b>Avto Tungi Rejim:</b> {auto_text}\n"
            f"🌙 <b>Avto Yopilish:</b> <code>{conf['start_hour']:02d}:00</code>\n"
            f"☀️ <b>Avto Ochilish:</b> <code>{conf['end_hour']:02d}:00</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Buyruqlar:</b>\n"
            f"• <code>/nightmode on</code> — Guruhni darhol yopish\n"
            f"• <code>/nightmode off</code> — Guruhni darhol ochish\n"
            f"• <code>/nightmode auto on/off</code> — Avto rejimni yoqish/o'chirish\n"
            f"• <code>/nightmode time 23 7</code> — Yopilish va ochilish soatini o'rnatish\n"
            f"• <code>/nightmode gmt +5</code> — Vaqt mintaqasini belgilash\n"
            f"• <i>Yoki barchasini <code>/admin</code> panel orqali interaktiv sozlang!</i>",
            parse_mode="HTML"
        )
        auto_delete(message, 25)
        auto_delete(info_msg, 30)
        return

    user = message.from_user

    # 5. Qo'lda ON qilish
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

    # 6. Qo'lda OFF qilish
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

@router.message(Command("time", "gmt"))
async def cmd_current_time(message: Message, bot: Bot):
    """Joriy sozlangan GMT va server real vaqtini ko'rish."""
    if not await IsAdminFilter()(message, bot):
        if message.chat.type != "private":
            try:
                await message.delete()
            except Exception:
                pass
        return

    chat_id = message.chat.id if message.chat.type != "private" else (config.GROUP_ID or 0)
    gmt_offset = await db.get_gmt_offset(chat_id)
    sign = "+" if gmt_offset >= 0 else ""
    tz = timezone(timedelta(hours=gmt_offset))
    now_dt = datetime.now(tz)
    dt_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    text = (
        f"🕒 <b>JORIY REAL VAQT VA GMT:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Sana va vaqt:</b> <code>{dt_str}</code>\n"
        f"🌐 <b>Vaqt mintaqasi:</b> <code>GMT{sign}{gmt_offset}</code>\n\n"
        f"<i>O'zgartirish uchun <code>/nightmode gmt &lt;offset&gt;</code> yoki <code>/admin</code> panelidan foydalaning.</i>"
    )
    resp = await message.reply(text, parse_mode="HTML")
    if message.chat.type != "private":
        auto_delete(message, 15)
        auto_delete(resp, 20)
