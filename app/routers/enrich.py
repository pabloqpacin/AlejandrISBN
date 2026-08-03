"""HTTP routes for optional online enrichment (fill empty fields)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.services import enrich as enrich_svc

router = APIRouter(prefix="/api/enrich", tags=["enrich"])


class EnrichPreviewRequest(BaseModel):
    ids: Optional[list[str]] = None
    isbns: Optional[list[str]] = None  # legacy
    fill_empty_only: bool = True
    limit: Optional[int] = Field(default=None, ge=1)


class EnrichApplyItem(BaseModel):
    id: Optional[str] = None
    isbn: Optional[str] = None  # legacy
    fields: dict[str, Any]


class EnrichApplyRequest(BaseModel):
    updates: list[EnrichApplyItem]
    fill_empty_only: bool = True


@router.post("/candidates")
async def enrich_candidates(payload: EnrichPreviewRequest, db=Depends(get_db)) -> dict:
    """List items that may need enrichment (no online calls)."""
    items = await enrich_svc.select_candidate_items(
        db,
        ids=payload.ids,
        limit=payload.limit,
    )
    return {
        "count": len(items),
        "items": [
            {
                "id": item["id"],
                "isbn": item.get("isbn") or "",
                "title": item.get("title") or "",
            }
            for item in items
        ],
    }


@router.post("/preview")
async def enrich_preview(payload: EnrichPreviewRequest, db=Depends(get_db)) -> dict:
    """Look up online metadata and return suggested fills (no DB writes)."""
    try:
        return await enrich_svc.preview_enrichment(
            db,
            ids=payload.ids,
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
