import logging
from datetime import datetime
from typing import Optional
import aiosqlite
import asyncpg
from bot.config import config

logger = logging.getLogger(__name__)

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
                    CREATE TABLE IF NOT EXISTS chat_settings (
                        chat_id BIGINT PRIMARY KEY,
                        night_mode BOOLEAN DEFAULT FALSE,
                        anti_link BOOLEAN DEFAULT TRUE,
                        anti_forward BOOLEAN DEFAULT TRUE,
                        captcha_enabled BOOLEAN DEFAULT TRUE
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
                CREATE TABLE IF NOT EXISTS chat_settings (
                    chat_id INTEGER PRIMARY KEY,
                    night_mode BOOLEAN DEFAULT 0,
                    anti_link BOOLEAN DEFAULT 1,
                    anti_forward BOOLEAN DEFAULT 1,
                    captcha_enabled BOOLEAN DEFAULT 1
                );
            """)
            await self.sqlite_conn.commit()

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

    async def get_night_mode(self, chat_id: int) -> bool:
        """Tungi rejim holatini qaytaradi."""
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                val = await conn.fetchval(
                    "SELECT night_mode FROM chat_settings WHERE chat_id = $1",
                    chat_id
                )
                return bool(val) if val is not None else False
        else:
            async with self.sqlite_conn.execute(
                "SELECT night_mode FROM chat_settings WHERE chat_id = ?",
                (chat_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return bool(row[0]) if row else False

    async def set_night_mode(self, chat_id: int, enabled: bool):
        """Tungi rejim holatini saqlaydi."""
        val = 1 if enabled else 0
        if self.is_postgres and self.pg_pool:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO chat_settings (chat_id, night_mode)
                    VALUES ($1, $2)
                    ON CONFLICT (chat_id)
                    DO UPDATE SET night_mode = $2
                """, chat_id, enabled)
        else:
            await self.sqlite_conn.execute("""
                INSERT INTO chat_settings (chat_id, night_mode)
                VALUES (?, ?)
                ON CONFLICT(chat_id)
                DO UPDATE SET night_mode = excluded.night_mode
            """, (chat_id, val))
            await self.sqlite_conn.commit()

    async def close(self):
        """Baza ulanishini xavfsiz yopish."""
        if self.pg_pool:
            await self.pg_pool.close()
        if self.sqlite_conn:
            await self.sqlite_conn.close()

db = Database()
