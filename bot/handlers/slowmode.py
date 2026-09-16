import logging
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message
from bot.database import db
from bot.filters.chat_type import IsGroupFilter
from bot.filters.admin import IsAdminFilter
from bot.services.cleaner import auto_delete
from bot.services.slowmode import apply_chat_slowmode, get_current_slowmode_delay

logger = logging.getLogger(__name__)
router = Router(name="slowmode")

@router.message(Command("slowmode"), IsGroupFilter())
async def cmd_slowmode(message: Message, bot: Bot):
    """Guruhda yozish tezligini (slowmode) ko'rish yoki boshqarish."""
    # 1. Adminlik tekshiruvi: oddiy a'zo yozsa jim o'chiramiz
    if not await IsAdminFilter()(message, bot):
        try:
            await message.delete()
        except Exception:
            pass
        return

    chat_id = message.chat.id
    parts = message.text.split()

    # 1. Faqat /slowmode yozilganda: joriy holatni ko'rsatish
    if len(parts) == 1:
        auto_enabled = await db.get_chat_setting_bool(chat_id, "auto_slowmode", default=False)
        current_delay = get_current_slowmode_delay(chat_id)

        auto_status = "✅ YOQILGAN (Avtomatik 10s va 30s ga sozlanadi)" if auto_enabled else "❌ O'CHIK"
        delay_status = f"{current_delay} soniya" if current_delay > 0 else "Cheklovsiz (0 soniya)"

        text = (
            f"⏱ <b>GURUH YOZISH TEZLIGI (SLOWMODE)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡️ <b>Dinamik Avto Rejim:</b> {auto_status}\n"
            f"⏳ <b>Hozirgi sekinlashtirish:</b> <code>{delay_status}</code>\n\n"
            f"💡 <b>Boshqaruv buyruqlari:</b>\n"
            f"• <code>/slowmode auto on</code> — Dinamik rejimni yoqish\n"
            f"• <code>/slowmode auto off</code> — Dinamik rejimni o'chirish\n"
            f"• <code>/slowmode 10</code> — 10 soniyalik cheklov qo'yish\n"
            f"• <code>/slowmode 30</code> — 30 soniyalik cheklov qo'yish\n"
            f"• <code>/slowmode 0</code> (yoki <code>off</code>) — Cheklovni bekor qilish"
        )
        msg = await message.reply(text, parse_mode="HTML")
        auto_delete(message, delay=15)
        auto_delete(msg, delay=40)
        return

    # 2. /slowmode auto on/off
    sub_cmd = parts[1].lower().strip()
    if sub_cmd == "auto":
        if len(parts) < 3:
            msg = await message.reply("ℹ️ <b>Foydalanish:</b> <code>/slowmode auto on</code> yoki <code>/slowmode auto off</code>", parse_mode="HTML")
            auto_delete(msg, delay=5)
            return

        action = parts[2].lower().strip()
        if action in ["on", "yoq", "1", "enable"]:
            await db.set_chat_setting_bool(chat_id, "auto_slowmode", True)
            msg = await message.reply("✅ <b>Dinamik Slowmode yoqildi!</b> Endi faollik oshganda bot tezlikni 10s yoki 30s ga o'zi moslaydi.", parse_mode="HTML")
        else:
            await db.set_chat_setting_bool(chat_id, "auto_slowmode", False)
            await apply_chat_slowmode(bot, chat_id, 0, reason="Admin buyrug'i bilan avto rejim o'chirildi")
            msg = await message.reply("❌ <b>Dinamik Slowmode o'chirildi.</b> Tezlik normal holatga qaytarildi.", parse_mode="HTML")

        auto_delete(message, delay=10)
        auto_delete(msg, delay=15)
        return

    # 3. Qo'lda soniya belgilash: /slowmode 10, /slowmode 30, /slowmode 0
    if sub_cmd in ["off", "ochir", "0"]:
        await apply_chat_slowmode(bot, chat_id, 0, reason="Admin qo'lda bekor qildi")
        msg = await message.reply("🟢 <b>Guruhdagi barcha sekinlashtirish cheklovlari olib tashlandi (0s).</b>", parse_mode="HTML")
    elif sub_cmd.isdigit():
        sec = int(sub_cmd)
        allowed = [10, 30, 60, 300]
        if sec not in allowed:
            msg = await message.reply("⚠️ Telegram faqat quyidagi soniyalarni qo'llab-quvvatlaydi: <code>0, 10, 30, 60, 300</code>", parse_mode="HTML")
            auto_delete(msg, delay=5)
            return

        success = await apply_chat_slowmode(bot, chat_id, sec, reason=f"Admin qo'lda {sec}s qilib belgiladi")
        if success:
            msg = await message.reply(f"✅ Guruhda yozish tezligi <b>{sec} soniya</b> qilib belgilandi.", parse_mode="HTML")
        else:
            msg = await message.reply("❌ Xatolik yuz berdi. Botga 'Change Chat Info' admin huquqi berilganini tekshiring.", parse_mode="HTML")
    else:
        msg = await message.reply("ℹ️ <b>Foydalanish:</b> <code>/slowmode 10</code>, <code>/slowmode 30</code>, <code>/slowmode 0</code> yoki <code>/slowmode auto on</code>", parse_mode="HTML")

    auto_delete(message, delay=10)
    auto_delete(msg, delay=15)
