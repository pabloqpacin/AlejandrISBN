import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "alejandrisbn.db"


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                isbn            TEXT PRIMARY KEY,
                title           TEXT NOT NULL,
                authors         TEXT NOT NULL DEFAULT '',
                publication_year INTEGER,
                genre           TEXT NOT NULL DEFAULT '',
                publisher       TEXT NOT NULL DEFAULT '',
                cover_url       TEXT NOT NULL DEFAULT '',
                description     TEXT NOT NULL DEFAULT '',
                notes           TEXT NOT NULL DEFAULT '',
                source          TEXT NOT NULL DEFAULT '',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_books_title
            ON books(title COLLATE NOCASE)
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_books_authors
            ON books(authors COLLATE NOCASE)
            """
        )
        await db.commit()
