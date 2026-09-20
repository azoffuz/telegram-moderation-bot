import logging
import re
import time
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Set, Tuple
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

        # Tezkor In-Memory Keshlar (Latency va DB yuklamasini 99% ga kamaytirish uchun)
        self._settings_cache: Dict[int, Dict[str, Any]] = {}
        self._settings_cache_ts: Dict[int, float] = {}
        self._bot_admins_cache: Optional[Set[int]] = None
        self._bad_words_cache: Optional[List[str]] = None
        self._bad_words_bounded_regex: Optional[re.Pattern] = None
        self._bad_words_unbounded_regex: Optional[re.Pattern] = None
        self._known_users_cache: Dict[int, Tuple[float, Optional[str], str]] = {}
        self._tracked_members_cache: Set[Tuple[int, int]] = set()
        self._newcomers_cache: Dict[Tuple[int, int], Optional[datetime]] = {}
        self._log_threads_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._daily_activity_cache: Dict[Tuple[int, int, str], Tuple[int, bool]] = {}

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
                self.pg_pool = await asyncpg.create_pool(
                    dsn=db_url,
                    min_size=2,
                    max_size=10,
                    statement_cache_size=0
                )
                logger.info("Supabase (PostgreSQL) bazasiga muvaffaqiyatli ulandi.")
            except Exception as e1:
                logger.warning(f"Standart PostgreSQL ulanishda xatolik ({e1}), ssl='require' bilan qayta urinilmoqda...")
                try:
                    self.pg_pool = await asyncpg.create_pool(
                        dsn=db_url,
                        ssl="require",
                        min_size=2,
                        max_size=10,
                        statement_cache_size=0
                    )
                    logger.info("Supabase (PostgreSQL) bazasiga SSL bilan muvaffaqiyatli ulandi.")
                except Exception as e2:
                    logger.error(f"PostgreSQL ulanishida yakuniy xatolik, SQLite ga o'tilmoqda: {e2}")
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
                        anti_custom_emoji BOOLEAN DEFAULT TRUE,
                        anti_location BOOLEAN DEFAULT FALSE,
                        auto_slowmode BOOLEAN DEFAULT FALSE,
                        probation_minutes INT DEFAULT 60,
                        gmt_offset INT DEFAULT 5,
                        nightmode_auto BOOLEAN DEFAULT FALSE,
                        nightmode_start_hour INT DEFAULT 23,
                        nightmode_end_hour INT DEFAULT 7,
                        last_auto_nightmode_action TEXT DEFAULT NULL
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
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS known_users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        full_name TEXT,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS group_members (
                        chat_id BIGINT,
                        user_id BIGINT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (chat_id, user_id)
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_daily_activity (
                        chat_id BIGINT,
                        user_id BIGINT,
                        activity_date TEXT,
                        message_count INT DEFAULT 1,
                        is_active_granted BOOLEAN DEFAULT FALSE,
                        PRIMARY KEY (chat_id, user_id, activity_date)
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
                    anti_custom_emoji BOOLEAN DEFAULT 1,
                    anti_location BOOLEAN DEFAULT 0,
                    auto_slowmode BOOLEAN DEFAULT 0,
                    probation_minutes INTEGER DEFAULT 60,
                    gmt_offset INTEGER DEFAULT 5,
                    nightmode_auto BOOLEAN DEFAULT 0,
                    nightmode_start_hour INTEGER DEFAULT 23,
                    nightmode_end_hour INTEGER DEFAULT 7,
                    last_auto_nightmode_action TEXT DEFAULT NULL
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
            await self.sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS known_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await self.sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS group_members (
                    chat_id INTEGER,
                    user_id INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
            await self.sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS user_daily_activity (
                    chat_id INTEGER,
                    user_id INTEGER,
                    activity_date TEXT,
                    message_count INTEGER DEFAULT 1,
                    is_active_granted BOOLEAN DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id, activity_date)
                );
            """)
            await self.sqlite_conn.commit()

        # Mavjud bazalar uchun xavfsiz ustun qo'shish (Migration)
        migrations = [
            ("anti_custom_emoji", "BOOLEAN DEFAULT TRUE", "BOOLEAN DEFAULT 1"),
            ("anti_location", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
            ("auto_slowmode", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
            ("captcha_timeout", "INT DEFAULT 90", "INTEGER DEFAULT 90"),
            ("flood_mute_minutes", "INT DEFAULT 10", "INTEGER DEFAULT 10"),
            ("auto_delete_seconds", "INT DEFAULT 20", "INTEGER DEFAULT 20"),
            ("max_warns", "INT DEFAULT 3", "INTEGER DEFAULT 3"),
            ("last_discord_message_id", "BIGINT DEFAULT 0", "INTEGER DEFAULT 0"),
            ("daytime_permissions", "TEXT DEFAULT NULL", "TEXT DEFAULT NULL"),
            ("gmt_offset", "INT DEFAULT 5", "INTEGER DEFAULT 5"),
            ("nightmode_auto", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
            ("nightmode_start_hour", "INT DEFAULT 23", "INTEGER DEFAULT 23"),
            ("nightmode_end_hour", "INT DEFAULT 7", "INTEGER DEFAULT 7"),
            ("last_auto_nightmode_action", "TEXT DEFAULT NULL", "TEXT DEFAULT NULL"),
            ("active_tag_enabled", "BOOLEAN DEFAULT TRUE", "BOOLEAN DEFAULT 1"),
            ("active_tag_threshold", "INT DEFAULT 10", "INTEGER DEFAULT 10"),
        ]
        for col, pg_type, sq_type in migrations:
            try:
                if self.is_postgres and self.pg_pool:
                    async with self.pg_pool.acquire() as conn:
                        await conn.execute(f"ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS {col} {pg_type};")
                elif self.sqlite_conn:
                    await self.sqlite_conn.execute(f"ALTER TABLE chat_settings ADD COLUMN {col} {sq_type};")
                    await self.sqlite_conn.commit()
            except Exception:
                pass

        # log_threads jadvalini yaratish (mavjud bazalar uchun ham)
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS log_threads (
                            category TEXT PRIMARY KEY,
                            channel_id BIGINT,
                            thread_id BIGINT,
                            thread_name TEXT,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute("""
                    CREATE TABLE IF NOT EXISTS log_threads (
                        category TEXT PRIMARY KEY,
                        channel_id INTEGER,
                        thread_id INTEGER,
                        thread_name TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                await self.sqlite_conn.commit()
        except Exception:
            pass

        # user_daily_activity jadvalini yaratish (mavjud bazalar uchun ham)
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS user_daily_activity (
                            chat_id BIGINT,
                            user_id BIGINT,
                            activity_date TEXT,
                            message_count INT DEFAULT 1,
                            is_active_granted BOOLEAN DEFAULT FALSE,
                            PRIMARY KEY (chat_id, user_id, activity_date)
                        );
                    """)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_daily_activity (
                        chat_id INTEGER,
                        user_id INTEGER,
                        activity_date TEXT,
                        message_count INTEGER DEFAULT 1,
                        is_active_granted BOOLEAN DEFAULT 0,
                        PRIMARY KEY (chat_id, user_id, activity_date)
                    );
                """)
                await self.sqlite_conn.commit()
        except Exception:
            pass

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

    async def _load_bot_admins_cache(self):
        """Barcha bot adminlari ID larini in-memory set keshiga yuklaydi."""
        admin_ids = set()
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    rows = await conn.fetch("SELECT user_id FROM bot_admins")
                    for r in rows:
                        admin_ids.add(r["user_id"])
            elif self.sqlite_conn:
                async with self.sqlite_conn.execute("SELECT user_id FROM bot_admins") as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        admin_ids.add(r[0])
        except Exception as e:
            logger.debug(f"_load_bot_admins_cache xatosi: {e}")
        self._bot_admins_cache = admin_ids

    async def is_bot_admin(self, user_id: int) -> bool:
        """Foydalanuvchi Owner yoki bot orqali tayinlangan admin ekanligini tezkor RAM keshdan tekshiradi (0ms)."""
        if self.is_owner(user_id):
            return True

        if self._bot_admins_cache is None:
            await self._load_bot_admins_cache()

        return user_id in self._bot_admins_cache

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

        if self._bot_admins_cache is not None:
            self._bot_admins_cache.add(user_id)
        return True

    async def remove_bot_admin(self, user_id: int) -> bool:
        """Bot adminini o'chiradi."""
        success = False
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                res = await conn.execute("DELETE FROM bot_admins WHERE user_id = $1", user_id)
                success = "DELETE 1" in res
        else:
            async with self.sqlite_conn.execute(
                "DELETE FROM bot_admins WHERE user_id = ?", (user_id,)
            ) as cursor:
                await self.sqlite_conn.commit()
                success = cursor.rowcount > 0

        if success and self._bot_admins_cache is not None:
            self._bot_admins_cache.discard(user_id)
        return success

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
        "nightmode_auto": False,
        "anti_link": True,
        "anti_forward": True,
        "anti_flood": True,
        "captcha_enabled": True,
        "service_cleaner": True,
        "anti_badwords": True,
        "anti_arabic": True,
        "newcomer_media_lock": True,
        "anti_custom_emoji": True,
        "anti_location": False,
        "auto_slowmode": False,
        "active_tag_enabled": True,
    }

    async def get_all_chat_settings(self, chat_id: int) -> Dict[str, Any]:
        """Guruhning barcha sozlamalarini tezkor RAM keshdan yoki bitta DB so'rov bilan oladi."""
        now = time.time()
        if chat_id in self._settings_cache and (now - self._settings_cache_ts.get(chat_id, 0) < 60):
            return dict(self._settings_cache[chat_id])

        res = dict(self.VALID_SETTINGS)
        res.update(self.VALID_INT_SETTINGS)
        res["last_auto_nightmode_action"] = ""

        query = "SELECT * FROM chat_settings WHERE chat_id = $1" if self.is_postgres else "SELECT * FROM chat_settings WHERE chat_id = ?"
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    row = await conn.fetchrow(query, chat_id)
                    if row:
                        for k in row.keys():
                            if k != "chat_id" and row[k] is not None:
                                res[k] = row[k]
            elif self.sqlite_conn:
                self.sqlite_conn.row_factory = aiosqlite.Row
                async with self.sqlite_conn.execute(query, (chat_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        for k in row.keys():
                            if k != "chat_id" and row[k] is not None:
                                res[k] = row[k]
        except Exception as e:
            logger.debug(f"get_all_chat_settings xatosi: {e}")

        self._settings_cache[chat_id] = res
        self._settings_cache_ts[chat_id] = now
        return dict(res)

    async def get_chat_setting_bool(self, chat_id: int, setting_name: str, default: bool = True) -> bool:
        """Muayyan sozlamaning boolean holatini oladi (RAM keshdan, 0ms)."""
        settings = await self.get_all_chat_settings(chat_id)
        return bool(settings.get(setting_name, default))

    async def set_chat_setting_bool(self, chat_id: int, setting_name: str, value: bool):
        """Muayyan sozlamani o'zgartiradi va keshni yangilaydi."""
        if setting_name not in self.VALID_SETTINGS:
            return

        # RAM keshni tezda yangilaymiz (0ms delay)
        if chat_id in self._settings_cache:
            self._settings_cache[chat_id][setting_name] = value

        val = value if self.is_postgres else (1 if value else 0)
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(f"""
                        INSERT INTO chat_settings (chat_id, {setting_name})
                        VALUES ($1, $2)
                        ON CONFLICT (chat_id) DO UPDATE SET {setting_name} = $2
                    """, chat_id, val)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute(f"""
                    INSERT INTO chat_settings (chat_id, {setting_name})
                    VALUES (?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET {setting_name} = excluded.{setting_name}
                """, (chat_id, val))
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.error(f"set_chat_setting_bool xatosi: {e}")

    async def toggle_chat_setting(self, chat_id: int, setting_name: str) -> bool:
        """Sozlamani ON -> OFF yoki OFF -> ON qilib, yangi qiymatini qaytaradi."""
        current = await self.get_chat_setting_bool(chat_id, setting_name, self.VALID_SETTINGS.get(setting_name, True))
        new_val = not current
        await self.set_chat_setting_bool(chat_id, setting_name, new_val)
        return new_val

    VALID_INT_SETTINGS = {
        "probation_minutes": 60,
        "captcha_timeout": 90,
        "flood_mute_minutes": 10,
        "auto_delete_seconds": 20,
        "max_warns": 3,
        "last_discord_message_id": 0,
        "gmt_offset": 5,
        "nightmode_start_hour": 23,
        "nightmode_end_hour": 7,
        "active_tag_threshold": 10,
    }

    async def get_chat_setting_int(self, chat_id: int, setting_name: str, default: Optional[int] = None) -> int:
        """Muayyan sozlamaning butun son (int) qiymatini oladi (RAM keshdan)."""
        if default is None:
            default = self.VALID_INT_SETTINGS.get(setting_name, 0)

        settings = await self.get_all_chat_settings(chat_id)
        val = settings.get(setting_name, default)
        try:
            return int(val) if val is not None else default
        except Exception:
            return default

    async def set_chat_setting_int(self, chat_id: int, setting_name: str, value: int):
        """Muayyan butun sonli sozlamani o'zgartiradi va keshni yangilaydi."""
        if setting_name not in self.VALID_INT_SETTINGS:
            return

        if chat_id in self._settings_cache:
            self._settings_cache[chat_id][setting_name] = value

        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(f"""
                        INSERT INTO chat_settings (chat_id, {setting_name})
                        VALUES ($1, $2)
                        ON CONFLICT (chat_id) DO UPDATE SET {setting_name} = $2
                    """, chat_id, value)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute(f"""
                    INSERT INTO chat_settings (chat_id, {setting_name})
                    VALUES (?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET {setting_name} = excluded.{setting_name}
                """, (chat_id, value))
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.error(f"set_chat_setting_int xatosi: {e}")

    VALID_STR_SETTINGS = {
        "last_auto_nightmode_action",
    }

    async def get_chat_setting_str(self, chat_id: int, setting_name: str, default: str = "") -> str:
        """Muayyan sozlamaning matn (str) qiymatini oladi (RAM keshdan)."""
        settings = await self.get_all_chat_settings(chat_id)
        val = settings.get(setting_name, default)
        return str(val) if val is not None else default

    async def set_chat_setting_str(self, chat_id: int, setting_name: str, value: str):
        """Muayyan matnli sozlamani o'zgartiradi va keshni yangilaydi."""
        if setting_name not in self.VALID_STR_SETTINGS:
            return

        if chat_id in self._settings_cache:
            self._settings_cache[chat_id][setting_name] = value

        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(f"""
                        INSERT INTO chat_settings (chat_id, {setting_name})
                        VALUES ($1, $2)
                        ON CONFLICT (chat_id) DO UPDATE SET {setting_name} = $2
                    """, chat_id, value)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute(f"""
                    INSERT INTO chat_settings (chat_id, {setting_name})
                    VALUES (?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET {setting_name} = excluded.{setting_name}
                """, (chat_id, value))
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.error(f"set_chat_setting_str xatosi: {e}")

    async def get_gmt_offset(self, chat_id: int) -> int:
        """Guruh uchun sozlangan GMT mintaqasini oladi (Sukut bo'yicha: GMT+5)."""
        return await self.get_chat_setting_int(chat_id, "gmt_offset", default=5)

    async def set_gmt_offset(self, chat_id: int, offset: int):
        """Guruh uchun GMT mintaqasini o'zgartiradi (masalan: +5, +3)."""
        # Cheklov: -12 dan +14 gacha
        clamped = max(-12, min(14, offset))
        await self.set_chat_setting_int(chat_id, "gmt_offset", clamped)

    async def get_auto_nightmode_settings(self, chat_id: int) -> Dict[str, Any]:
        """Tungi rejim va GMT sozlamalarini to'liq to'plamda oladi."""
        is_auto = await self.get_chat_setting_bool(chat_id, "nightmode_auto", default=False)
        gmt = await self.get_gmt_offset(chat_id)
        start_h = await self.get_chat_setting_int(chat_id, "nightmode_start_hour", default=23)
        end_h = await self.get_chat_setting_int(chat_id, "nightmode_end_hour", default=7)
        is_night = await self.get_night_mode(chat_id)
        return {
            "auto_enabled": is_auto,
            "gmt_offset": gmt,
            "start_hour": start_h,
            "end_hour": end_h,
            "is_night": is_night,
        }

    # ==================== TAQIQLANGAN SO'ZLAR (BAD WORDS) ====================
    def _rebuild_bad_words_regex(self):
        """Taqiqlangan so'zlardan oldindan kompilyatsiya qilingan tezkor regex yasaydi."""
        if not self._bad_words_cache:
            self._bad_words_bounded_regex = None
            self._bad_words_unbounded_regex = None
            return

        letters_pattern = r'[a-zA-Zа-яА-ЯёЁўқғҳЎҚҒҲ0-9]'
        bounded_words = []
        unbounded_words = []

        for w in self._bad_words_cache:
            w_clean = w.strip().lower()
            if not w_clean or len(w_clean) < 2:
                continue
            esc = re.escape(w_clean)
            if len(w_clean) < 5 or ' ' in w_clean:
                bounded_words.append(esc)
            else:
                unbounded_words.append(esc)

        if bounded_words:
            # So'zning oldidan ham, ketidan ham harf kelmasligi SHART (salam, tamom, yordam xato o'chmasligi uchun)
            p_bounded = rf'(?<!{letters_pattern})(?:{"|".join(bounded_words)})(?!{letters_pattern})'
            self._bad_words_bounded_regex = re.compile(p_bounded, re.IGNORECASE)
        else:
            self._bad_words_bounded_regex = None

        if unbounded_words:
            # Oldidan harf kelmasligi shart, orqasidan esa qo'shimcha (1xbetda, jalablar) kelishi mumkin
            p_unbounded = rf'(?<!{letters_pattern})(?:{"|".join(unbounded_words)})'
            self._bad_words_unbounded_regex = re.compile(p_unbounded, re.IGNORECASE)
        else:
            self._bad_words_unbounded_regex = None

    async def add_bad_word(self, word: str, added_by: int = 0) -> bool:
        """Taqiqlangan so'z qo'shadi va keshni yangilaydi."""
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

        if self._bad_words_cache is not None and cleaned_word not in self._bad_words_cache:
            self._bad_words_cache.append(cleaned_word)
            self._bad_words_cache.sort()
            self._rebuild_bad_words_regex()
        return True

    async def remove_bad_word(self, word: str) -> bool:
        """Taqiqlangan so'zni o'chiradi va keshni yangilaydi."""
        cleaned_word = word.strip().lower()
        success = False
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                res = await conn.execute("DELETE FROM bad_words WHERE word = $1", cleaned_word)
                success = "DELETE 1" in res
        else:
            async with self.sqlite_conn.execute("DELETE FROM bad_words WHERE word = ?", (cleaned_word,)) as cursor:
                await self.sqlite_conn.commit()
                success = cursor.rowcount > 0

        if success and self._bad_words_cache is not None:
            if cleaned_word in self._bad_words_cache:
                self._bad_words_cache.remove(cleaned_word)
                self._rebuild_bad_words_regex()
        return success

    async def get_all_bad_words(self) -> List[str]:
        """Barcha taqiqlangan so'zlar ro'yxatini qaytaradi (RAM keshdan, 0ms)."""
        if self._bad_words_cache is not None:
            return list(self._bad_words_cache)

        words = []
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch("SELECT word FROM bad_words ORDER BY word ASC")
                words = [r["word"] for r in rows]
        else:
            async with self.sqlite_conn.execute("SELECT word FROM bad_words ORDER BY word ASC") as cursor:
                rows = await cursor.fetchall()
                words = [r[0] for r in rows]

        self._bad_words_cache = words
        self._rebuild_bad_words_regex()
        return list(words)

    async def check_bad_words_in_text(self, text: str) -> Optional[str]:
        """Matnda taqiqlangan so'z borligini tezkor pre-compiled regex bilan tekshiradi (0.05ms)."""
        if not text:
            return None

        if self._bad_words_cache is None:
            await self.get_all_bad_words()

        if not self._bad_words_bounded_regex and not self._bad_words_unbounded_regex:
            return None

        lowered = text.lower()
        # 3 ta va undan ortiq takrorlangan harflarni siqish (masalan: aaaam -> am, saloooom -> salom)
        compressed = re.sub(r'([a-zA-Zа-яА-ЯёЁўқғҳЎҚҒҲ])\1{2,}', r'\1', lowered)

        for target in (lowered, compressed):
            if self._bad_words_bounded_regex:
                m = self._bad_words_bounded_regex.search(target)
                if m:
                    return m.group(0)
            if self._bad_words_unbounded_regex:
                m = self._bad_words_unbounded_regex.search(target)
                if m:
                    return m.group(0)

        return None

    # ==================== YANGI A'ZOLAR SINOV MUDDATI ====================
    async def record_newcomer(self, user_id: int, chat_id: int):
        """Yangi a'zo qo'shilgan vaqtini yozadi."""
        now = datetime.now()
        self._newcomers_cache[(user_id, chat_id)] = now

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
        pair = (user_id, chat_id)
        if pair in self._newcomers_cache:
            joined_at = self._newcomers_cache[pair]
            if not joined_at:
                return False
            elapsed = (datetime.now() - joined_at).total_seconds() / 60.0
            return elapsed < probation_minutes

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

        self._newcomers_cache[pair] = joined_at
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
            "custom_emoji_deleted": 0,
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

    async def save_daytime_permissions(self, chat_id: int, perms: Dict[str, Any]):
        """Kunduzgi guruh huquqlari nusxasini bazada saqlaydi."""
        import json
        raw = json.dumps(perms)
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO chat_settings (chat_id, daytime_permissions)
                        VALUES ($1, $2)
                        ON CONFLICT (chat_id) DO UPDATE SET daytime_permissions = $2
                    """, chat_id, raw)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute("""
                    INSERT INTO chat_settings (chat_id, daytime_permissions)
                    VALUES (?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET daytime_permissions = excluded.daytime_permissions
                """, (chat_id, raw))
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.debug(f"save_daytime_permissions xatosi: {e}")

    async def get_daytime_permissions(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Bazadan saqlangan kunduzgi huquqlarni oladi."""
        import json
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    val = await conn.fetchval(
                        "SELECT daytime_permissions FROM chat_settings WHERE chat_id = $1",
                        chat_id
                    )
                    if val:
                        return json.loads(val)
            elif self.sqlite_conn:
                async with self.sqlite_conn.execute(
                    "SELECT daytime_permissions FROM chat_settings WHERE chat_id = ?",
                    (chat_id,)
                ) as cur:
                    row = await cur.fetchone()
                    if row and row[0]:
                        return json.loads(row[0])
        except Exception as e:
            logger.debug(f"get_daytime_permissions xatosi: {e}")
        return None

    # ==================== FOYDALANUVCHILARNI RO'YXATGA OLISH (KNOWN USERS) ====================
    async def save_known_user(self, user_id: int, username: Optional[str], full_name: str):
        """Foydalanuvchi ma'lumotlarini saqlash yoki yangilash (Throttled: 10 daqiqada 1 marta)."""
        u_clean = username.lower().lstrip("@") if username else None
        now_ts = time.time()

        if user_id in self._known_users_cache:
            last_ts, old_u, old_name = self._known_users_cache[user_id]
            if (now_ts - last_ts < 600) and (old_u == u_clean) and (old_name == full_name):
                return

        self._known_users_cache[user_id] = (now_ts, u_clean, full_name)
        now = datetime.now()
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO known_users (user_id, username, full_name, last_seen)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (user_id) DO UPDATE 
                        SET username = COALESCE($2, known_users.username),
                            full_name = $3,
                            last_seen = $4
                    """, user_id, u_clean, full_name, now)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute("""
                    INSERT INTO known_users (user_id, username, full_name, last_seen)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE 
                    SET username = COALESCE(excluded.username, known_users.username),
                        full_name = excluded.full_name,
                        last_seen = excluded.last_seen
                """, (user_id, u_clean, full_name, now))
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.debug(f"save_known_user xatosi: {e}")

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Username orqali foydalanuvchini topish."""
        if not username:
            return None
        u_clean = username.lower().lstrip("@")
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT user_id, username, full_name FROM known_users WHERE LOWER(username) = $1",
                        u_clean
                    )
                    if row:
                        return dict(row)
            elif self.sqlite_conn:
                async with self.sqlite_conn.execute(
                    "SELECT user_id, username, full_name FROM known_users WHERE LOWER(username) = ?",
                    (u_clean,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {"user_id": row[0], "username": row[1], "full_name": row[2]}
        except Exception as e:
            logger.debug(f"get_user_by_username xatosi: {e}")
        return None

    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """User ID orqali foydalanuvchini topish."""
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT user_id, username, full_name FROM known_users WHERE user_id = $1",
                        user_id
                    )
                    if row:
                        return dict(row)
            elif self.sqlite_conn:
                async with self.sqlite_conn.execute(
                    "SELECT user_id, username, full_name FROM known_users WHERE user_id = ?",
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {"user_id": row[0], "username": row[1], "full_name": row[2]}
        except Exception as e:
            logger.debug(f"get_user_by_id xatosi: {e}")
        return None

    # ==================== GURUH A'ZOLARINI KUZATISH VA TOZALASH ====================
    async def track_chat_member(self, chat_id: int, user_id: int):
        """Guruh a'zosini ro'yxatga kiritish yoki yangilash (Throttled)."""
        pair = (chat_id, user_id)
        if pair in self._tracked_members_cache:
            return
        self._tracked_members_cache.add(pair)

        now = datetime.now()
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO group_members (chat_id, user_id, updated_at)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (chat_id, user_id) DO UPDATE
                        SET updated_at = $3
                    """, chat_id, user_id, now)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute("""
                    INSERT INTO group_members (chat_id, user_id, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(chat_id, user_id) DO UPDATE
                    SET updated_at = excluded.updated_at
                """, (chat_id, user_id, now))
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.debug(f"track_chat_member xatosi: {e}")

    async def get_chat_member_ids(self, chat_id: int) -> List[int]:
        """Guruhda ma'lum bo'lgan barcha a'zolarning ID ro'yxatini qaytaradi."""
        ids = set()
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    rows = await conn.fetch("SELECT user_id FROM group_members WHERE chat_id = $1", chat_id)
                    for r in rows:
                        ids.add(r["user_id"])
                    n_rows = await conn.fetch("SELECT user_id FROM newcomers WHERE chat_id = $1", chat_id)
                    for r in n_rows:
                        ids.add(r["user_id"])
                    w_rows = await conn.fetch("SELECT user_id FROM warnings WHERE chat_id = $1", chat_id)
                    for r in w_rows:
                        ids.add(r["user_id"])
            elif self.sqlite_conn:
                async with self.sqlite_conn.execute("SELECT user_id FROM group_members WHERE chat_id = ?", (chat_id,)) as cur:
                    rows = await cur.fetchall()
                    for r in rows:
                        ids.add(r[0])
                async with self.sqlite_conn.execute("SELECT user_id FROM newcomers WHERE chat_id = ?", (chat_id,)) as cur:
                    rows = await cur.fetchall()
                    for r in rows:
                        ids.add(r[0])
                async with self.sqlite_conn.execute("SELECT user_id FROM warnings WHERE chat_id = ?", (chat_id,)) as cur:
                    rows = await cur.fetchall()
                    for r in rows:
                        ids.add(r[0])
        except Exception as e:
            logger.debug(f"get_chat_member_ids xatosi: {e}")
        return list(ids)

    async def remove_chat_member(self, chat_id: int, user_id: int):
        """Guruh a'zosini ro'yxatdan o'chirish."""
        self._tracked_members_cache.discard((chat_id, user_id))
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("DELETE FROM group_members WHERE chat_id = $1 AND user_id = $2", chat_id, user_id)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute("DELETE FROM group_members WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.debug(f"remove_chat_member xatosi: {e}")

    async def get_all_known_user_ids(self) -> List[int]:
        """Tizimdagi barcha ma'lum foydalanuvchilar ID larini qaytaradi."""
        ids = set()
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    rows = await conn.fetch("SELECT user_id FROM known_users")
                    for r in rows:
                        ids.add(r["user_id"])
            elif self.sqlite_conn:
                async with self.sqlite_conn.execute("SELECT user_id FROM known_users") as cur:
                    rows = await cur.fetchall()
                    for r in rows:
                        ids.add(r[0])
        except Exception as e:
            logger.debug(f"get_all_known_user_ids xatosi: {e}")
        return list(ids)

    # ==================== LOG MAVZULARI (FORUM THREADS) ====================
    async def _load_log_threads_cache(self):
        """Barcha sozlangan log threadlarini RAM keshga yuklaydi."""
        threads = {}
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    rows = await conn.fetch("SELECT category, channel_id, thread_id, thread_name FROM log_threads")
                    for r in rows:
                        threads[r["category"]] = {
                            "channel_id": r["channel_id"],
                            "thread_id": r["thread_id"],
                            "thread_name": r["thread_name"] or ""
                        }
            elif self.sqlite_conn:
                async with self.sqlite_conn.execute("SELECT category, channel_id, thread_id, thread_name FROM log_threads") as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        threads[r[0]] = {
                            "channel_id": r[1],
                            "thread_id": r[2],
                            "thread_name": r[3] or ""
                        }
        except Exception as e:
            logger.debug(f"_load_log_threads_cache xatosi: {e}")
        self._log_threads_cache = threads

    async def set_log_thread(self, category: str, channel_id: int, thread_id: int, thread_name: str = ""):
        """Kategoriya uchun log mavzusi (thread) ID sini saqlaydi va keshni yangilaydi."""
        if self._log_threads_cache is None:
            await self._load_log_threads_cache()
        self._log_threads_cache[category] = {
            "channel_id": channel_id,
            "thread_id": thread_id,
            "thread_name": thread_name
        }

        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO log_threads (category, channel_id, thread_id, thread_name, updated_at)
                        VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                        ON CONFLICT (category) DO UPDATE
                        SET channel_id = $2, thread_id = $3, thread_name = $4, updated_at = CURRENT_TIMESTAMP
                    """, category, channel_id, thread_id, thread_name)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute("""
                    INSERT INTO log_threads (category, channel_id, thread_id, thread_name, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(category) DO UPDATE
                    SET channel_id = excluded.channel_id, thread_id = excluded.thread_id,
                        thread_name = excluded.thread_name, updated_at = CURRENT_TIMESTAMP
                """, (category, channel_id, thread_id, thread_name))
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.error(f"set_log_thread xatosi: {e}")

    async def get_log_thread(self, category: str) -> Optional[Tuple[int, int]]:
        """Kategoriya uchun (channel_id, thread_id) juftligini oladi (RAM keshdan, 0ms)."""
        if self._log_threads_cache is None:
            await self._load_log_threads_cache()
        item = self._log_threads_cache.get(category)
        if item and item.get("thread_id"):
            return (item["channel_id"], item["thread_id"])
        return None

    async def get_all_log_threads(self) -> Dict[str, Dict[str, Any]]:
        """Barcha saqlangan log threadlarini oladi."""
        if self._log_threads_cache is None:
            await self._load_log_threads_cache()
        return dict(self._log_threads_cache)

    async def clear_log_threads(self):
        """Barcha log mavzularini tozalaydi."""
        self._log_threads_cache = {}
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("DELETE FROM log_threads")
            elif self.sqlite_conn:
                await self.sqlite_conn.execute("DELETE FROM log_threads")
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.error(f"clear_log_threads xatosi: {e}")

    # ==================== KUNLIK FOALLIK VA ACTIVE UNVONI ====================
    async def record_user_activity(self, chat_id: int, user_id: int, date_str: str) -> Tuple[int, bool]:
        """
        Foydalanuvchining bugungi xabarlar sonini 1 taga oshiradi (0ms RAM kesh + DB).
        Qaytadi: (message_count, is_active_granted)
        """
        cache_key = (chat_id, user_id, date_str)
        if cache_key in self._daily_activity_cache:
            count, granted = self._daily_activity_cache[cache_key]
            count += 1
            self._daily_activity_cache[cache_key] = (count, granted)
        else:
            count = 1
            granted = False
            try:
                if self.is_postgres and self.pg_pool:
                    async with self.pg_pool.acquire() as conn:
                        row = await conn.fetchrow(
                            "SELECT message_count, is_active_granted FROM user_daily_activity WHERE chat_id = $1 AND user_id = $2 AND activity_date = $3",
                            chat_id, user_id, date_str
                        )
                        if row:
                            count = row["message_count"] + 1
                            granted = bool(row["is_active_granted"])
                elif self.sqlite_conn:
                    async with self.sqlite_conn.execute(
                        "SELECT message_count, is_active_granted FROM user_daily_activity WHERE chat_id = ? AND user_id = ? AND activity_date = ?",
                        (chat_id, user_id, date_str)
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            count = row[0] + 1
                            granted = bool(row[1])
            except Exception as e:
                logger.error(f"record_user_activity select xatosi: {e}")
            self._daily_activity_cache[cache_key] = (count, granted)

        # Bazaga asinxron yangilab qo'yamiz
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO user_daily_activity (chat_id, user_id, activity_date, message_count, is_active_granted)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (chat_id, user_id, activity_date)
                        DO UPDATE SET message_count = $4;
                    """, chat_id, user_id, date_str, count, granted)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute("""
                    INSERT INTO user_daily_activity (chat_id, user_id, activity_date, message_count, is_active_granted)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(chat_id, user_id, activity_date)
                    DO UPDATE SET message_count = ?;
                """, (chat_id, user_id, date_str, count, 1 if granted else 0, count))
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.error(f"record_user_activity save xatosi: {e}")

        return count, granted

    async def mark_active_granted(self, chat_id: int, user_id: int, date_str: str):
        """Foydalanuvchiga bugun Active unvoni berilganini qayd etadi."""
        cache_key = (chat_id, user_id, date_str)
        count = 1
        if cache_key in self._daily_activity_cache:
            count = self._daily_activity_cache[cache_key][0]
        self._daily_activity_cache[cache_key] = (count, True)

        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO user_daily_activity (chat_id, user_id, activity_date, message_count, is_active_granted)
                        VALUES ($1, $2, $3, $4, TRUE)
                        ON CONFLICT (chat_id, user_id, activity_date)
                        DO UPDATE SET is_active_granted = TRUE;
                    """, chat_id, user_id, date_str, count)
            elif self.sqlite_conn:
                await self.sqlite_conn.execute("""
                    INSERT INTO user_daily_activity (chat_id, user_id, activity_date, message_count, is_active_granted)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(chat_id, user_id, activity_date)
                    DO UPDATE SET is_active_granted = 1;
                """, (chat_id, user_id, date_str, count))
                await self.sqlite_conn.commit()
        except Exception as e:
            logger.error(f"mark_active_granted xatosi: {e}")

    async def get_daily_activity_leaderboard(self, chat_id: int, date_str: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Kunlik eng faol a'zolar ro'yxatini qaytaradi."""
        results = []
        try:
            if self.is_postgres and self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    rows = await conn.fetch("""
                        SELECT a.user_id, a.message_count, a.is_active_granted, u.full_name, u.username
                        FROM user_daily_activity a
                        LEFT JOIN known_users u ON a.user_id = u.user_id
                        WHERE a.chat_id = $1 AND a.activity_date = $2
                        ORDER BY a.message_count DESC
                        LIMIT $3;
                    """, chat_id, date_str, limit)
                    for r in rows:
                        results.append({
                            "user_id": r["user_id"],
                            "message_count": r["message_count"],
                            "is_active_granted": r["is_active_granted"],
                            "full_name": r["full_name"] or "Foydalanuvchi",
                            "username": r["username"]
                        })
            elif self.sqlite_conn:
                async with self.sqlite_conn.execute("""
                    SELECT a.user_id, a.message_count, a.is_active_granted, u.full_name, u.username
                    FROM user_daily_activity a
                    LEFT JOIN known_users u ON a.user_id = u.user_id
                    WHERE a.chat_id = ? AND a.activity_date = ?
                    ORDER BY a.message_count DESC
                    LIMIT ?;
                """, (chat_id, date_str, limit)) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        results.append({
                            "user_id": r[0],
                            "message_count": r[1],
                            "is_active_granted": bool(r[2]),
                            "full_name": r[3] or "Foydalanuvchi",
                            "username": r[4]
                        })
        except Exception as e:
            logger.error(f"get_daily_activity_leaderboard xatosi: {e}")
        return results

    async def close(self):
        """Baza ulanishini xavfsiz yopish."""
        if self.pg_pool:
            await self.pg_pool.close()
        if self.sqlite_conn:
            await self.sqlite_conn.close()

db = Database()
