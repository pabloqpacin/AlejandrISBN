"""Inventory import (JSON / CSV upload, offline)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.db import get_db
from app.seed import _books_from_import_csv, _books_from_json, _insert_books

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/books")
async def import_books(
    file: UploadFile = File(..., description="JSON or CSV export/seed"),
    db=Depends(get_db),
) -> dict:
    """Import books from a JSON or CSV file (same shapes as ``/api/export/books``).

    Existing ISBNs are skipped (``ON CONFLICT DO NOTHING``).
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Codificación inválida: {exc}") from exc

    name = (file.filename or "").lower()
    ctype = (file.content_type or "").lower()
    is_csv = name.endswith(".csv") or "csv" in ctype
    is_json = name.endswith(".json") or "json" in ctype

    if not is_csv and not is_json:
        stripped = text.lstrip()
        is_json = stripped.startswith("{") or stripped.startswith("[")
        is_csv = not is_json

    try:
        if is_csv:
            books = _books_from_import_csv(text)
        else:
            books = _books_from_json(json.loads(text))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not books:
        raise HTTPException(status_code=400, detail="No hay libros válidos en el archivo")

    for book in books:
        if not book.get("source") or book["source"] in {"seed", "seed-csv:lookup", "seed-csv:manual"}:
            book["source"] = "import"

    inserted_isbns = await _insert_books(db, books)
    return {
        "ok": True,
        "format": "csv" if is_csv else "json",
        "parsed": len(books),
        "inserted": len(inserted_isbns),
        "skipped": len(books) - len(inserted_isbns),
        "inserted_isbns": inserted_isbns,
    }
