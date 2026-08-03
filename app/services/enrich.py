"""Fill empty bibliographic fields from online ISBN lookup (user-confirmed).

Import never calls this — it stays offline. The UI asks for a preview,
then posts confirmed field updates to ``apply_updates``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.schemas import is_local_id, is_print_media

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

LOOKUP_CONCURRENCY = 3


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def field_is_empty(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    if field == "title":
        text = str(value or "").strip()
        isbn = str(item.get("isbn") or "").strip()
        # Import CSV may stash the ISBN as a placeholder title.
        return not text or (isbn and text.upper() == isbn.upper())
    return _is_blank(value)


def item_needs_enrichment(item: dict[str, Any]) -> bool:
    isbn = str(item.get("isbn") or "").strip()
    if not isbn or is_local_id(isbn):
        return False
    if not is_print_media(item.get("media_type") or "book"):
        return False
    return any(field_is_empty(item, field) for field in ENRICHABLE_FIELDS)


# Back-compat names
book_needs_enrichment = item_needs_enrichment


def suggested_fills(
    item: dict[str, Any],
    meta: dict[str, Any],
    *,
    fill_empty_only: bool = True,
) -> list[dict[str, Any]]:
    """Diff current item vs lookup metadata."""
    fields: list[dict[str, Any]] = []
    for name in ENRICHABLE_FIELDS:
        suggested = meta.get(name)
        if suggested is None:
            continue
        if isinstance(suggested, str):
            suggested = suggested.strip()
            if not suggested:
                continue
        current = item.get(name)
        if isinstance(current, str):
            current_out: Any = current
        else:
            current_out = current

        empty = field_is_empty(item, name)
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


async def select_candidate_items(
    db: Any,
    *,
    ids: Optional[list[str]] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Load inventory rows eligible for enrichment."""
    from app.db.common import record_to_dict

    capped = max(1, int(limit)) if limit is not None else None

    if ids:
        items: list[dict[str, Any]] = []
        for raw in ids:
            key = str(raw or "").strip()
            if not key:
                continue
            row = await db.fetchrow("SELECT * FROM items WHERE id = $1", key)
            if row:
                item = record_to_dict(row)
                if item_needs_enrichment(item):
                    items.append(item)
            if capped is not None and len(items) >= capped:
                break
        return items

    rows = await db.fetch(
        """
        SELECT * FROM items
        WHERE isbn IS NOT NULL AND TRIM(isbn) <> ''
        ORDER BY updated_at DESC
        """
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        item = record_to_dict(row)
        if item_needs_enrichment(item):
            candidates.append(item)
        if capped is not None and len(candidates) >= capped:
            break
    return candidates


# Back-compat
select_candidate_isbns = select_candidate_items


async def preview_enrichment(
    db: Any,
    *,
    ids: Optional[list[str]] = None,
    isbns: Optional[list[str]] = None,
    fill_empty_only: bool = True,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    from app.services.isbn_lookup import lookup_isbn

    # Legacy callers may still pass isbns; resolve to items by ISBN.
    resolved_ids = list(ids or [])
    if isbns and not resolved_ids:
        for raw in isbns:
            key = str(raw or "").strip()
            if not key or is_local_id(key):
                continue
            row = await db.fetchrow("SELECT id FROM items WHERE isbn = $1", key)
            if row:
                resolved_ids.append(row["id"])

    candidates = await select_candidate_items(
        db, ids=resolved_ids or None, limit=limit
    )
    sem = asyncio.Semaphore(LOOKUP_CONCURRENCY)
    suggestions: list[dict[str, Any]] = []
    failed = 0

    async def one(item: dict[str, Any]) -> None:
        nonlocal failed
        isbn = item["isbn"]
        item_id = item["id"]
        async with sem:
            try:
                meta = await lookup_isbn(isbn)
            except ValueError as exc:
                failed += 1
                suggestions.append(
                    {
                        "id": item_id,
                        "isbn": isbn,
                        "title": item.get("title") or "",
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
                        "id": item_id,
                        "isbn": isbn,
                        "title": item.get("title") or "",
                        "lookup_source": "",
                        "fields": [],
                        "error": f"Error de red: {exc}",
                    }
                )
                return

        fields = suggested_fills(item, meta, fill_empty_only=fill_empty_only)
        if not fields and not fill_empty_only:
            return
        suggestions.append(
            {
                "id": item_id,
                "isbn": isbn,
                "title": item.get("title") or "",
                "lookup_source": meta.get("source") or "",
                "fields": fields,
                "error": None,
            }
        )

    await asyncio.gather(*(one(item) for item in candidates))
    suggestions.sort(key=lambda item: (item.get("isbn") or "", item.get("id") or ""))

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
    from app.schemas import normalize_authors, normalize_labels

    updated = 0
    skipped = 0
    errors: list[dict[str, str]] = []

    for entry in updates:
        item_id = str(entry.get("id") or "").strip()
        raw_isbn = str(entry.get("isbn") or "").strip()
        fields = entry.get("fields") or {}
        if not isinstance(fields, dict) or not fields:
            skipped += 1
            continue

        if item_id:
            row = await db.fetchrow("SELECT * FROM items WHERE id = $1", item_id)
        elif raw_isbn and not is_local_id(raw_isbn):
            row = await db.fetchrow("SELECT * FROM items WHERE isbn = $1", raw_isbn)
        else:
            skipped += 1
            continue

        if not row:
            errors.append({"id": item_id or raw_isbn, "error": "No encontrado"})
            continue
        item = record_to_dict(row)
        item_id = item["id"]

        if not item_needs_enrichment(item) and fill_empty_only:
            # Still allow apply when fields were already previewed as empty.
            pass

        patch: dict[str, Any] = {}
        for name, value in fields.items():
            if name not in ENRICHABLE_FIELDS:
                continue
            if fill_empty_only and not field_is_empty(item, name):
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
        values.append(item_id)
        await db.fetchrow(
            f"""
            UPDATE items
            SET {', '.join(assignments)}, updated_at = NOW()
            WHERE id = ${len(values)}
            RETURNING id
            """,
            *values,
        )
        updated += 1

    return {"updated": updated, "skipped": skipped, "errors": errors}
