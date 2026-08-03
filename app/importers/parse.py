"""Parse inventory files (JSON/CSV) into book row dicts for insert."""

from __future__ import annotations

import logging
from csv import DictReader
from datetime import datetime
from io import StringIO
from typing import Any, Optional

logger = logging.getLogger("alejandrisbn.importers")

_NA_VALUES = {"", "n/a", "na", "n.a.", "n.a", "none", "null", "-", "—", "–"}


def parse_ts(value: Any) -> Optional[datetime]:
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


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "t", "yes", "y", "si", "sí"}


def normalize_isbn_digits(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isalnum()).upper()


def optional_text(value: Any) -> str:
    """Treat blank / n/a placeholders as empty string."""
    text = str(value or "").strip()
    if text.lower() in _NA_VALUES:
        return ""
    return text


def legal_deposit_from_row(row: dict[str, Any]) -> str:
    return optional_text(row.get("legal_deposit") or row.get("deposito_legal") or "")


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
        raise ValueError("JSON seed must be a list of books or an object with a 'books' array")

    cleaned: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = optional_text(row.get("title"))
        raw_isbn = optional_text(row.get("isbn"))

        if not title and not raw_isbn:
            continue

        if not raw_isbn:
            isbn = generate_local_id()
        elif is_local_id(raw_isbn):
            isbn = raw_isbn.upper()
        else:
            isbn = normalize_isbn_digits(raw_isbn)
            if len(isbn) not in (10, 13):
                logger.warning("JSON import: skipping invalid ISBN %r", row.get("isbn"))
                continue

        if not title:
            title = isbn

        year = row.get("publication_year")
        if year in ("", None):
            year = None
        elif not isinstance(year, int):
            try:
                year = int(year)
            except (TypeError, ValueError):
                year = None

        original_year = row.get("original_year")
        if original_year in ("", None):
            original_year = None
        elif not isinstance(original_year, int):
            try:
                original_year = int(original_year)
            except (TypeError, ValueError):
                original_year = None

        cleaned.append(
            {
                "isbn": isbn,
                "title": title,
                "authors": normalize_authors(row.get("authors")),
                "publication_year": year,
                "genre": normalize_labels(row.get("genre")),
                "publisher": optional_text(row.get("publisher")),
                "cover_url": optional_text(row.get("cover_url")),
                "description": optional_text(row.get("description")),
                "location": optional_text(row.get("location")),
                "notes": optional_text(row.get("notes")),
                "legal_deposit": legal_deposit_from_row(row),
                "collection": optional_text(row.get("collection") or row.get("coleccion")),
                "volume": optional_text(row.get("volume") or row.get("volumen") or row.get("tomo")),
                "original_year": original_year,
                "translators": normalize_labels(row.get("translators") or row.get("traductores")),
                "original_title": optional_text(
                    row.get("original_title") or row.get("titulo_original")
                ),
                "favourite": parse_bool(row["favourite"]) if "favourite" in row else False,
                "source": optional_text(row.get("source")) or "seed",
                "created_at": parse_ts(row.get("created_at")),
                "updated_at": parse_ts(row.get("updated_at")),
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
        if not any(optional_text(v) for v in row.values()):
            continue

        title = optional_text(row.get("title"))
        raw_isbn = optional_text(row.get("isbn"))

        if not title and not raw_isbn:
            continue

        if not raw_isbn:
            isbn = generate_local_id()
        elif is_local_id(raw_isbn):
            isbn = raw_isbn.upper()
        else:
            isbn = normalize_isbn_digits(raw_isbn)
            if len(isbn) not in (10, 13):
                logger.warning("CSV import: skipping invalid ISBN %r", row.get("isbn"))
                continue

        if not title:
            title = isbn

        year = None
        year_raw = optional_text(row.get("publication_year") or row.get("year") or "")
        if year_raw:
            try:
                year = int(float(year_raw))
            except ValueError:
                year = None

        original_year = None
        oy_raw = optional_text(row.get("original_year") or "")
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
                "publisher": optional_text(row.get("publisher")),
                "cover_url": optional_text(row.get("cover_url")),
                "description": optional_text(row.get("description")),
                "location": optional_text(row.get("location")),
                "notes": optional_text(row.get("notes")),
                "legal_deposit": legal_deposit_from_row(row),
                "collection": optional_text(row.get("collection") or row.get("coleccion")),
                "volume": optional_text(row.get("volume") or row.get("volumen") or row.get("tomo")),
                "original_year": original_year,
                "translators": normalize_labels(row.get("translators") or row.get("traductores")),
                "original_title": optional_text(
                    row.get("original_title") or row.get("titulo_original")
                ),
                "favourite": parse_bool(row["favourite"])
                if "favourite" in row and optional_text(row.get("favourite")) != ""
                else False,
                "source": optional_text(row.get("source")) or "import",
                "created_at": parse_ts(row.get("created_at")),
                "updated_at": parse_ts(row.get("updated_at")),
            }
        )
    return cleaned
