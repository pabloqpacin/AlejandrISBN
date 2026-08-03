"""Inventory export (JSON / CSV download)."""

from __future__ import annotations

from csv import DictWriter
from datetime import datetime, timezone
from io import StringIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response

from app.db import get_db, record_to_dict

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/books")
async def export_books(
    format: str = Query("json", pattern="^(json|csv)$"),
    db=Depends(get_db),
) -> Response:
    """Download full inventory as JSON (seed) or CSV (Sheets/Excel)."""
    rows = await db.fetch("SELECT * FROM books ORDER BY title ASC")
    books = []
    for row in rows:
        item = record_to_dict(row)
        books.append(
            {
                "isbn": item["isbn"],
                "title": item["title"],
                "authors": item.get("authors") or "",
                "publication_year": item.get("publication_year"),
                "genre": item.get("genre") or "",
                "publisher": item.get("publisher") or "",
                "cover_url": item.get("cover_url") or "",
                "description": item.get("description") or "",
                "location": item.get("location") or "",
                "notes": item.get("notes") or "",
                "legal_deposit": item.get("legal_deposit") or "",
                "collection": item.get("collection") or "",
                "volume": item.get("volume") or "",
                "original_year": item.get("original_year"),
                "translators": item.get("translators") or "",
                "original_title": item.get("original_title") or "",
                "favourite": bool(item.get("favourite")),
                "source": item.get("source") or "",
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    if format == "csv":
        fieldnames = [
            "isbn",
            "title",
            "authors",
            "publication_year",
            "genre",
            "publisher",
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
        buffer = StringIO()
        writer = DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for book in books:
            writer.writerow(book)
        filename = f"alejandrisbn-books-{stamp}.csv"
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    filename = f"alejandrisbn-books-{stamp}.json"
    response = JSONResponse(content={"books": books})
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
