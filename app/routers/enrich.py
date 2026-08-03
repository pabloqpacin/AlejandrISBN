"""HTTP routes for optional online enrichment (fill empty fields)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.services import enrich as enrich_svc

router = APIRouter(prefix="/api/enrich", tags=["enrich"])


class EnrichPreviewRequest(BaseModel):
    isbns: Optional[list[str]] = None
    fill_empty_only: bool = True
    limit: int = Field(default=enrich_svc.DEFAULT_LIMIT, ge=1, le=enrich_svc.MAX_LIMIT)


class EnrichApplyItem(BaseModel):
    isbn: str
    fields: dict[str, Any]


class EnrichApplyRequest(BaseModel):
    updates: list[EnrichApplyItem]
    fill_empty_only: bool = True


@router.post("/candidates")
async def enrich_candidates(payload: EnrichPreviewRequest, db=Depends(get_db)) -> dict:
    """List books that may need enrichment (no online calls)."""
    books = await enrich_svc.select_candidate_isbns(
        db,
        isbns=payload.isbns,
        limit=payload.limit,
    )
    return {
        "count": len(books),
        "items": [
            {"isbn": book["isbn"], "title": book.get("title") or ""}
            for book in books
        ],
    }


@router.post("/preview")
async def enrich_preview(payload: EnrichPreviewRequest, db=Depends(get_db)) -> dict:
    """Look up online metadata and return suggested fills (no DB writes)."""
    try:
        return await enrich_svc.preview_enrichment(
            db,
            isbns=payload.isbns,
            fill_empty_only=payload.fill_empty_only,
            limit=payload.limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo consultar catálogos: {exc}") from exc


@router.post("/apply")
async def enrich_apply(payload: EnrichApplyRequest, db=Depends(get_db)) -> dict:
    """Apply user-confirmed field updates."""
    if not payload.updates:
        raise HTTPException(status_code=400, detail="Sin cambios que aplicar")
    return await enrich_svc.apply_updates(
        db,
        [item.model_dump() for item in payload.updates],
        fill_empty_only=payload.fill_empty_only,
    )
