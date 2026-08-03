"""Inventory export (JSON / CSV download)."""

from __future__ import annotations

from csv import DictWriter
from datetime import datetime, timezone
from io import StringIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response

from app.db import get_db, record_to_dict

router = APIRouter(prefix="/api/export", tags=["export"])

EXPORT_FIELDS = [
    "id",
    "media_type",
    "isbn",
    "title",
    "authors",
    "publication_year",
    "genre",
    "publisher",
    "room",
    "furniture",
    "location",
    "notes",
    "legal_deposit",
    "collection",
    "volume",
    "original_year",
    "translators",
    "original_title",
    "favourite",
    "cover_url",
    "description",
    "source",
    "created_at",
    "updated_at",
]


def _row_to_export(row: dict) -> dict:
    from app.schemas import format_placement

    room = row.get("room") or ""
    furniture = row.get("furniture") or ""
    location = format_placement(room, furniture, row.get("location") or "")
    return {
        "id": row.get("id") or "",
        "media_type": row.get("media_type") or "book",
        "isbn": row.get("isbn") or "",
        "title": row.get("title") or "",
        "authors": row.get("authors") or "",
        "publication_year": row.get("publication_year"),
        "genre": row.get("genre") or "",
        "publisher": row.get("publisher") or "",
        "cover_url": row.get("cover_url") or "",
        "description": row.get("description") or "",
        "room": room,
        "furniture": furniture,
        "location": location,
        "notes": row.get("notes") or "",
        "legal_deposit": row.get("legal_deposit") or "",
        "collection": row.get("collection") or "",
        "volume": row.get("volume") or "",
        "original_year": row.get("original_year"),
        "translators": row.get("translators") or "",
        "original_title": row.get("original_title") or "",
        "favourite": bool(row.get("favourite")),
        "source": row.get("source") or "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


@router.get("/items")
async def export_items(
    format: str = Query("json", pattern="^(json|csv)$"),
    db=Depends(get_db),
) -> Response:
    """Download full inventory as JSON or CSV (Sheets/Excel)."""
    rows = await db.fetch("SELECT * FROM items ORDER BY title ASC")
    items = [_row_to_export(record_to_dict(row)) for row in rows]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    if format == "csv":
        buffer = StringIO()
        writer = DictWriter(buffer, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            writer.writerow(item)
        filename = f"alejandrisbn-items-{stamp}.csv"
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    filename = f"alejandrisbn-items-{stamp}.json"
    response = JSONResponse(content={"items": items})
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# Back-compat alias path
@router.get("/books")
async def export_books_legacy(
    format: str = Query("json", pattern="^(json|csv)$"),
    db=Depends(get_db),
) -> Response:
    return await export_items(format=format, db=db)
