# 🛡 Telegram Guruh Nazoratchisi & Moderatsiya Boti

Professional, 100% spamsiz, tezkor va avtomatlashtirilgan Telegram guruh moderatsiya boti. Python 3 (`aiogram 3.x`) asosida qurilgan bo'lib, **Render.com** (bepul 24/7) hamda **Supabase** (yoki mahalliy SQLite) bilan to'liq integratsiyaga ega.

---

## 🚀 Asosiy Imkoniyatlar

1. **🤖 Bir Tugmali Kirish Captchasi (Welcome Button Captcha)**:
   - Yangi a'zo guruhga qo'shilganda darhol yozish huquqi cheklanadi (Mute).
   - Bot yangi a'zoga bitta tugmali xabar chiqaradi: `[ ✅ Men robot emasman ]`.
   - Faqat o'sha yangi a'zo bosa oladi (begona odam bossa ogohlantirish beradi).
   - **Taymer (masalan, 90s)**: Agar belgilangan vaqtda bosmasa, avtomatik guruhdan chiqariladi (Kick) va log kanalga qayd etiladi.
   - Tasdiqlangach, qisqa xush kelibsiz xabari chiqadi va u ham chat toza bo'lishi uchun 15 soniyada o'chiriladi.

2. **🔗 100% Anti-Link (Mutlaq Havola Himoyasi)**:
   - Barcha turdagi ochiq havolalar (`http`, `https`, `t.me/...`, domenlar `.uz`, `.com` va h.k.).
   - Telegram matniga yashirilgan havolalar (`text_link`).
   - `@username` / `@kanal` ko'rinishidagi mention havolalar.
   - Rasm va videolar ostidagi (caption) havolalar.
   - Xabar darhol o'chiriladi, qoidabuzar ogohlantiriladi va maxfiy log kanalga xabar yuboriladi (Adminlar bundan mustasno).

3. **🔀 100% Anti-Forward (Uzatilgan Xabarlar Himoyasi)**:
   - Telegram Bot API 7.0+ (`forward_origin`) va barcha eski API turlari qo'llab-quvvatlanadi.
   - Boshqa shaxslar, kanallar yoki maxfiy profillardan uzatilgan xabarlar 100% aniqlanib o'chiriladi va loglanadi.

4. **⚡️ Anti-Flood / Anti-Spam (Tezkor Cheklov)**:
   - Foydalanuvchi 4 soniya ichida 5 tadan ortiq xabar yuborsa, bot yoki spammer deb hisoblanib, avtomatik 10 daqiqaga mute qilinadi.

5. **⚠️ Ogohlantirish (Warn) Tizimi**:
   - `/warn [sabab]` - Reply qilib ogohlantirish berish.
   - `/unwarn` - Ogohlantirishni kamaytirish.
   - `/warns` - Foydalanuvchi ogohlantirishlarini ko'rish.
   - **3 ta ogohlantirish** to'planganda, foydalanuvchi avtomatik **24 soatga mute** qilinadi.

6. **👮‍♂️ Tezkor Moderatsiya Buyruqlari**:
   - `/mute 30m [sabab]` (masalan: `30m`, `2h`, `1d`, `1w`) - Vaqtincha mute qilish.
   - `/unmute` - Cheklovni bekor qilish.
   - `/ban [sabab]` - Guruhdan butunlay ban qilish.
   - `/unban [user_id]` - Bandan chiqarish.
   - `/kick [sabab]` - Guruhdan chiqarish (qayta kira oladi).
   - `/clean [soni]` - Chatdagi oxirgi X ta xabarni tozalash (masalan: `/clean 20`).

7. **🌙 Tungi Rejim (Night Mode)**:
   - `/nightmode on` - Guruh yopiladi (oddiy a'zolar yoza olmaydi, faqat adminlar yoza oladi).
   - `/nightmode off` - Guruh barcha a'zolar uchun ochiladi.

8. **🧹 Chat Tozaligi (Auto-cleaning)**:
   - Guruhdagi kirdi/chiqdi xizmat xabarlari (`joined`, `left`, `pinned`) darhol o'chiriladi.
   - Bot javoblari va admin buyruqlari belgilangan vaqtda (15–30 soniyada) avtomatik o'chiriladi.

9. **📋 Maxfiy Log Kanal**:
   - Har bir hodisa (Captcha o'tishi/o'tmasligi, link o'chirilishi, forward o'chirilishi, warn, mute, ban, report) maxfiy log kanalga chiroyli HTML formatda yuboriladi.

10. **⭐️ Anti-Premium Emoji (Tashqi va Maxsus Emojilarni O'chirish)**:
    - Telegram Premium foydalanuvchilari va spambotlar tomonidan yuboriladigan tashqi/maxsus animatsiyali emojilar (`custom_emoji`) avtomatik aniqlanib o'chiriladi. Paneldan yoqish/o'chirish mumkin.

11. **📜 Foydalanuvchi Buyruqlari**:
    - `/rules` - Guruh qoidalari.
    - `/discord` - Discord server havolasi (Inline tugma bilan).
    - `/report [sabab]` - Qoidabuzar xabarga reply qilib adminga va log kanalga xabar berish.

---

## 🛠 O'rnatish va Sozlash (Bosqichma-bosqich)

### 1-qadam: Telegram Bot yaratish
1. Telegramda [@BotFather](https://t.me/BotFather) ga kiring va `/newbot` buyrug'i orqali yangi bot oching.
2. Sizga berilgan **API Token**ni saqlab oling.
3. BotFather'da quyidagi sozlamalarni bajaring:
   - `/setprivacy` -> Botingizni tanlang -> **Disable** qiling (Guruhdagi barcha xabarlarni ko'ra olishi uchun).
   - `/setjoingroups` -> **Enable** qiling.

### 2-qadam: Guruh va Maxfiy Log Kanalni tayyorlash
1. Botingizni o'z **guruhingizga** va **maxfiy log kanalingizga** qo'shing.
2. Botga ikkala joyda ham **Administrator** huquqlarini bering:
   - *Delete messages* (Xabarlarni o'chirish)
   - *Ban users / Restrict members* (A'zolarni cheklash va chiqarish)
   - *Change group info* (Tungi rejim uchun guruh ruxsatlarini o'zgartirish)
3. Guruh va Kanal ID larini aniqlash:
   - Guruhga va kanalga biror xabar yozib, uni [@userinfobot](https://t.me/userinfobot) ga forward qiling.
   - ID odatda `-100...` bilan boshlanadi (masalan: `-1001234567890`).

### 3-qadam: Muhit O'zgaruvchilarini sozlash (.env)
Lokal ishga tushirish uchun `.env.example` dan nusxa olib `.env` fayl yarating:

```bash
cp .env.example .env
```

`.env` faylini to'ldiring:
```env
BOT_TOKEN=sizning_bot_tokeningiz
ADMIN_IDS=sizning_telegram_id_ingiz
GROUP_ID=-1001234567890
LOG_CHANNEL_ID=-1009876543210
DISCORD_URL=https://discord.gg/yourserver
CAPTCHA_TIMEOUT=90
MAX_WARNS=3
AUTO_DELETE_DELAY=20
DATABASE_URL=
PORT=8080
```

> **Eslatma:** Agar `DATABASE_URL` bo'sh qoldirilsa, bot avtomatik ravishda `moderation.db` (SQLite) faylida ishlaydi!
> Agar Supabase ishlatmoqchi bo'lsangiz, Supabase Project Settings -> Database bo'limidan Connection string'ni olasiz:
> `DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres`

---

## ☁️ Render.com da 24/7 Bepul Joylashtirish (Deploy)

Render.com bepul tarifida veb-servislar 15 daqiqa faoliyatsizlikdan keyin uxlab qoladi. Bizning botimizda ichki **HTTP Web Server** mavjud bo'lib, **UptimeRobot** orqali uni har 5 daqiqada uyg'otib turish evaziga **24/7 to'xtovsiz** ishlaydi!

### Render.com ga yuklash bosqichlari:
1. Ushbu loyihani o'z GitHub hisobingizga yuklang (quyidagi Git ko'rsatmalariga qarang).
2. [Render.com](https://render.com) ga kiring va GitHub profilingiz orqali ro'yxatdan o'ting.
3. **New +** tugmasini bosing va **Web Service** ni tanlang.
4. O'zingizning bot repozitoriyangizni tanlang.
5. Sozlamalarni kiriting:
   - **Name:** `telegram-moderation-bot`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Instance Type:** `Free`
6. **Environment Variables** bo'limiga `.env` dagi barcha qiymatlarni qo'shing:
   - `BOT_TOKEN`
   - `ADMIN_IDS`
   - `GROUP_ID`
   - `LOG_CHANNEL_ID`
   - `DISCORD_URL`
   - `DATABASE_URL` (ixtiyoriy)
7. **Create Web Service** tugmasini bosing. Render botni o'rnatib, ishga tushiradi.
8. Render sizga servis havolasini beradi (masalan: `https://telegram-moderation-bot-xyz.onrender.com`).

---

## ⏱ UptimeRobot orqali 24/7 Faol Saqlash

1. [UptimeRobot.com](https://uptimerobot.com) saytiga bepul ro'yxatdan o'ting.
2. **Add New Monitor** tugmasini bosing:
   - **Monitor Type:** `HTTP(s)`
   - **Friendly Name:** `Telegram Bot Health`
   - **URL (or IP):** `https://sizning-servisingiz.onrender.com/health`
   - **Monitoring Interval:** `5 minutes`
3. **Create Monitor** tugmasini bosing.
Endi UptimeRobot har 5 daqiqada botingizga so'rov yuboradi va Render uni hech qachon o'chirib qo'ymaydi!

---

## 📦 GitHub ga Chiqarish Buyruqlari

Terminalda quyidagi buyruqlarni ketma-ket bajaring:

```bash
# 1. Gitni ishga tushirish (agar hali qilinmagan bo'lsa)
git init

# 2. Barcha fayllarni indekslash
git add .

# 3. Dastlabki commit
git commit -m "feat: Telegram guruh moderatsiya boti to'liq tayyor"

# 4. Asosiy tarmoqni 'main' deb belgilash
git branch -M main

# 5. GitHub'dagi repozitoriyangizni ulash
git remote add origin https://github.com/azoffuz/telegram-moderation-bot.git

# 6. Kodlarni GitHub'ga yuklash
git push -u origin main
```

---

## 🎛 Admin Panel va Adminlar Boshqaruvi

| Buyruq | Tavsif | Huquq |
| :--- | :--- | :--- |
| `/admin` yoki `/panel` | Interaktiv Admin Panelni ochish (sozlamalarni bitta tugma bilan yoqish/o'chirish) | Owner / Bot Admin |
| `/addadmin <ID> [Izoh]` | Botga yangi admin qo'shish (Bazada saqlanadi) | Faqat Owner |
| `/deladmin <ID>` | Adminni o'chirish | Faqat Owner |
| `/admins` | Barcha faol bot adminlarini ko'rish | Owner / Bot Admin |
| `/addword <so'z>` | Taqiqlangan so'z qo'shish (Blacklist) | Owner / Bot Admin |
| `/delword <so'z>` | Taqiqlangan so'zni o'chirish | Owner / Bot Admin |
| `/words` | Taqiqlangan so'zlar ro'yxatini ko'rish | Owner / Bot Admin |
| `/dailyreport` | Bugungi jonli moderatsiya hisobotini ko'rish | Owner / Bot Admin |
| `/broadcast <matn>` | Butun guruhga administratsiya nomidan rasmiy e'lon yuborish | Owner / Bot Admin |

---

## 📑 Guruh Moderatsiya Buyruqlari

| Buyruq | Tavsif | Misol |
| :--- | :--- | :--- |
| `/warn [sabab]` | Foydalanuvchiga ogohlantirish berish (reply) | `/warn Qoidalarni buzmang` |
| `/unwarn` | Oxirgi ogohlantirishni bekor qilish (reply) | `/unwarn` |
| `/warns` | Ogohlantirishlar sonini tekshirish (reply) | `/warns` |
| `/mute [vaqt] [sabab]` | Foydalanuvchini vaqtincha mute qilish | `/mute 2h So'kinish` |
| `/unmute` | Foydalanuvchidan cheklovni olish | `/unmute` |
| `/ban [sabab]` | Foydalanuvchini guruhdan butunlay chiqarish | `/ban Reklama` |
| `/unban [ID]` | Bandan chiqarish | `/unban 12345678` |
| `/kick [sabab]` | Guruhdan chiqarish | `/kick Tushunarsiz akkaunt` |
| `/clean [soni]` | Chatdagi xabarlarni o'chirish | `/clean 20` |
| `/nightmode on` | Guruhni yopish (faqat adminlar yoza oladi) | `/nightmode on` |
| `/nightmode off` | Guruhni ochish | `/nightmode off` |

---

## 👥 Foydalanuvchi Buyruqlari

| Buyruq | Tavsif |
| :--- | :--- |
| `/rules` | Guruh qoidalarini ko'rsatish |
| `/discord` | Rasmiy Discord serverga ulanish tugmasi |
| `/report [sabab]` | Qoidabuzar xabarga reply qilib moderatorlarga xabar berish |

---
*Loyiha muallifi: Antigravity AI Pair Programmer*
