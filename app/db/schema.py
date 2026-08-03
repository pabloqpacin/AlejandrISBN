"""Shared books schema (DDL). Dialect-specific bits live in each backend module."""

from __future__ import annotations

from typing import Any


async def ensure_books_schema(conn: Any, *, is_sqlite: bool) -> None:
    from app.db import postgres as pg
    from app.db import sqlite as sq

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

    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_books_title ON books (lower(title))",
        "CREATE INDEX IF NOT EXISTS idx_books_authors ON books (lower(authors))",
        "CREATE INDEX IF NOT EXISTS idx_books_isbn ON books (isbn)",
        "CREATE INDEX IF NOT EXISTS idx_books_location ON books (lower(location))",
        "CREATE INDEX IF NOT EXISTS idx_books_favourite ON books (favourite)",
        "CREATE INDEX IF NOT EXISTS idx_books_legal_deposit ON books (lower(legal_deposit))",
        "CREATE INDEX IF NOT EXISTS idx_books_collection ON books (lower(collection))",
        "CREATE INDEX IF NOT EXISTS idx_books_volume ON books (lower(volume))",
    ):
        await conn.execute(stmt)
