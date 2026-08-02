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


_NA_VALUES = {"", "n/a", "na", "n.a.", "n.a", "none", "null", "-", "—", "–"}


def _optional_text(value: Any) -> str:
    """Treat blank / n/a placeholders as empty string."""
    text = str(value or "").strip()
    if text.lower() in _NA_VALUES:
        return ""
    return text


def _legal_deposit_from_row(row: dict[str, Any]) -> str:
    return _optional_text(row.get("legal_deposit") or row.get("deposito_legal") or "")


def _books_from_json(payload: Any) -> list[dict[str, Any]]:
    from app.schemas import generate_local_id, is_local_id, normalize_labels

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
        title = _optional_text(row.get("title"))
        if not title:
            continue

        raw_isbn = _optional_text(row.get("isbn"))
        if not raw_isbn:
            isbn = generate_local_id()
        elif is_local_id(raw_isbn):
            isbn = raw_isbn.upper()
        else:
            isbn = _normalize_isbn(raw_isbn)
            if len(isbn) not in (10, 13):
                logger.warning("JSON seed: skipping invalid ISBN %r for %r", row.get("isbn"), title)
                continue

        cleaned.append(
            {
                "isbn": isbn,
                "title": title,
                "authors": normalize_labels(row.get("authors")),
                "publication_year": row.get("publication_year"),
                "genre": normalize_labels(row.get("genre")),
                "publisher": _optional_text(row.get("publisher")),
                "cover_url": _optional_text(row.get("cover_url")),
                "description": _optional_text(row.get("description")),
                "location": _optional_text(row.get("location")),
                "notes": _optional_text(row.get("notes")),
                "legal_deposit": _legal_deposit_from_row(row),
                "collection": _optional_text(row.get("collection") or row.get("coleccion")),
                "volume": _optional_text(row.get("volume") or row.get("volumen") or row.get("tomo")),
                "original_year": row.get("original_year"),
                "translators": normalize_labels(row.get("translators") or row.get("traductores")),
                "original_title": _optional_text(
                    row.get("original_title") or row.get("titulo_original")
                ),
                "favourite": bool(row.get("favourite", False)),
                "source": _optional_text(row.get("source")) or "seed",
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
    if "isbn" not in fields and "title" not in fields:
        raise ValueError(f"CSV seed {path.name} must include an 'isbn' and/or 'title' column")

    rows: list[dict[str, str]] = []
    for raw in reader:
        normalized = {
            key.strip().lower(): (raw.get(original) or "").strip()
            for key, original in fields.items()
        }
        if not any(_optional_text(v) for v in normalized.values()):
            continue
        rows.append(normalized)
    return rows


def _override_from_csv(meta: dict[str, Any], row: dict[str, str]) -> dict[str, Any]:
    """Build a book row from online lookup metadata + optional CSV overrides.

    Lookup always wins for bibliographic fields (title, authors, year, publisher,
    cover, description, source). CSV may still set library fields: location, notes,
    genre, favourite, legal_deposit. Authors/genre are stored as ``;``-separated labels.
    """
    from app.schemas import normalize_labels

    book = {
        "isbn": _normalize_isbn(row.get("isbn") or meta.get("isbn") or ""),
        "title": meta.get("title") or "",
        "authors": normalize_labels(meta.get("authors") or ""),
        "publication_year": meta.get("publication_year"),
        "genre": normalize_labels(meta.get("genre") or ""),
        "publisher": meta.get("publisher") or "",
        "cover_url": meta.get("cover_url") or "",
        "description": meta.get("description") or "",
        "location": "",
        "notes": "",
        "legal_deposit": "",
        "collection": "",
        "volume": "",
        "original_year": None,
        "translators": "",
        "original_title": "",
        "favourite": False,
        "source": f"seed-csv:{meta.get('source') or 'lookup'}",
        "created_at": None,
        "updated_at": None,
    }

    for key in ("location", "notes"):
        value = _optional_text(row.get(key))
        if value:
            book[key] = value

    collection = _optional_text(row.get("collection") or row.get("coleccion"))
    if collection:
        book["collection"] = collection

    volume = _optional_text(row.get("volume") or row.get("volumen") or row.get("tomo"))
    if volume:
        book["volume"] = volume

    translators = normalize_labels(row.get("translators") or row.get("traductores"))
    if translators:
        book["translators"] = translators

    original_title = _optional_text(row.get("original_title") or row.get("titulo_original"))
    if original_title:
        book["original_title"] = original_title

    year_orig = _optional_text(row.get("original_year") or row.get("año_original") or "")
    if year_orig:
        try:
            book["original_year"] = int(year_orig)
        except ValueError:
            pass

    genre_override = normalize_labels(row.get("genre"))
    if genre_override:
        book["genre"] = genre_override

    book["legal_deposit"] = _legal_deposit_from_row(row)

    if "favourite" in row and _optional_text(row.get("favourite")) != "":
        book["favourite"] = _parse_bool(row["favourite"])

    if _optional_text(row.get("source")):
        book["source"] = _optional_text(row["source"])

    if not book["title"] and _optional_text(row.get("title")):
        book["title"] = _optional_text(row["title"])

    return book


def _manual_book_from_csv(row: dict[str, str]) -> Optional[dict[str, Any]]:
    """Row without usable ISBN: insert as LOCAL item (title required)."""
    from app.schemas import generate_local_id, normalize_labels

    title = _optional_text(row.get("title"))
    if not title:
        return None

    authors = normalize_labels(row.get("authors") or row.get("autor") or "")
    year_raw = _optional_text(row.get("publication_year") or row.get("year") or "")
    year = None
    if year_raw:
        try:
            year = int(year_raw)
        except ValueError:
            year = None

    book = {
        "isbn": generate_local_id(),
        "title": title,
        "authors": authors,
        "publication_year": year,
        "genre": normalize_labels(row.get("genre")),
        "publisher": _optional_text(row.get("publisher")),
        "cover_url": "",
        "description": _optional_text(row.get("description")),
        "location": _optional_text(row.get("location")),
        "notes": _optional_text(row.get("notes")),
        "legal_deposit": _legal_deposit_from_row(row),
        "collection": _optional_text(row.get("collection") or row.get("coleccion")),
        "volume": _optional_text(row.get("volume") or row.get("volumen") or row.get("tomo")),
        "original_year": None,
        "translators": normalize_labels(row.get("translators") or row.get("traductores")),
        "original_title": _optional_text(row.get("original_title") or row.get("titulo_original")),
        "favourite": _parse_bool(row["favourite"])
        if "favourite" in row and _optional_text(row.get("favourite")) != ""
        else False,
        "source": _optional_text(row.get("source")) or "seed-csv:manual",
        "created_at": None,
        "updated_at": None,
    }
    year_orig = _optional_text(row.get("original_year") or row.get("año_original") or "")
    if year_orig:
        try:
            book["original_year"] = int(year_orig)
        except ValueError:
            pass
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
                cover_url, description, location, notes, legal_deposit, collection, volume,
                original_year, translators, original_title,
                favourite, source, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10, $11, $12, $13,
                $14, $15, $16,
                $17, $18,
                COALESCE($19, NOW()),
                COALESCE($20, NOW())
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
            book.get("legal_deposit") or "",
            book.get("collection") or "",
            book.get("volume") or "",
            book.get("original_year"),
            book.get("translators") or "",
            book.get("original_title") or "",
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
    """ISBN rows → online lookup; rows without ISBN → manual insert (title + optional DL)."""
    from app.services.isbn_lookup import lookup_isbn

    rows = _csv_rows(path)
    inserted = 0
    skipped = 0
    failed = 0

    for row in rows:
        raw_isbn = _optional_text(row.get("isbn"))
        isbn = _normalize_isbn(raw_isbn) if raw_isbn else ""
        has_isbn = bool(isbn) and len(isbn) in (10, 13)

        if raw_isbn and not has_isbn:
            logger.warning("Seed CSV %s: skipping invalid ISBN %r", path.name, row.get("isbn"))
            failed += 1
            continue

        if not has_isbn:
            book = _manual_book_from_csv(row)
            if not book:
                logger.warning(
                    "Seed CSV %s: row without ISBN needs a title (got legal_deposit=%r)",
                    path.name,
                    row.get("legal_deposit") or row.get("deposito_legal"),
                )
                failed += 1
                continue
            count = await _insert_books(conn, [book])
            inserted += count
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
