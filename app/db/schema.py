"""Shared inventory schema (DDL) and one-shot books → items migration."""

from __future__ import annotations

import uuid
from typing import Any

from app.schemas import is_local_id


async def _table_exists(conn: Any, table: str, *, is_sqlite: bool) -> bool:
    if is_sqlite:
        row = await conn.fetchrow(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = $1",
            table,
        )
        return row is not None
    row = await conn.fetchrow(
        """
        SELECT 1 AS ok
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    return row is not None


async def _migrate_books_to_items(conn: Any, *, is_sqlite: bool) -> None:
    """Copy legacy ``books`` rows into ``items`` once, then archive ``books``."""
    if not await _table_exists(conn, "books", is_sqlite=is_sqlite):
        return
    if await _table_exists(conn, "books_migrated_legacy", is_sqlite=is_sqlite):
        return

    items_count = await conn.fetchval("SELECT COUNT(*) FROM items")
    books_count = await conn.fetchval("SELECT COUNT(*) FROM books")
    if int(items_count or 0) > 0:
        # Items already populated (fresh or prior partial run) — just archive books if empty of need.
        if int(books_count or 0) == 0:
            await conn.execute("ALTER TABLE books RENAME TO books_migrated_legacy")
        return
    if int(books_count or 0) == 0:
        await conn.execute("ALTER TABLE books RENAME TO books_migrated_legacy")
        return

    rows = await conn.fetch("SELECT * FROM books")
    for row in rows:
        data = dict(row) if not hasattr(row, "keys") else {k: row[k] for k in row.keys()}
        raw_isbn = str(data.get("isbn") or "").strip()
        isbn_value = None
        if raw_isbn and not is_local_id(raw_isbn):
            isbn_value = raw_isbn.upper()

        item_id = str(uuid.uuid4())
        await conn.execute(
            """
            INSERT INTO items (
                id, media_type, isbn, title, authors, publication_year, genre, publisher,
                cover_url, description, location, notes, legal_deposit, collection, volume,
                original_year, translators, original_title, favourite, source,
                created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9, $10, $11, $12, $13, $14, $15,
                $16, $17, $18, $19, $20,
                COALESCE($21, NOW()), COALESCE($22, NOW())
            )
            """,
            item_id,
            "book",
            isbn_value,
            data.get("title") or "",
            data.get("authors") or "",
            data.get("publication_year"),
            data.get("genre") or "",
            data.get("publisher") or "",
            data.get("cover_url") or "",
            data.get("description") or "",
            data.get("location") or "",
            data.get("notes") or "",
            data.get("legal_deposit") or "",
            data.get("collection") or "",
            data.get("volume") or "",
            data.get("original_year"),
            data.get("translators") or "",
            data.get("original_title") or "",
            bool(data.get("favourite")),
            data.get("source") or "",
            data.get("created_at"),
            data.get("updated_at"),
        )

    await conn.execute("ALTER TABLE books RENAME TO books_migrated_legacy")


async def ensure_items_schema(conn: Any, *, is_sqlite: bool) -> None:
    from app.db import postgres as pg
    from app.db import sqlite as sq

    # Keep ensuring legacy books columns exist so migration can read a complete row.
    if await _table_exists(conn, "books", is_sqlite=is_sqlite):
        await _ensure_legacy_books_columns(conn, is_sqlite=is_sqlite)

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id               TEXT PRIMARY KEY,
            media_type       TEXT NOT NULL DEFAULT 'book',
            isbn             TEXT UNIQUE,
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
            favourite        BOOLEAN NOT NULL DEFAULT FALSE,
            legal_deposit    TEXT NOT NULL DEFAULT '',
            collection       TEXT NOT NULL DEFAULT '',
            volume           TEXT NOT NULL DEFAULT '',
            original_year    INTEGER,
            translators      TEXT NOT NULL DEFAULT '',
            original_title   TEXT NOT NULL DEFAULT '',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    alter_columns = (
        ("media_type", "TEXT NOT NULL DEFAULT 'book'"),
        ("isbn", "TEXT"),
        ("location", "TEXT NOT NULL DEFAULT ''"),
        ("favourite", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("legal_deposit", "TEXT NOT NULL DEFAULT ''"),
        ("collection", "TEXT NOT NULL DEFAULT ''"),
        ("volume", "TEXT NOT NULL DEFAULT ''"),
        ("original_year", "INTEGER"),
        ("translators", "TEXT NOT NULL DEFAULT ''"),
        ("original_title", "TEXT NOT NULL DEFAULT ''"),
    )
    for name, typedef in alter_columns:
        if is_sqlite:
            await sq.add_column_if_missing(conn, "items", name, typedef)
        else:
            await pg.add_column_if_missing(conn, "items", name, typedef)

    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_items_title ON items (lower(title))",
        "CREATE INDEX IF NOT EXISTS idx_items_authors ON items (lower(authors))",
        "CREATE INDEX IF NOT EXISTS idx_items_media_type ON items (media_type)",
        "CREATE INDEX IF NOT EXISTS idx_items_location ON items (lower(location))",
        "CREATE INDEX IF NOT EXISTS idx_items_favourite ON items (favourite)",
        "CREATE INDEX IF NOT EXISTS idx_items_legal_deposit ON items (lower(legal_deposit))",
        "CREATE INDEX IF NOT EXISTS idx_items_collection ON items (lower(collection))",
        "CREATE INDEX IF NOT EXISTS idx_items_volume ON items (lower(volume))",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_isbn_unique ON items (isbn)",
    ):
        await conn.execute(stmt)

    await _migrate_books_to_items(conn, is_sqlite=is_sqlite)


async def _ensure_legacy_books_columns(conn: Any, *, is_sqlite: bool) -> None:
    from app.db import postgres as pg
    from app.db import sqlite as sq

    alter_columns = (
        ("location", "TEXT NOT NULL DEFAULT ''"),
        ("favourite", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("legal_deposit", "TEXT NOT NULL DEFAULT ''"),
        ("collection", "TEXT NOT NULL DEFAULT ''"),
        ("volume", "TEXT NOT NULL DEFAULT ''"),
        ("original_year", "INTEGER"),
        ("translators", "TEXT NOT NULL DEFAULT ''"),
        ("original_title", "TEXT NOT NULL DEFAULT ''"),
    )
    for name, typedef in alter_columns:
        if is_sqlite:
            await sq.add_column_if_missing(conn, "books", name, typedef)
        else:
            await pg.add_column_if_missing(conn, "books", name, typedef)


# Back-compat alias used by older call sites during transition.
async def ensure_books_schema(conn: Any, *, is_sqlite: bool) -> None:
    await ensure_items_schema(conn, is_sqlite=is_sqlite)
