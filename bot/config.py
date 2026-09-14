import os
from typing import List, Optional
from dotenv import load_dotenv

# .env faylini yuklaymiz
load_dotenv()

def parse_channel_or_group_id(raw_val: Optional[str]) -> Optional[int]:
    """
    Guruh yoki kanal ID sini to'g'ri Telegram Bot API formatiga o'tkazadi.
    Vergullar (4,320,577,661) va bo'sh joylarni tozalaydi.
    Agar foydalanuvchi -100 siz kiritgan bo'lsa (4320577661),
    avtomatik -1004320577661 formatiga keltiradi.
    """
    if not raw_val:
        return None
    cleaned = str(raw_val).strip().replace(",", "").replace(" ", "").replace("'", "").replace('"', "")
    if not cleaned:
        return None

    # Allaqachon to'g'ri -100 bilan kiritilgan bo'lsa
    if cleaned.startswith("-100") and cleaned[4:].isdigit():
        return int(cleaned)

    # Agar - bilan boshlangan bo'lsa
    if cleaned.startswith("-") and cleaned[1:].isdigit():
        if len(cleaned[1:]) >= 9:
            return int(f"-100{cleaned[1:]}")
        return int(cleaned)

    # Agar musbat raqam bo'lsa (masalan: 4320577661)
    if cleaned.isdigit():
        return int(f"-100{cleaned}")

def parse_admin_ids(raw_val: str) -> List[int]:
    """Vergul bilan ajratilgan admin ID larini int ro'yxatiga o'tkazadi."""
    if not raw_val:
        return []
    ids = []
    for item in raw_val.split(","):
        cleaned = item.strip().replace(" ", "")
        if cleaned.lstrip("-").isdigit():
            ids.append(int(cleaned))
    return ids

class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
    
    # Asosiy adminlar ID ro'yxati
    ADMIN_IDS: List[int] = parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    
    # Nazorat qilinadigan asosiy guruh ID si
    GROUP_ID: Optional[int] = parse_channel_or_group_id(os.getenv("GROUP_ID"))
    
    # Maxfiy log kanal ID si
    LOG_CHANNEL_ID: Optional[int] = parse_channel_or_group_id(os.getenv("LOG_CHANNEL_ID"))
    
    # Discord server havolasi
    DISCORD_URL: str = os.getenv("DISCORD_URL", "https://discord.gg/").strip()
    
    # Captcha kutish vaqti (soniya)
    CAPTCHA_TIMEOUT: int = int(os.getenv("CAPTCHA_TIMEOUT", "90"))
    
    # Maksimal ogohlantirishlar soni (Warn chegarasi)
    MAX_WARNS: int = int(os.getenv("MAX_WARNS", "3"))
    
    # Avtomatik o'chirish kechikishi (soniya)
    AUTO_DELETE_DELAY: int = int(os.getenv("AUTO_DELETE_DELAY", "20"))
    
    # Ma'lumotlar bazasi havolasi (Supabase / Postgres yoki SQLite)
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL", "").strip() or None
    
    # Web server porti (Render.com uchun)
    PORT: int = int(os.getenv("PORT", "8080"))

    # Guruh qoidalari matni
    RULES_TEXT: str = (
        "📜 <b>GURUH QOIDALARI:</b>\n\n"
        "1. 🚫 <b>Reklama va havolalar taqiqlanadi:</b> Har qanday havola (link), boshqa kanal va guruhlar havolasi darhol o'chiriladi.\n"
        "2. 🚫 <b>Forward xabarlar taqiqlanadi:</b> Boshqa kanallardan yoki shaxslardan xabar uzatish (forward) mumkin emas.\n"
        "3. 🚫 <b>Haqorat va so'kinish:</b> Boshqa a'zolarni kamsitish, haqorat qilish qat'iyan taqiqlanadi.\n"
        "4. 🚫 <b>Spam va flood:</b> Ketma-ket keraksiz xabarlar, stikerlar va emojilarni yuborish taqiqlanadi.\n"
        "5. ⚠️ <b>3 ta ogohlantirish (warn):</b> 3 ta ogohlantirish olgan a'zo avtomatik ravishda 24 soatga mute qilinadi yoki chetlatiladi.\n"
        "6. 🌙 <b>Tungi rejim:</b> Tungi vaqtda guruhda faqat adminlar yoza oladi.\n\n"
        "<i>Guruhimizda samimiy va hurmatli muhitni saqlaylik!</i>"
    )

config = Config()
