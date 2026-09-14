import logging
import re
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import aiosqlite
import asyncpg
from bot.config import config

logger = logging.getLogger(__name__)

DEFAULT_BAD_WORDS = [
    "1xbet", "melbet", "mostbet", "linebet", "aviator", "kazino",
    "kassir", "kripto", "pul ishlash", "aloqa uchun", "18+",
    "qotoq", "sikish", "jalap", "fahiwa", "iflos", "haromi"
]

class Database:
    def __init__(self):
        self.is_postgres: bool = False
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.sqlite_path: str = "moderation.db"
        self.sqlite_conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Ma'lumotlar bazasiga ulanish va jadvallarni yaratish."""
        db_url = config.DATABASE_URL

        if db_url and ("postgres" in db_url or "supabase" in db_url):
            self.is_postgres = True
            # asyncpg uchun moslash
            if db_url.startswith("postgresql+asyncpg://"):
                db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
            elif db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            
            try:
                self.pg_pool = await asyncpg.create_pool(dsn=db_url, min_size=1, max_size=5)
                logger.info("Supabase (PostgreSQL) bazasiga muvaffaqiyatli ulandi.")
            except Exception as e:
                logger.error(f"PostgreSQL ulanishida xatolik, SQLite ga o'tilmoqda: {e}")
                self.is_postgres = False

        if not self.is_postgres:
            self.sqlite_conn = await aiosqlite.connect(self.sqlite_path)
            logger.info("Mahalliy SQLite bazasiga muvaffaqiyatli ulandi.")

        await self._init_tables()
        await self._seed_default_bad_words()

    async def _init_tables(self):
        """Jadvallarni yaratish (agar mavjud bo'lmasa)."""
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS warnings (
                        user_id BIGINT,
                        chat_id BIGINT,
                        count INT DEFAULT 0,
                        last_reason TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, chat_id)
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS bot_admins (
                        user_id BIGINT PRIMARY KEY,
                        added_by BIGINT,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        title TEXT DEFAULT 'Admin'
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS chat_settings (
                        chat_id BIGINT PRIMARY KEY,
                        night_mode BOOLEAN DEFAULT FALSE,
                        anti_link BOOLEAN DEFAULT TRUE,
                        anti_forward BOOLEAN DEFAULT TRUE,
                        anti_flood BOOLEAN DEFAULT TRUE,
                        captcha_enabled BOOLEAN DEFAULT TRUE,
                        service_cleaner BOOLEAN DEFAULT TRUE,
                        anti_badwords BOOLEAN DEFAULT TRUE,
                        anti_arabic BOOLEAN DEFAULT TRUE,
                        newcomer_media_lock BOOLEAN DEFAULT TRUE,
                        probation_minutes INT DEFAULT 60
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS bad_words (
                        word TEXT PRIMARY KEY,
                        added_by BIGINT,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS newcomers (
                        user_id BIGINT,
                        chat_id BIGINT,
                        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, chat_id)
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS daily_stats (
                        stat_date DATE,
                        stat_type TEXT,
                        count INT DEFAULT 0,
                        PRIMARY KEY (stat_date, stat_type)
                    );
                """)
        else:
            await self.sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    user_id INTEGER,
                    chat_id INTEGER,
                    count INTEGER DEFAULT 0,
                    last_reason TEXT,
                    updated_at TIMESTAMP,
                    PRIMARY KEY (user_id, chat_id)
                );
            """)
            await self.sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    added_at TIMESTAMP,
                    title TEXT DEFAULT 'Admin'
                );
            """)
            await self.sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_settings (
                    chat_id INTEGER PRIMARY KEY,
                    night_mode BOOLEAN DEFAULT 0,
                    anti_link BOOLEAN DEFAULT 1,
                    anti_forward BOOLEAN DEFAULT 1,
                    anti_flood BOOLEAN DEFAULT 1,
                    captcha_enabled BOOLEAN DEFAULT 1,
                    service_cleaner BOOLEAN DEFAULT 1,
                    anti_badwords BOOLEAN DEFAULT 1,
                    anti_arabic BOOLEAN DEFAULT 1,
                    newcomer_media_lock BOOLEAN DEFAULT 1,
                    probation_minutes INTEGER DEFAULT 60
                );
            """)
            await self.sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS bad_words (
                    word TEXT PRIMARY KEY,
                    added_by INTEGER,
                    added_at TIMESTAMP
                );
            """)
            await self.sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS newcomers (
                    user_id INTEGER,
                    chat_id INTEGER,
                    joined_at TIMESTAMP,
                    PRIMARY KEY (user_id, chat_id)
                );
            """)
            await self.sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    stat_date TEXT,
                    stat_type TEXT,
                    count INTEGER DEFAULT 0,
                    PRIMARY KEY (stat_date, stat_type)
                );
            """)
            await self.sqlite_conn.commit()

    async def _seed_default_bad_words(self):
        """Baza bo'sh bo'lsa standart taqiqlangan so'zlarni kiritadi."""
        existing = await self.get_all_bad_words()
        if not existing:
            for w in DEFAULT_BAD_WORDS:
                await self.add_bad_word(w, added_by=0)

    # ==================== ADMINLAR BOSHQARUVI ====================
    def is_owner(self, user_id: int) -> bool:
        """Foydalanuvchi asosiy bosh admin (Owner) ekanligini tekshiradi."""
        return user_id in config.ADMIN_IDS

    async def is_bot_admin(self, user_id: int) -> bool:
        """Foydalanuvchi Owner yoki bot orqali tayinlangan admin ekanligini tekshiradi."""
        if self.is_owner(user_id):
            return True

        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                val = await conn.fetchval(
                    "SELECT user_id FROM bot_admins WHERE user_id = $1", user_id
                )
                return val is not None
        else:
            async with self.sqlite_conn.execute(
                "SELECT user_id FROM bot_admins WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None

    async def add_bot_admin(self, user_id: int, added_by: int, title: str = "Admin") -> bool:
        """Yangi bot adminini qo'shadi."""
        now = datetime.now()
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO bot_admins (user_id, added_by, added_at, title)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id) DO UPDATE SET title = $4
                """, user_id, added_by, now, title)
        else:
            await self.sqlite_conn.execute("""
                INSERT INTO bot_admins (user_id, added_by, added_at, title)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET title = excluded.title
            """, (user_id, added_by, now, title))
            await self.sqlite_conn.commit()
        return True

    async def remove_bot_admin(self, user_id: int) -> bool:
        """Bot adminini o'chiradi."""
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                res = await conn.execute("DELETE FROM bot_admins WHERE user_id = $1", user_id)
                return "DELETE 1" in res
        else:
            async with self.sqlite_conn.execute(
                "DELETE FROM bot_admins WHERE user_id = ?", (user_id,)
            ) as cursor:
                await self.sqlite_conn.commit()
                return cursor.rowcount > 0

    async def get_all_bot_admins(self) -> List[Dict[str, Any]]:
        """Barcha qo'shilgan bot adminlarini ro'yxatini qaytaradi."""
        admins = []
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch("SELECT user_id, added_by, added_at, title FROM bot_admins ORDER BY added_at DESC")
                for r in rows:
                    admins.append({
                        "user_id": r["user_id"],
                        "added_by": r["added_by"],
                        "added_at": r["added_at"],
                        "title": r["title"]
                    })
        else:
            async with self.sqlite_conn.execute(
                "SELECT user_id, added_by, added_at, title FROM bot_admins ORDER BY added_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    admins.append({
                        "user_id": r[0],
                        "added_by": r[1],
                        "added_at": r[2],
                        "title": r[3]
                    })
        return admins

    # ==================== SOZLAMALAR (CHAT SETTINGS) ====================
    VALID_SETTINGS = {
        "night_mode": False,
        "anti_link": True,
        "anti_forward": True,
        "anti_flood": True,
        "captcha_enabled": True,
        "service_cleaner": True,
        "anti_badwords": True,
        "anti_arabic": True,
        "newcomer_media_lock": True,
    }

    async def get_chat_setting_bool(self, chat_id: int, setting_name: str, default: bool = True) -> bool:
        """Muayyan sozlamaning boolean holatini oladi."""
        if setting_name not in self.VALID_SETTINGS:
            return default

        query = f"SELECT {setting_name} FROM chat_settings WHERE chat_id = $1" if self.is_postgres else f"SELECT {setting_name} FROM chat_settings WHERE chat_id = ?"
        
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    val = await conn.fetchval(query, chat_id)
                    return bool(val) if val is not None else default
            else:
                async with self.sqlite_conn.execute(query, (chat_id,)) as cursor:
                    row = await cursor.fetchone()
                    return bool(row[0]) if row and row[0] is not None else default
        except Exception:
            return default

    async def set_chat_setting_bool(self, chat_id: int, setting_name: str, value: bool):
        """Muayyan sozlamani o'zgartiradi."""
        if setting_name not in self.VALID_SETTINGS:
            return

        val = value if self.is_postgres else (1 if value else 0)

        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                await conn.execute(f"""
                    INSERT INTO chat_settings (chat_id, {setting_name})
                    VALUES ($1, $2)
                    ON CONFLICT (chat_id) DO UPDATE SET {setting_name} = $2
                """, chat_id, val)
        else:
            await self.sqlite_conn.execute(f"""
                INSERT INTO chat_settings (chat_id, {setting_name})
                VALUES (?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET {setting_name} = excluded.{setting_name}
            """, (chat_id, val))
            await self.sqlite_conn.commit()

    async def toggle_chat_setting(self, chat_id: int, setting_name: str) -> bool:
        """Sozlamani ON -> OFF yoki OFF -> ON qilib, yangi qiymatini qaytaradi."""
        current = await self.get_chat_setting_bool(chat_id, setting_name, self.VALID_SETTINGS.get(setting_name, True))
        new_val = not current
        await self.set_chat_setting_bool(chat_id, setting_name, new_val)
        return new_val

    async def get_all_chat_settings(self, chat_id: int) -> Dict[str, bool]:
        """Guruhning barcha sozlamalarini lug'at ko'rinishida qaytaradi."""
        res = {}
        for k, def_val in self.VALID_SETTINGS.items():
            res[k] = await self.get_chat_setting_bool(chat_id, k, def_val)
        return res

    # ==================== TAQIQLANGAN SO'ZLAR (BAD WORDS) ====================
    async def add_bad_word(self, word: str, added_by: int = 0) -> bool:
        """Taqiqlangan so'z qo'shadi."""
        cleaned_word = word.strip().lower()
        if not cleaned_word:
            return False
        now = datetime.now()
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO bad_words (word, added_by, added_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (word) DO NOTHING
                """, cleaned_word, added_by, now)
        else:
            await self.sqlite_conn.execute("""
                INSERT OR IGNORE INTO bad_words (word, added_by, added_at)
                VALUES (?, ?, ?)
            """, (cleaned_word, added_by, now))
            await self.sqlite_conn.commit()
        return True

    async def remove_bad_word(self, word: str) -> bool:
        """Taqiqlangan so'zni o'chiradi."""
        cleaned_word = word.strip().lower()
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                res = await conn.execute("DELETE FROM bad_words WHERE word = $1", cleaned_word)
                return "DELETE 1" in res
        else:
            async with self.sqlite_conn.execute("DELETE FROM bad_words WHERE word = ?", (cleaned_word,)) as cursor:
                await self.sqlite_conn.commit()
                return cursor.rowcount > 0

    async def get_all_bad_words(self) -> List[str]:
        """Barcha taqiqlangan so'zlar ro'yxatini qaytaradi."""
        words = []
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch("SELECT word FROM bad_words ORDER BY word ASC")
                words = [r["word"] for r in rows]
        else:
            async with self.sqlite_conn.execute("SELECT word FROM bad_words ORDER BY word ASC") as cursor:
                rows = await cursor.fetchall()
                words = [r[0] for r in rows]
        return words

    async def check_bad_words_in_text(self, text: str) -> Optional[str]:
        """Matnda taqiqlangan so'z borligini tekshiradi va topilgan so'zni qaytaradi."""
        if not text:
            return None
        words = await self.get_all_bad_words()
        lowered = text.lower()
        for w in words:
            # So'z to'liq yoki so'z sifatida qatnashganini tekshiramiz
            pattern = re.escape(w)
            if re.search(pattern, lowered):
                return w
        return None

    # ==================== YANGI A'ZOLAR SINOV MUDDATI ====================
    async def record_newcomer(self, user_id: int, chat_id: int):
        """Yangi a'zo qo'shilgan vaqtini yozadi."""
        now = datetime.now()
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO newcomers (user_id, chat_id, joined_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, chat_id) DO UPDATE SET joined_at = $3
                """, user_id, chat_id, now)
        else:
            await self.sqlite_conn.execute("""
                INSERT INTO newcomers (user_id, chat_id, joined_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET joined_at = excluded.joined_at
            """, (user_id, chat_id, now))
            await self.sqlite_conn.commit()

    async def is_in_probation(self, user_id: int, chat_id: int, probation_minutes: int = 60) -> bool:
        """Foydalanuvchi hali sinov muddatida (masalan, dastlabki 60 daqiqada) ekanligini tekshiradi."""
        joined_at = None
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                val = await conn.fetchval(
                    "SELECT joined_at FROM newcomers WHERE user_id = $1 AND chat_id = $2",
                    user_id, chat_id
                )
                joined_at = val
        else:
            async with self.sqlite_conn.execute(
                "SELECT joined_at FROM newcomers WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    if isinstance(row[0], str):
                        try:
                            joined_at = datetime.fromisoformat(row[0])
                        except Exception:
                            joined_at = None
                    else:
                        joined_at = row[0]

        if not joined_at:
            return False

        elapsed = (datetime.now() - joined_at).total_seconds() / 60.0
        return elapsed < probation_minutes

    # ==================== KUNLIK STATISTIKA (DAILY STATS) ====================
    async def increment_stat(self, stat_type: str, count: int = 1):
        """Bugungi statistika hisoblagichini oshiradi."""
        today_str = date.today().isoformat()
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO daily_stats (stat_date, stat_type, count)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (stat_date, stat_type)
                    DO UPDATE SET count = daily_stats.count + $3
                """, date.today(), stat_type, count)
        else:
            await self.sqlite_conn.execute("""
                INSERT INTO daily_stats (stat_date, stat_type, count)
                VALUES (?, ?, ?)
                ON CONFLICT(stat_date, stat_type)
                DO UPDATE SET count = daily_stats.count + ?
            """, (today_str, stat_type, count, count))
            await self.sqlite_conn.commit()

    async def get_today_stats() -> Dict[str, int]:
        """Bugungi statistika ma'lumotlarini qaytaradi."""
        pass # To be defined inside class below

    async def get_stats_for_date(self, target_date: Optional[date] = None) -> Dict[str, int]:
        """Muayyan kun bo'yicha statistikani qaytaradi."""
        d = target_date or date.today()
        stats = {
            "links_deleted": 0,
            "forwards_deleted": 0,
            "badwords_deleted": 0,
            "arabic_deleted": 0,
            "media_blocked": 0,
            "mutes_count": 0,
            "warns_count": 0,
            "joins_count": 0
        }
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch("SELECT stat_type, count FROM daily_stats WHERE stat_date = $1", d)
                for r in rows:
                    stats[r["stat_type"]] = r["count"]
        else:
            d_str = d.isoformat()
            async with self.sqlite_conn.execute("SELECT stat_type, count FROM daily_stats WHERE stat_date = ?", (d_str,)) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    stats[r[0]] = r[1]
        return stats

    # ==================== OGOHLANTIRISHLAR (WARNS) ====================
    async def get_warn_count(self, user_id: int, chat_id: int) -> int:
        """Foydalanuvchining ogohlantirishlar sonini qaytaradi."""
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                val = await conn.fetchval(
                    "SELECT count FROM warnings WHERE user_id = $1 AND chat_id = $2",
                    user_id, chat_id
                )
                return val or 0
        else:
            async with self.sqlite_conn.execute(
                "SELECT count FROM warnings WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def add_warn(self, user_id: int, chat_id: int, reason: str = "") -> int:
        """Foydalanuvchiga bitta warn qo'shadi va yangi sonini qaytaradi."""
        current = await self.get_warn_count(user_id, chat_id)
        new_count = current + 1
        now = datetime.now()

        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO warnings (user_id, chat_id, count, last_reason, updated_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id, chat_id)
                    DO UPDATE SET count = $3, last_reason = $4, updated_at = $5
                """, user_id, chat_id, new_count, reason, now)
        else:
            await self.sqlite_conn.execute("""
                INSERT INTO warnings (user_id, chat_id, count, last_reason, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, chat_id)
                DO UPDATE SET count = excluded.count, last_reason = excluded.last_reason, updated_at = excluded.updated_at
            """, (user_id, chat_id, new_count, reason, now))
            await self.sqlite_conn.commit()

        await self.increment_stat("warns_count")
        return new_count

    async def remove_warn(self, user_id: int, chat_id: int) -> int:
        """Foydalanuvchidan bitta warn kamaytiradi."""
        current = await self.get_warn_count(user_id, chat_id)
        new_count = max(0, current - 1)
        now = datetime.now()

        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE warnings SET count = $1, updated_at = $2
                    WHERE user_id = $3 AND chat_id = $4
                """, new_count, now, user_id, chat_id)
        else:
            await self.sqlite_conn.execute("""
                UPDATE warnings SET count = ?, updated_at = ?
                WHERE user_id = ? AND chat_id = ?
            """, (new_count, now, user_id, chat_id))
            await self.sqlite_conn.commit()

        return new_count

    async def reset_warns(self, user_id: int, chat_id: int):
        """Foydalanuvchi ogohlantirishlarini 0 ga tushiradi."""
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM warnings WHERE user_id = $1 AND chat_id = $2",
                    user_id, chat_id
                )
        else:
            await self.sqlite_conn.execute(
                "DELETE FROM warnings WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )
            await self.sqlite_conn.commit()

    async def get_total_warns_count(self) -> int:
        """Baza bo'yicha jami berilgan warnlar sonini hisoblaydi."""
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    val = await conn.fetchval("SELECT SUM(count) FROM warnings")
                    return val or 0
            else:
                async with self.sqlite_conn.execute("SELECT SUM(count) FROM warnings") as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row and row[0] else 0
        except Exception:
            return 0

    # ==================== TUNGI REJIM ====================
    async def get_night_mode(self, chat_id: int) -> bool:
        """Tungi rejim holatini qaytaradi."""
        return await self.get_chat_setting_bool(chat_id, "night_mode", default=False)

    async def set_night_mode(self, chat_id: int, enabled: bool):
        """Tungi rejim holatini saqlaydi."""
        await self.set_chat_setting_bool(chat_id, "night_mode", enabled)

    async def close(self):
        """Baza ulanishini xavfsiz yopish."""
        if self.pg_pool:
            await self.pg_pool.close()
        if self.sqlite_conn:
            await self.sqlite_conn.close()

db = Database()
