"""Fill empty bibliographic fields from online ISBN lookup (user-confirmed).

Import/seed never call this — they stay offline. The UI asks for a preview,
then posts confirmed field updates to ``apply_updates``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.schemas import is_local_id

logger = logging.getLogger("alejandrisbn.enrich")

# Catalog fields only — never location / notes / legal_deposit / favourite.
ENRICHABLE_FIELDS = (
    "title",
    "authors",
    "publication_year",
    "genre",
    "publisher",
    "cover_url",
    "description",
    "original_title",
    "translators",
    "original_year",
)

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
LOOKUP_CONCURRENCY = 3


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def field_is_empty(book: dict[str, Any], field: str) -> bool:
    value = book.get(field)
    if field == "title":
        text = str(value or "").strip()
        isbn = str(book.get("isbn") or "").strip()
        # Import CSV may stash the ISBN as a placeholder title.
        return not text or text.upper() == isbn.upper()
    return _is_blank(value)


def book_needs_enrichment(book: dict[str, Any]) -> bool:
    if is_local_id(str(book.get("isbn") or "")):
        return False
    return any(field_is_empty(book, field) for field in ENRICHABLE_FIELDS)


def suggested_fills(
    book: dict[str, Any],
    meta: dict[str, Any],
    *,
    fill_empty_only: bool = True,
) -> list[dict[str, Any]]:
    """Diff current book vs lookup metadata."""
    fields: list[dict[str, Any]] = []
    for name in ENRICHABLE_FIELDS:
        suggested = meta.get(name)
        if suggested is None:
            continue
        if isinstance(suggested, str):
            suggested = suggested.strip()
            if not suggested:
                continue
        current = book.get(name)
        if isinstance(current, str):
            current_out: Any = current
        else:
            current_out = current

        empty = field_is_empty(book, name)
        if fill_empty_only and not empty:
            continue
        if not fill_empty_only and current_out == suggested:
            continue

        fields.append(
            {
                "name": name,
                "current": current_out if current_out is not None else "",
                "suggested": suggested,
                "empty": empty,
            }
        )
    return fields


async def select_candidate_isbns(
    db: Any,
    *,
    isbns: Optional[list[str]] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Load inventory rows eligible for enrichment."""
    from app.db.common import record_to_dict

    limit = max(1, min(int(limit), MAX_LIMIT))

    if isbns:
        books: list[dict[str, Any]] = []
        for raw in isbns[:limit]:
            key = str(raw or "").strip()
            if not key or is_local_id(key):
                continue
            row = await db.fetchrow("SELECT * FROM books WHERE isbn = $1", key)
            if row:
                books.append(record_to_dict(row))
        return books

    rows = await db.fetch(
        """
        SELECT * FROM books
        ORDER BY updated_at DESC
        LIMIT $1
        """,
        limit * 4,
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        book = record_to_dict(row)
        if book_needs_enrichment(book):
            candidates.append(book)
        if len(candidates) >= limit:
            break
    return candidates


async def preview_enrichment(
    db: Any,
    *,
    isbns: Optional[list[str]] = None,
    fill_empty_only: bool = True,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    from app.services.isbn_lookup import lookup_isbn

    candidates = await select_candidate_isbns(db, isbns=isbns, limit=limit)
    sem = asyncio.Semaphore(LOOKUP_CONCURRENCY)
    suggestions: list[dict[str, Any]] = []
    failed = 0

    async def one(book: dict[str, Any]) -> None:
        nonlocal failed
        isbn = book["isbn"]
        async with sem:
            try:
                meta = await lookup_isbn(isbn)
            except ValueError as exc:
                failed += 1
                suggestions.append(
                    {
                        "isbn": isbn,
                        "title": book.get("title") or "",
                        "lookup_source": "",
                        "fields": [],
                        "error": str(exc),
                    }
                )
                return
            except Exception as exc:
                failed += 1
                logger.exception("enrich lookup failed for %s", isbn)
                suggestions.append(
                    {
                        "isbn": isbn,
                        "title": book.get("title") or "",
                        "lookup_source": "",
                        "fields": [],
                        "error": f"Error de red: {exc}",
                    }
                )
                return

        fields = suggested_fills(book, meta, fill_empty_only=fill_empty_only)
        if not fields and not fill_empty_only:
            return
        suggestions.append(
            {
                "isbn": isbn,
                "title": book.get("title") or "",
                "lookup_source": meta.get("source") or "",
                "fields": fields,
                "error": None,
            }
        )

    await asyncio.gather(*(one(book) for book in candidates))
    suggestions.sort(key=lambda item: item["isbn"])

    with_changes = [s for s in suggestions if s.get("fields")]
    return {
        "scanned": len(candidates),
        "with_suggestions": len(with_changes),
        "failed": failed,
        "fill_empty_only": fill_empty_only,
        "suggestions": suggestions,
    }


async def apply_updates(
    db: Any,
    updates: list[dict[str, Any]],
    *,
    fill_empty_only: bool = True,
) -> dict[str, Any]:
    """Apply confirmed field maps. Re-checks emptiness when ``fill_empty_only``."""
    from app.db.common import record_to_dict
    from app.schemas import normalize_authors, normalize_book_key, normalize_labels

    updated = 0
    skipped = 0
    errors: list[dict[str, str]] = []

    for item in updates:
        raw_isbn = str(item.get("isbn") or "").strip()
        fields = item.get("fields") or {}
        if not raw_isbn or not isinstance(fields, dict) or not fields:
            skipped += 1
            continue
        try:
            isbn = normalize_book_key(raw_isbn)
        except ValueError as exc:
            errors.append({"isbn": raw_isbn, "error": str(exc)})
            continue
        if is_local_id(isbn):
            skipped += 1
            continue

        row = await db.fetchrow("SELECT * FROM books WHERE isbn = $1", isbn)
        if not row:
            errors.append({"isbn": isbn, "error": "No encontrado"})
            continue
        book = record_to_dict(row)

        patch: dict[str, Any] = {}
        for name, value in fields.items():
            if name not in ENRICHABLE_FIELDS:
                continue
            if fill_empty_only and not field_is_empty(book, name):
                continue
            if name in {"authors", "translators"}:
                value = normalize_authors(value)
            elif name == "genre":
                value = normalize_labels(value)
            elif name in {"publication_year", "original_year"}:
                if value is None or value == "":
                    continue
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            elif isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
            patch[name] = value

        if not patch:
            skipped += 1
            continue

        assignments = []
        values: list[Any] = []
        for index, (key, value) in enumerate(patch.items(), start=1):
            assignments.append(f"{key} = ${index}")
            values.append(value)
        values.append(isbn)
        await db.fetchrow(
            f"""
            UPDATE books
            SET {', '.join(assignments)}, updated_at = NOW()
            WHERE isbn = ${len(values)}
            RETURNING isbn
            """,
            *values,
        )
        updated += 1

    return {"updated": updated, "skipped": skipped, "errors": errors}
