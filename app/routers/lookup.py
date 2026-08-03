"""Online ISBN metadata preview (no DB write)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import normalize_isbn
from app.services.isbn_lookup import lookup_isbn

router = APIRouter(tags=["lookup"])


@router.get("/api/lookup/{isbn}")
async def preview_lookup(isbn: str) -> dict:
    """Preview online metadata without saving."""
    try:
        clean = normalize_isbn(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return await lookup_isbn(clean)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
