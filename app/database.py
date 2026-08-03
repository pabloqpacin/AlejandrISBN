import os
from typing import Any, AsyncIterator, Optional

import asyncpg

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://alejandrisbn:alejandrisbn@localhost:5432/alejandrisbn",
)

pool: Optional[asyncpg.Pool] = None


async def init_pool() -> None:
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )


async def close_pool() -> None:
    global pool
    if pool is not None:
        await pool.close()
        pool = None


async def get_db() -> AsyncIterator[asyncpg.Connection]:
    if pool is None:
        raise RuntimeError("Database pool is not initialized")
    async with pool.acquire() as conn:
        yield conn


def record_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    data = dict(row)
    for key in ("created_at", "updated_at"):
        value = data.get(key)
        if hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    return data


async def init_db() -> None:
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS books (
                    isbn             TEXT PRIMARY KEY,
                    title            TEXT NOT NULL,
                    authors          TEXT NOT NULL DEFAULT '',
                    publication_year INTEGER,
                    genre            TEXT NOT NULL DEFAULT '',
                    publisher        TEXT NOT NULL DEFAULT '',
                    cover_url        TEXT NOT NULL DEFAULT '',
                    description      TEXT NOT NULL DEFAULT '',
                    location         TEXT NOT NULL DEFAULT '',
                    notes            TEXT NOT NULL DEFAULT '',
                    source           TEXT NOT NULL DEFAULT '',
                    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute(
                """
                ALTER TABLE books
                ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT ''
                """
            )
            await conn.execute(
                """
                ALTER TABLE books
                ADD COLUMN IF NOT EXISTS favourite BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
            await conn.execute(
                """
                ALTER TABLE books
                ADD COLUMN IF NOT EXISTS legal_deposit TEXT NOT NULL DEFAULT ''
                """
            )
            await conn.execute(
                """
                ALTER TABLE books
                ADD COLUMN IF NOT EXISTS collection TEXT NOT NULL DEFAULT ''
                """
            )
            await conn.execute(
                """
                ALTER TABLE books
                ADD COLUMN IF NOT EXISTS volume TEXT NOT NULL DEFAULT ''
                """
            )
            await conn.execute(
                """
                ALTER TABLE books
                ADD COLUMN IF NOT EXISTS original_year INTEGER
                """
            )
            await conn.execute(
                """
                ALTER TABLE books
                ADD COLUMN IF NOT EXISTS translators TEXT NOT NULL DEFAULT ''
                """
            )
            await conn.execute(
                """
                ALTER TABLE books
                ADD COLUMN IF NOT EXISTS original_title TEXT NOT NULL DEFAULT ''
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_title
                ON books (lower(title))
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_authors
                ON books (lower(authors))
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_isbn
                ON books (isbn)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_location
                ON books (lower(location))
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_favourite
                ON books (favourite)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_legal_deposit
                ON books (lower(legal_deposit))
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_collection
                ON books (lower(collection))
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_volume
                ON books (lower(volume))
                """
            )

    from app.seed import apply_seeds

    await apply_seeds(pool)
