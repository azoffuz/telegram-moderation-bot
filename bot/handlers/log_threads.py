import logging
from typing import Dict, Any, List
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from bot.database import db
from bot.services.cleaner import auto_delete

logger = logging.getLogger(__name__)
router = Router(name="log_threads")

# Mavzular konfiguratsiyasi
TOPIC_CONFIGS = {
    "moderation": {
        "name": "🛡 Moderatsiya",
        "icon_color": 0x6FB9F0,  # Ko'k
        "desc": "Warn, Mute, Ban, Kick va boshqa jazo choralari",
        "intro": (
            "🛡 <b>MODERATSIYA MAVZUSI</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Bu mavzuga guruhdagi barcha jazolash harakatlari tushadi:\n"
            "• <code>/mute</code> va <code>/unmute</code>\n"
            "• <code>/ban</code> va <code>/unban</code>\n"
            "• <code>/warn</code> va <code>/unwarn</code>\n"
            "• <code>/kick</code> va boshqa cheklovlar."
        )
    },
    "spam": {
        "name": "🚫 Spam & Filtrlar",
        "icon_color": 0xFF93B2,  # Qizil / Pushti
        "desc": "Havolalar, Forward, Lokatsiya, Arabcha, Premium emojilar",
        "intro": (
            "🚫 <b>SPAM VA FILTRLAR MAVZUSI</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Bu mavzuga avtomatik filtrlar tomonidan to'xtatilgan qoidabuzarliklar tushadi:\n"
            "• 🔗 <b>Anti-Link:</b> Reklama va havolalar\n"
            "• 🔀 <b>Anti-Forward:</b> Begona kanallardan forwardlar\n"
            "• 📍 <b>Anti-Location:</b> Telegram lokatsiyalari\n"
            "• 🛑 <b>Arab/Fors:</b> Begona yozuvlar\n"
            "• ⭐️ <b>Premium Emojilar:</b> Maxsus stiker va emojilar\n"
            "• ⚡️ <b>Anti-Flood:</b> Spam hujumlari."
        )
    },
    "badwords": {
        "name": "📝 Taqiqlangan So'zlar",
        "icon_color": 0xFFD67E,  # Sariq / To'q sariq
        "desc": "Ushlangan va yangi qo'shilgan so'zlar",
        "intro": (
            "📝 <b>TAQIQLANGAN SO'ZLAR MAVZUSI</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Bu mavzuga guruhda taqiqlangan so'zlar ushlanganda,\n"
            "shuningdek yangi so'z qo'shilganda (<code>/addword</code>) yoki "
            "o'chirilganda (<code>/delword</code>) loglar yuboriladi."
        )
    },
    "reports": {
        "name": "🚨 Shikoyatlar",
        "icon_color": 0xE17076,  # To'q qizil
        "desc": "A'zolardan kelgan /report shikoyatlari",
        "intro": (
            "🚨 <b>SHIKOYATLAR MAVZUSI (/report)</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Guruh a'zolari nojo'ya xabarlarga javoban <code>/report</code> "
            "buyrug'ini yuborganida shikoyatlar to'g'ridan-to'g'ri shu mavzuga kelib tushadi."
        )
    },
    "members": {
        "name": "👥 A'zolar & Captcha",
        "icon_color": 0x72D5FD,  # Moviy
        "desc": "Kirganlar, Captcha va Deleted account tozalash",
        "intro": (
            "👥 <b>A'ZOLAR VA CAPTCHA MAVZUSI</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Guruhga yangi a'zolar qo'shilishi, Captcha robot tekshiruvi natijalari "
            "va o'chirilgan akkauntlarni guruhdan chiqarish hisobotlari shu yerga tushadi."
        )
    },
    "system": {
        "name": "📊 Tizim & Hisobot",
        "icon_color": 0xCB86DB,  # Binafsharang
        "desc": "Kunlik hisobot, Tungi rejim va adminlar",
        "intro": (
            "📊 <b>TIZIM VA HISOBOT MAVZUSI</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Bu yerga har kecha 00:00 da kunlik moderatsiya hisoboti,\n"
            "avtomatik Tungi rejim holatlari va bot adminlari o'zgarishlari keladi."
        )
    }
}

# ==================== 1 TA BUYRUQ BILAN AVTOMATIK OCHISH ====================
@router.message(Command("setup_threads", "setup_topics", "setup-threads", "setup-topics", "init_threads"))
async def cmd_setup_threads(message: Message, bot: Bot):
    """
    Admin/Log guruhida barcha 6 ta log mavzusini (Forum Topics)
    1 ta buyruq bilan avtomatik yaratish va ulash.
    """
    # Faqat bot adminlari yoki guruh adminlari
    if not await db.is_bot_admin(message.from_user.id):
        return

    chat = message.chat
    if chat.type not in ["group", "supergroup"]:
        await message.reply("❌ Ushbu buyruqni faqat loglar yuboriladigan <b>Admin Guruhida</b> ishlatish kerak!")
        return

    # Guruhda Forum (Mavzular) yoqilganligini tekshiramiz
    if not getattr(chat, "is_forum", False):
        guide = (
            "⚠️ <b>Ushbu guruhda Forum (Mavzular / Topics) yoqilmagan!</b>\n\n"
            "Bot avtomatik mavzular ochishi uchun quyidagilarni bajaring:\n"
            "1️⃣ Guruh sozlamalariga kiring (Guruh nomi -> ✏️ Tahrirlash);\n"
            "2️⃣ <b>Mavzular (Topics / Темы)</b> funksiyasini YOQING;\n"
            "3️⃣ Botga guruhda <b>Mavzularni boshqarish (Manage Topics)</b> admin huquqini bering;\n"
            "4️⃣ So'ng ushbu buyruqni qayta yuboring: <code>/setup_threads</code>"
        )
        await message.reply(guide, parse_mode="HTML")
        return

    progress_msg = await message.reply("⏳ Mavzular avtomatik yaratilmoqda, iltimos kuting...")
    created_topics = []
    failed_topics = []

    for cat_key, conf in TOPIC_CONFIGS.items():
        try:
            # 1. Telegram API orqali Forum Topic yaratamiz
            topic = await bot.create_forum_topic(
                chat_id=chat.id,
                name=conf["name"],
                icon_color=conf["icon_color"]
            )
            thread_id = topic.message_thread_id

            # 2. Bazaga saqlaymiz
            await db.set_log_thread(
                category=cat_key,
                channel_id=chat.id,
                thread_id=thread_id,
                thread_name=conf["name"]
            )

            # 3. Mavzu ichiga kirish/tanishtiruv xabarini yuboramiz
            try:
                await bot.send_message(
                    chat_id=chat.id,
                    message_thread_id=thread_id,
                    text=conf["intro"],
                    parse_mode="HTML"
                )
            except Exception:
                pass

            created_topics.append((conf["name"], thread_id))
        except TelegramBadRequest as e:
            logger.error(f"Topic yaratishda Telegram xatosi ({conf['name']}): {e}")
            failed_topics.append((conf["name"], str(e)))
        except Exception as e:
            logger.error(f"Topic yaratishda kutilmagan xatolik ({conf['name']}): {e}")
            failed_topics.append((conf["name"], str(e)))

    # Natija hisoboti
    res_text = "🎉 <b>BARCHA MAVZULAR MUVAFFAQIYATLI YARATILDI!</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    for name, tid in created_topics:
        res_text += f"✅ <b>{name}</b> (Thread ID: <code>{tid}</code>)\n"

    if failed_topics:
        res_text += "\n⚠️ <b>Yaratilmagan mavzular:</b>\n"
        for name, err in failed_topics:
            res_text += f"❌ {name} ({err})\n"
        res_text += "\n<i>Iltimos, botga guruhda 'Manage Topics' huquqi berilganini tekshiring.</i>\n"

    res_text += (
        "\n🚀 <b>Endi bot barcha loglarni toifasiga qarab ushbu mavzularga bo'lib yuboradi!</b>\n"
        "Mavzularni ko'rish yoki tekshirish: <code>/threads</code>"
    )

    try:
        await progress_msg.edit_text(res_text, parse_mode="HTML")
    except Exception:
        await message.reply(res_text, parse_mode="HTML")


# ==================== QO'LDA MAVZU ICHIDA SOZLASH BUYRUQLARI ====================
async def _handle_manual_set_thread(message: Message, category: str):
    """Admin mavzu ichida yozganda o'sha mavzuni kategoriya uchun sozlash."""
    if not await db.is_bot_admin(message.from_user.id):
        return

    thread_id = getattr(message, "message_thread_id", None)
    if not thread_id:
        await message.reply(
            "⚠️ <b>Ushbu buyruqni sozlamoqchi bo'lgan Mavzuingiz (Topic) ichida yuboring!</b>\n"
            "Har bir mavzuning ichiga kirib, tegishli buyruqni yuborsangiz, bot uni eslab qoladi.",
            parse_mode="HTML"
        )
        return

    conf = TOPIC_CONFIGS.get(category, {})
    cat_name = conf.get("name", category.capitalize())

    await db.set_log_thread(
        category=category,
        channel_id=message.chat.id,
        thread_id=thread_id,
        thread_name=cat_name
    )

    resp = await message.reply(
        f"✅ <b>{cat_name}</b> loglari muvaffaqiyatli ushbu mavzuga "
        f"(Thread ID: <code>{thread_id}</code>) ulandi!\n\n"
        f"<i>Endi ushbu toifadagi barcha xabarlar shu yerga tushadi.</i>",
        parse_mode="HTML"
    )
    auto_delete(message, delay=15)
    auto_delete(resp, delay=25)


@router.message(Command("set_moderation", "set-moderation", "setmoderation"))
async def cmd_set_moderation(message: Message):
    await _handle_manual_set_thread(message, "moderation")

@router.message(Command("set_spam", "set-spam", "setspam"))
async def cmd_set_spam(message: Message):
    await _handle_manual_set_thread(message, "spam")

@router.message(Command("set_badwords", "set-badwords", "setbadwords", "set_badword", "set-badword", "setbadword"))
async def cmd_set_badwords(message: Message):
    await _handle_manual_set_thread(message, "badwords")

@router.message(Command("set_reports", "set-reports", "setreports", "set_report", "set-report", "setreport"))
async def cmd_set_reports(message: Message):
    await _handle_manual_set_thread(message, "reports")

@router.message(Command("set_members", "set-members", "setmembers", "set_captcha", "set-captcha", "setcaptcha"))
async def cmd_set_members(message: Message):
    await _handle_manual_set_thread(message, "members")

@router.message(Command("set_system", "set-system", "setsystem"))
async def cmd_set_system(message: Message):
    await _handle_manual_set_thread(message, "system")


# ==================== MAVZULAR HOLATINI KO'RISH VA TOZALASH ====================
@router.message(Command("threads", "topics", "log_topics", "logtopics"))
async def cmd_view_threads(message: Message):
    """Hozirgi ulangan mavzular ro'yxatini ko'rsatish."""
    if not await db.is_bot_admin(message.from_user.id):
        return

    all_threads = await db.get_all_log_threads()
    text = "🧵 <b>SOZLANGAN LOG MAVZULARI (THREADS):</b>\n━━━━━━━━━━━━━━━━━━\n\n"

    for cat_key, conf in TOPIC_CONFIGS.items():
        th = all_threads.get(cat_key)
        if th and th.get("thread_id"):
            text += f"✅ <b>{conf['name']}:</b> ID <code>{th['thread_id']}</code> (Chat: <code>{th['channel_id']}</code>)\n"
        else:
            text += f"⚪️ <b>{conf['name']}:</b> <i>Ulanmagan (Umumiy chatga boradi)</i>\n"

    text += (
        "\n💡 <b>Boshqaruv buyruqlari:</b>\n"
        "• <code>/setup_threads</code> — Barcha 6 ta mavzuni 1 ta buyruq bilan avto ochish.\n"
        "• Mavzu ichida turib sozlash: <code>/set_moderation</code>, <code>/set_spam</code>, <code>/set_badwords</code>, <code>/set_reports</code>, <code>/set_members</code>, <code>/set_system</code>.\n"
        "• <code>/reset_threads</code> — Mavzular ulanishini tozalash."
    )

    msg = await message.reply(text, parse_mode="HTML")
    if message.chat.type in ["group", "supergroup"]:
        auto_delete(message, delay=20)
        auto_delete(msg, delay=60)


@router.message(Command("reset_threads", "reset-threads", "clear_threads"))
async def cmd_reset_threads(message: Message):
    """Barcha mavzu ulanishlarini tozalash."""
    if not await db.is_bot_admin(message.from_user.id):
        return

    await db.clear_log_threads()
    msg = await message.reply(
        "🧹 Barcha log mavzulari ulanishi tozalandi. Endi barcha loglar umumiy log kanaliga jo'natiladi.",
        parse_mode="HTML"
    )
    if message.chat.type in ["group", "supergroup"]:
        auto_delete(message, delay=15)
        auto_delete(msg, delay=30)
