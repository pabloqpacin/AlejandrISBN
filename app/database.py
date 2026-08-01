import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import asyncpg


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://alejandrisbn:alejandrisbn@localhost:5432/alejandrisbn",
)

SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "alejandrisbn.db"
SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "books_seed.json"

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
            # Existing deployments created before `location`
            await conn.execute(
                """
                ALTER TABLE books
                ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT ''
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

    await migrate_legacy_data()


def _load_legacy_rows() -> list[dict[str, Any]]:
    if SEED_PATH.exists():
        return json.loads(SEED_PATH.read_text(encoding="utf-8"))

    if not SQLITE_PATH.exists():
        return []

    import sqlite3

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute("SELECT * FROM books")]
    finally:
        conn.close()

    SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEED_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return rows


async def migrate_legacy_data() -> None:
    """Import SQLite/seed books once if Postgres inventory is empty."""
    if pool is None:
        return

    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM books")
        if count and count > 0:
            return

        rows = _load_legacy_rows()
        if not rows:
            return

        async with conn.transaction():
            for row in rows:
                created_at = _parse_ts(row.get("created_at"))
                updated_at = _parse_ts(row.get("updated_at"))
                await conn.execute(
                    """
                    INSERT INTO books (
                        isbn, title, authors, publication_year, genre, publisher,
                        cover_url, description, location, notes, source, created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6,
                        $7, $8, $9, $10, $11,
                        COALESCE($12, NOW()),
                        COALESCE($13, NOW())
                    )
                    ON CONFLICT (isbn) DO NOTHING
                    """,
                    row.get("isbn"),
                    row.get("title") or "Untitled",
                    row.get("authors") or "",
                    row.get("publication_year"),
                    row.get("genre") or "",
                    row.get("publisher") or "",
                    row.get("cover_url") or "",
                    row.get("description") or "",
                    row.get("location") or "",
                    row.get("notes") or "",
                    row.get("source") or "",
                    created_at,
                    updated_at,
                )
