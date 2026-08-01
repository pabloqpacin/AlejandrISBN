import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import asyncpg

logger = logging.getLogger("alejandrisbn.seed")

SEED_DIR = Path(os.getenv("SEED_DIR", Path(__file__).resolve().parent.parent / "seed"))



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


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _split_sql(script: str) -> list[str]:
    """Split a SQL file into statements (no dollar-quoting support; keep seeds simple)."""
    statements: list[str] = []
    for chunk in script.split(";"):
        # drop full-line comments
        lines = []
        for line in chunk.splitlines():
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            lines.append(line)
        statement = "\n".join(lines).strip()
        if statement:
            statements.append(statement)
    return statements


def _normalize_isbn(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isalnum()).upper()


def _books_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("books"), list):
            rows = payload["books"]
        else:
            rows = [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("JSON seed must be a list of books or an object with a 'books' array")

    cleaned: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        isbn = _normalize_isbn(row.get("isbn") or "")
        title = (row.get("title") or "").strip()
        if not isbn or not title:
            continue
        cleaned.append(
            {
                "isbn": isbn,
                "title": title,
                "authors": (row.get("authors") or "").strip(),
                "publication_year": row.get("publication_year"),
                "genre": (row.get("genre") or "").strip(),
                "publisher": (row.get("publisher") or "").strip(),
                "cover_url": (row.get("cover_url") or "").strip(),
                "description": (row.get("description") or "").strip(),
                "location": (row.get("location") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
                "source": (row.get("source") or "seed").strip() or "seed",
                "created_at": _parse_ts(row.get("created_at")),
                "updated_at": _parse_ts(row.get("updated_at")),
            }
        )
    return cleaned


async def _ensure_seed_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_seeds (
            filename   TEXT PRIMARY KEY,
            checksum   TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


async def _already_applied(conn: asyncpg.Connection, filename: str, checksum: str) -> bool:
    row = await conn.fetchrow(
        "SELECT checksum FROM schema_seeds WHERE filename = $1",
        filename,
    )
    return bool(row and row["checksum"] == checksum)


async def _mark_applied(conn: asyncpg.Connection, filename: str, checksum: str) -> None:
    await conn.execute(
        """
        INSERT INTO schema_seeds (filename, checksum, applied_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (filename) DO UPDATE
        SET checksum = EXCLUDED.checksum,
            applied_at = NOW()
        """,
        filename,
        checksum,
    )


async def _insert_books(conn: asyncpg.Connection, books: list[dict[str, Any]]) -> int:
    inserted = 0
    for book in books:
        result = await conn.execute(
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
            book["isbn"],
            book["title"],
            book["authors"],
            book["publication_year"],
            book["genre"],
            book["publisher"],
            book["cover_url"],
            book["description"],
            book["location"],
            book["notes"],
            book["source"],
            book["created_at"],
            book["updated_at"],
        )
        if result == "INSERT 0 1":
            inserted += 1
    return inserted


async def _apply_json(conn: asyncpg.Connection, path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    books = _books_from_json(payload)
    count = await _insert_books(conn, books)
    logger.info("Seed JSON %s: %s book(s) in file, %s inserted", path.name, len(books), count)


async def _apply_sql(conn: asyncpg.Connection, path: Path) -> None:
    script = path.read_text(encoding="utf-8")
    statements = _split_sql(script)
    for statement in statements:
        await conn.execute(statement)
    logger.info("Seed SQL %s: executed %s statement(s)", path.name, len(statements))


def _seed_files() -> list[Path]:
    if not SEED_DIR.exists():
        return []
    files = [
        path
        for path in sorted(SEED_DIR.iterdir())
        if path.is_file()
        and path.suffix.lower() in {".json", ".sql"}
        and not path.name.endswith(".example.json")
        and not path.name.endswith(".example.sql")
        and ".example." not in path.name
    ]
    return files


async def apply_seeds(pool: asyncpg.Pool) -> None:
    """
    Apply new/changed files from SEED_DIR.

    - *.json  → upsert book rows (ON CONFLICT DO NOTHING)
    - *.sql   → run SQL statements
    Tracked in schema_seeds by filename + checksum (re-apply if file changes).
    """
    files = _seed_files()
    if not files:
        logger.info("No seed files found in %s", SEED_DIR)
        return

    async with pool.acquire() as conn:
        await _ensure_seed_table(conn)
        for path in files:
            checksum = _checksum(path)
            if await _already_applied(conn, path.name, checksum):
                logger.info("Seed %s already applied (unchanged)", path.name)
                continue
            try:
                async with conn.transaction():
                    if path.suffix.lower() == ".json":
                        await _apply_json(conn, path)
                    else:
                        await _apply_sql(conn, path)
                    await _mark_applied(conn, path.name, checksum)
                logger.info("Applied seed %s", path.name)
            except Exception:
                logger.exception("Failed to apply seed %s", path.name)
                raise
