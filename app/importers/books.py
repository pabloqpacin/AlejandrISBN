"""Offline inventory import helpers (JSON / CSV → book rows → DB insert)."""

from __future__ import annotations

import logging
from csv import DictReader
from datetime import datetime
from io import StringIO
from typing import Any, Optional

from app.db import DbConnection

logger = logging.getLogger("alejandrisbn.importers")

_NA_VALUES = {"", "n/a", "na", "n.a.", "n.a", "none", "null", "-", "—", "–"}


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


def _normalize_isbn(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isalnum()).upper()


def _optional_text(value: Any) -> str:
    """Treat blank / n/a placeholders as empty string."""
    text = str(value or "").strip()
    if text.lower() in _NA_VALUES:
        return ""
    return text


def _legal_deposit_from_row(row: dict[str, Any]) -> str:
    return _optional_text(row.get("legal_deposit") or row.get("deposito_legal") or "")


def books_from_json(payload: Any) -> list[dict[str, Any]]:
    from app.schemas import generate_local_id, is_local_id, normalize_authors, normalize_labels

    if isinstance(payload, dict):
        if isinstance(payload.get("books"), list):
            rows = payload["books"]
        else:
            rows = [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("JSON must be a list of books or an object with a 'books' array")

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
                logger.warning("JSON import: skipping invalid ISBN %r for %r", row.get("isbn"), title)
                continue

        cleaned.append(
            {
                "isbn": isbn,
                "title": title,
                "authors": normalize_authors(row.get("authors")),
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
                "source": _optional_text(row.get("source")) or "import",
                "created_at": _parse_ts(row.get("created_at")),
                "updated_at": _parse_ts(row.get("updated_at")),
            }
        )
    return cleaned


def books_from_csv(text: str) -> list[dict[str, Any]]:
    """Parse an export-style CSV (full inventory columns) into book rows for insert."""
    from app.schemas import generate_local_id, is_local_id, normalize_authors, normalize_labels

    reader = DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV sin cabecera")

    fields = {name.strip().lower(): name for name in reader.fieldnames if name}
    if "title" not in fields and "isbn" not in fields:
        raise ValueError("CSV debe incluir columna 'title' y/o 'isbn'")

    cleaned: list[dict[str, Any]] = []
    for raw in reader:
        row = {
            key: (raw.get(original) or "").strip()
            for key, original in fields.items()
        }
        if not any(_optional_text(v) for v in row.values()):
            continue

        title = _optional_text(row.get("title"))
        raw_isbn = _optional_text(row.get("isbn"))

        if not title and not raw_isbn:
            continue

        if not raw_isbn:
            isbn = generate_local_id()
        elif is_local_id(raw_isbn):
            isbn = raw_isbn.upper()
        else:
            isbn = _normalize_isbn(raw_isbn)
            if len(isbn) not in (10, 13):
                logger.warning("CSV import: skipping invalid ISBN %r", row.get("isbn"))
                continue

        if not title:
            title = isbn

        year = None
        year_raw = _optional_text(row.get("publication_year") or row.get("year") or "")
        if year_raw:
            try:
                year = int(float(year_raw))
            except ValueError:
                year = None

        original_year = None
        oy_raw = _optional_text(row.get("original_year") or "")
        if oy_raw:
            try:
                original_year = int(float(oy_raw))
            except ValueError:
                original_year = None

        cleaned.append(
            {
                "isbn": isbn,
                "title": title,
                "authors": normalize_authors(row.get("authors")),
                "publication_year": year,
                "genre": normalize_labels(row.get("genre")),
                "publisher": _optional_text(row.get("publisher")),
                "cover_url": _optional_text(row.get("cover_url")),
                "description": _optional_text(row.get("description")),
                "location": _optional_text(row.get("location")),
                "notes": _optional_text(row.get("notes")),
                "legal_deposit": _legal_deposit_from_row(row),
                "collection": _optional_text(row.get("collection") or row.get("coleccion")),
                "volume": _optional_text(row.get("volume") or row.get("volumen") or row.get("tomo")),
                "original_year": original_year,
                "translators": normalize_labels(row.get("translators") or row.get("traductores")),
                "original_title": _optional_text(
                    row.get("original_title") or row.get("titulo_original")
                ),
                "favourite": _parse_bool(row["favourite"])
                if "favourite" in row and _optional_text(row.get("favourite")) != ""
                else False,
                "source": _optional_text(row.get("source")) or "import",
                "created_at": _parse_ts(row.get("created_at")),
                "updated_at": _parse_ts(row.get("updated_at")),
            }
        )
    return cleaned


async def insert_books(conn: DbConnection, books: list[dict[str, Any]]) -> list[str]:
    """Insert books; return ISBNs that were newly inserted (conflicts skipped)."""
    inserted_isbns: list[str] = []
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
        # asyncpg: "INSERT 0 1"; sqlite rowcount may be 1 or -1 depending on version
        if result.startswith("INSERT") and not result.rstrip().endswith(" 0"):
            inserted_isbns.append(book["isbn"])
    return inserted_isbns
