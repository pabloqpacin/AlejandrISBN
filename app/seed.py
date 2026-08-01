import hashlib
import json
import logging
import os
from csv import DictReader
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Optional

import asyncpg

logger = logging.getLogger("alejandrisbn.seed")

SEED_DIR = Path(os.getenv("SEED_DIR", Path(__file__).resolve().parent.parent / "seed"))

SEED_SUFFIXES = {".json", ".sql", ".csv"}


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


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "t", "yes", "y", "si", "sí"}


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _split_sql(script: str) -> list[str]:
    """Split a SQL file into statements (no dollar-quoting support; keep seeds simple)."""
    statements: list[str] = []
    for chunk in script.split(";"):
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
                "favourite": bool(row.get("favourite", False)),
                "source": (row.get("source") or "seed").strip() or "seed",
                "created_at": _parse_ts(row.get("created_at")),
                "updated_at": _parse_ts(row.get("updated_at")),
            }
        )
    return cleaned


def _csv_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    reader = DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ValueError(f"CSV seed {path.name} has no header row")
    fields = {name.strip().lower(): name for name in reader.fieldnames if name}
    if "isbn" not in fields:
        raise ValueError(f"CSV seed {path.name} must include an 'isbn' column")

    rows: list[dict[str, str]] = []
    for raw in reader:
        normalized = {
            key.strip().lower(): (raw.get(original) or "").strip()
            for key, original in fields.items()
        }
        if not any(normalized.values()):
            continue
        rows.append(normalized)
    return rows


def _override_from_csv(meta: dict[str, Any], row: dict[str, str]) -> dict[str, Any]:
    """Build a book row from online lookup metadata + optional CSV overrides.

    Lookup always wins for bibliographic fields (title, authors, year, publisher,
    cover, description, source). CSV may still set library fields: location, notes,
    genre, favourite.
    """
    book = {
        "isbn": _normalize_isbn(row.get("isbn") or meta.get("isbn") or ""),
        "title": meta.get("title") or "",
        "authors": meta.get("authors") or "",
        "publication_year": meta.get("publication_year"),
        "genre": meta.get("genre") or "",
        "publisher": meta.get("publisher") or "",
        "cover_url": meta.get("cover_url") or "",
        "description": meta.get("description") or "",
        "location": "",
        "notes": "",
        "favourite": False,
        "source": f"seed-csv:{meta.get('source') or 'lookup'}",
        "created_at": None,
        "updated_at": None,
    }

    # Library / personal fields — CSV overrides are intentional.
    for key in ("location", "notes", "genre"):
        if row.get(key):
            book[key] = row[key]

    if "favourite" in row and row["favourite"] != "":
        book["favourite"] = _parse_bool(row["favourite"])

    if row.get("source"):
        book["source"] = row["source"]

    # Title (and other bib fields) stay from lookup. CSV title is ignored on purpose
    # so a provisional label in the sheet gets rewritten by the catalog match.
    if not book["title"] and row.get("title"):
        book["title"] = row["title"]

    return book


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
                cover_url, description, location, notes, favourite, source, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10, $11, $12,
                COALESCE($13, NOW()),
                COALESCE($14, NOW())
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
            book["favourite"],
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


async def _apply_csv(conn: asyncpg.Connection, path: Path) -> None:
    """Lookup each ISBN online, then insert. CSV may override location/notes/etc."""
    from app.services.isbn_lookup import lookup_isbn

    rows = _csv_rows(path)
    inserted = 0
    skipped = 0
    failed = 0

    for row in rows:
        isbn = _normalize_isbn(row.get("isbn") or "")
        if not isbn or len(isbn) not in (10, 13):
            logger.warning("Seed CSV %s: skipping invalid ISBN %r", path.name, row.get("isbn"))
            failed += 1
            continue

        existing = await conn.fetchval("SELECT isbn FROM books WHERE isbn = $1", isbn)
        if existing:
            skipped += 1
            continue

        try:
            meta = await lookup_isbn(isbn)
        except ValueError as exc:
            logger.warning("Seed CSV %s: lookup failed for %s (%s)", path.name, isbn, exc)
            failed += 1
            continue
        except Exception:
            logger.exception("Seed CSV %s: unexpected lookup error for %s", path.name, isbn)
            failed += 1
            continue

        book = _override_from_csv(meta, {**row, "isbn": isbn})
        if not book["title"]:
            logger.warning("Seed CSV %s: no title after lookup for %s", path.name, isbn)
            failed += 1
            continue

        count = await _insert_books(conn, [book])
        inserted += count

    logger.info(
        "Seed CSV %s: %s row(s), %s inserted, %s already present, %s failed",
        path.name,
        len(rows),
        inserted,
        skipped,
        failed,
    )


def _seed_files() -> list[Path]:
    if not SEED_DIR.exists():
        return []
    return [
        path
        for path in sorted(SEED_DIR.iterdir())
        if path.is_file()
        and path.suffix.lower() in SEED_SUFFIXES
        and ".example." not in path.name
        and not path.name.endswith(".example.json")
        and not path.name.endswith(".example.sql")
        and not path.name.endswith(".example.csv")
    ]


async def apply_seeds(pool: asyncpg.Pool) -> None:
    """
    Apply new/changed files from SEED_DIR.

    - *.json  → write book rows directly (ON CONFLICT DO NOTHING)
    - *.csv   → online ISBN lookup per row, then insert (optional field overrides)
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
                suffix = path.suffix.lower()
                if suffix == ".csv":
                    # Lookups are slow; do not wrap the whole file in one DB transaction.
                    await _apply_csv(conn, path)
                    await _mark_applied(conn, path.name, checksum)
                else:
                    async with conn.transaction():
                        if suffix == ".json":
                            await _apply_json(conn, path)
                        else:
                            await _apply_sql(conn, path)
                        await _mark_applied(conn, path.name, checksum)
                logger.info("Applied seed %s", path.name)
            except Exception:
                logger.exception("Failed to apply seed %s", path.name)
                raise
