"""Inventory import (JSON / CSV upload, offline)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.db import get_db
from app.importers import items_from_csv, items_from_json, insert_items

router = APIRouter(prefix="/api/import", tags=["import"])

_LEGACY_SEED_SOURCES = {"seed", "seed-csv:lookup", "seed-csv:manual"}


async def _import_payload(file: UploadFile, db) -> dict:
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
            items = items_from_csv(text)
        else:
            items = items_from_json(json.loads(text))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not items:
        raise HTTPException(status_code=400, detail="No hay ítems válidos en el archivo")

    for item in items:
        if not item.get("source") or item["source"] in _LEGACY_SEED_SOURCES:
            item["source"] = "import"

    inserted_ids = await insert_items(db, items)
    return {
        "ok": True,
        "format": "csv" if is_csv else "json",
        "parsed": len(items),
        "inserted": len(inserted_ids),
        "skipped": len(items) - len(inserted_ids),
        "inserted_ids": inserted_ids,
    }


@router.post("/items")
async def import_items(
    file: UploadFile = File(..., description="JSON or CSV inventory export"),
    db=Depends(get_db),
) -> dict:
    """Import items from a JSON or CSV file (same shapes as ``/api/export/items``).

    Also accepts legacy ``{"books": [...]}`` exports. Existing IDs / ISBNs are skipped.
    """
    return await _import_payload(file, db)


@router.post("/books")
async def import_books_legacy(
    file: UploadFile = File(..., description="JSON or CSV inventory export"),
    db=Depends(get_db),
) -> dict:
    return await _import_payload(file, db)
