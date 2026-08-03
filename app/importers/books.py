"""Offline inventory import helpers (JSON / CSV → item rows → DB insert)."""

from __future__ import annotations

import logging
import uuid
from csv import DictReader
from datetime import datetime
from io import StringIO
from typing import Any, Optional

from app.db import DbConnection
from app.schemas import MediaType, is_local_id, is_print_media

logger = logging.getLogger("alejandrisbn.importers")

_NA_VALUES = {"", "n/a", "na", "n.a.", "n.a", "none", "null", "-", "—", "–"}
_VALID_MEDIA = {m.value for m in MediaType}


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
    text = str(value or "").strip()
    if text.lower() in _NA_VALUES:
        return ""
    return text


def _legal_deposit_from_row(row: dict[str, Any]) -> str:
    return _optional_text(row.get("legal_deposit") or row.get("deposito_legal") or "")


def _parse_media_type(row: dict[str, Any]) -> str:
    raw = _optional_text(row.get("media_type") or row.get("tipo") or "").lower()
    if raw in _VALID_MEDIA:
        return raw
    return "book"


def _parse_item_id(row: dict[str, Any]) -> str:
    raw = _optional_text(row.get("id"))
    if raw:
        return raw
    return str(uuid.uuid4())


def _isbn_from_row(row: dict[str, Any], *, media_type: str) -> Optional[str]:
    if not is_print_media(media_type):
        return None
    raw_isbn = _optional_text(row.get("isbn"))
    if not raw_isbn or is_local_id(raw_isbn):
        return None
    isbn = _normalize_isbn(raw_isbn)
    if len(isbn) not in (10, 13):
        return "__invalid__"
    return isbn


def _year_from(row: dict[str, Any], *keys: str) -> Optional[int]:
    for key in keys:
        raw = _optional_text(row.get(key) or "")
        if not raw:
            continue
        try:
            return int(float(raw))
        except ValueError:
            continue
    return None


def _clean_row(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    from app.schemas import normalize_authors, normalize_labels, resolve_placement

    title = _optional_text(row.get("title"))
    media_type = _parse_media_type(row)
    isbn = _isbn_from_row(row, media_type=media_type)
    if isbn == "__invalid__":
        logger.warning("Import: skipping invalid ISBN %r for %r", row.get("isbn"), title)
        return None
    if not title:
        if isbn:
            title = isbn
        else:
            return None

    room, furniture, composed = resolve_placement(
        room=_optional_text(row.get("room") or row.get("habitacion") or row.get("habitación")),
        furniture=_optional_text(
            row.get("furniture") or row.get("mueble") or row.get("estanteria") or row.get("estantería")
        ),
        location=_optional_text(row.get("location") or row.get("ubicacion") or row.get("ubicación")),
    )

    return {
        "id": _parse_item_id(row),
        "media_type": media_type,
        "isbn": isbn,
        "title": title,
        "authors": normalize_authors(row.get("authors")),
        "publication_year": row.get("publication_year")
        if isinstance(row.get("publication_year"), int)
        else _year_from(row, "publication_year", "year"),
        "genre": normalize_labels(row.get("genre")),
        "publisher": _optional_text(row.get("publisher")),
        "cover_url": _optional_text(row.get("cover_url")),
        "description": _optional_text(row.get("description")),
        "room": room,
        "furniture": furniture,
        "location": composed,
        "notes": _optional_text(row.get("notes")),
        "legal_deposit": _legal_deposit_from_row(row) if is_print_media(media_type) else "",
        "collection": _optional_text(row.get("collection") or row.get("coleccion")),
        "volume": _optional_text(row.get("volume") or row.get("volumen") or row.get("tomo")),
        "original_year": row.get("original_year")
        if isinstance(row.get("original_year"), int)
        else _year_from(row, "original_year"),
        "translators": normalize_labels(row.get("translators") or row.get("traductores")),
        "original_title": _optional_text(row.get("original_title") or row.get("titulo_original")),
        "favourite": bool(row.get("favourite", False)),
        "source": _optional_text(row.get("source")) or "import",
        "created_at": _parse_ts(row.get("created_at")),
        "updated_at": _parse_ts(row.get("updated_at")),
    }


def items_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            rows = payload["items"]
        elif isinstance(payload.get("books"), list):
            rows = payload["books"]
        else:
            rows = [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("JSON must be a list of items or an object with an 'items'/'books' array")

    cleaned: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = _clean_row(row)
        if item:
            cleaned.append(item)
    return cleaned


def items_from_csv(text: str) -> list[dict[str, Any]]:
    """Parse an export-style CSV into item rows for insert."""
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
        if "favourite" in row and _optional_text(row.get("favourite")) != "":
            row["favourite"] = _parse_bool(row["favourite"])
        else:
            row["favourite"] = False
        item = _clean_row(row)
        if item:
            cleaned.append(item)
    return cleaned


async def insert_items(conn: DbConnection, items: list[dict[str, Any]]) -> list[str]:
    """Insert items; return IDs that were newly inserted (conflicts skipped)."""
    inserted_ids: list[str] = []
    for item in items:
        # Skip if ISBN already present (print media).
        if item.get("isbn"):
            exists = await conn.fetchval("SELECT id FROM items WHERE isbn = $1", item["isbn"])
            if exists:
                continue
        exists_id = await conn.fetchval("SELECT id FROM items WHERE id = $1", item["id"])
        if exists_id:
            continue

        result = await conn.execute(
            """
            INSERT INTO items (
                id, media_type, isbn, title, authors, publication_year, genre, publisher,
                cover_url, description, location, room, furniture, notes, legal_deposit,
                collection, volume, original_year, translators, original_title,
                favourite, source, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9, $10, $11, $12, $13, $14, $15,
                $16, $17, $18, $19, $20,
                $21, $22,
                COALESCE($23, NOW()),
                COALESCE($24, NOW())
            )
            ON CONFLICT (id) DO NOTHING
            """,
            item["id"],
            item["media_type"],
            item["isbn"],
            item["title"],
            item["authors"],
            item["publication_year"],
            item["genre"],
            item["publisher"],
            item["cover_url"],
            item["description"],
            item.get("location") or "",
            item.get("room") or "",
            item.get("furniture") or "",
            item["notes"],
            item.get("legal_deposit") or "",
            item.get("collection") or "",
            item.get("volume") or "",
            item.get("original_year"),
            item.get("translators") or "",
            item.get("original_title") or "",
            item["favourite"],
            item["source"],
            item["created_at"],
            item["updated_at"],
        )
        if result.startswith("INSERT") and not result.rstrip().endswith(" 0"):
            inserted_ids.append(item["id"])
    return inserted_ids


# Back-compat aliases
books_from_json = items_from_json
books_from_csv = items_from_csv
insert_books = insert_items
