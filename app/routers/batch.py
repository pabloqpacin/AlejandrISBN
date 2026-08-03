"""Batch operations on selected inventory rows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.routers.common import ALLOWED_UPDATE_FIELDS
from app.schemas import MediaType, is_print_media, normalize_authors, normalize_labels

router = APIRouter(prefix="/api/items/batch", tags=["batch"])

ALLOWED_BATCH_FIELDS = ALLOWED_UPDATE_FIELDS - {"isbn"}


class BatchDeleteRequest(BaseModel):
    ids: list[str] = Field(min_length=1)


class BatchUpdateRequest(BaseModel):
    ids: list[str] = Field(min_length=1)
    fields: dict[str, Any]


def _normalize_ids(raw: list[str]) -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    for value in raw:
        key = str(value or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        clean.append(key)
    return clean


def _normalize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in ALLOWED_BATCH_FIELDS:
            continue
        if key == "media_type":
            try:
                patch[key] = MediaType(str(value).strip().lower()).value
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"media_type inválido: {value}") from exc
        elif key in {"authors", "translators"}:
            patch[key] = normalize_authors(value)
        elif key == "genre":
            patch[key] = normalize_labels(value)
        elif key in {"publication_year", "original_year"}:
            if value is None or value == "":
                patch[key] = None
            else:
                try:
                    patch[key] = int(value)
                except (TypeError, ValueError) as exc:
                    raise HTTPException(
                        status_code=400, detail=f"Valor inválido para {key}"
                    ) from exc
        elif key == "favourite":
            patch[key] = bool(value)
        elif isinstance(value, str):
            patch[key] = value.strip()
        else:
            patch[key] = value
    if not patch:
        raise HTTPException(status_code=400, detail="Ningún campo válido para actualizar")
    return patch


@router.post("/delete")
async def batch_delete(payload: BatchDeleteRequest, db=Depends(get_db)) -> dict:
    ids = _normalize_ids(payload.ids)
    if not ids:
        raise HTTPException(status_code=400, detail="Sin IDs válidos")

    deleted = 0
    missing: list[str] = []
    for item_id in ids:
        result = await db.execute("DELETE FROM items WHERE id = $1", item_id)
        if result == "DELETE 0":
            missing.append(item_id)
        else:
            deleted += 1

    return {"deleted": deleted, "missing": missing, "requested": len(ids)}


@router.post("/update")
async def batch_update(payload: BatchUpdateRequest, db=Depends(get_db)) -> dict:
    ids = _normalize_ids(payload.ids)
    if not ids:
        raise HTTPException(status_code=400, detail="Sin IDs válidos")
    patch = _normalize_fields(payload.fields)

    updated = 0
    missing: list[str] = []
    for item_id in ids:
        row = await db.fetchrow("SELECT * FROM items WHERE id = $1", item_id)
        if not row:
            missing.append(item_id)
            continue

        effective = dict(patch)
        next_type = effective.get("media_type") or row["media_type"]
        if not is_print_media(next_type):
            effective["isbn"] = None

        assignments = []
        values: list[Any] = []
        for index, (key, value) in enumerate(effective.items(), start=1):
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

    return {
        "updated": updated,
        "missing": missing,
        "requested": len(ids),
        "fields": list(patch.keys()),
    }
