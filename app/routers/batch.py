"""Batch operations on selected inventory rows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.schemas import normalize_authors, normalize_book_key, normalize_labels

router = APIRouter(prefix="/api/books/batch", tags=["batch"])

ALLOWED_BATCH_FIELDS = {
    "title",
    "authors",
    "publication_year",
    "genre",
    "publisher",
    "cover_url",
    "description",
    "location",
    "notes",
    "legal_deposit",
    "collection",
    "volume",
    "original_year",
    "translators",
    "original_title",
    "favourite",
}


class BatchDeleteRequest(BaseModel):
    isbns: list[str] = Field(min_length=1)


class BatchUpdateRequest(BaseModel):
    isbns: list[str] = Field(min_length=1)
    fields: dict[str, Any]


def _normalize_isbns(raw: list[str]) -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    for value in raw:
        try:
            key = normalize_book_key(value)
        except ValueError:
            continue
        if key in seen:
            continue
        seen.add(key)
        clean.append(key)
    return clean


def _normalize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in ALLOWED_BATCH_FIELDS:
            continue
        if key in {"authors", "translators"}:
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
    isbns = _normalize_isbns(payload.isbns)
    if not isbns:
        raise HTTPException(status_code=400, detail="Sin ISBN válidos")

    deleted = 0
    missing: list[str] = []
    for isbn in isbns:
        result = await db.execute("DELETE FROM books WHERE isbn = $1", isbn)
        if result == "DELETE 0":
            missing.append(isbn)
        else:
            deleted += 1

    return {"deleted": deleted, "missing": missing, "requested": len(isbns)}


@router.post("/update")
async def batch_update(payload: BatchUpdateRequest, db=Depends(get_db)) -> dict:
    isbns = _normalize_isbns(payload.isbns)
    if not isbns:
        raise HTTPException(status_code=400, detail="Sin ISBN válidos")
    patch = _normalize_fields(payload.fields)

    updated = 0
    missing: list[str] = []
    for isbn in isbns:
        exists = await db.fetchval("SELECT isbn FROM books WHERE isbn = $1", isbn)
        if not exists:
            missing.append(isbn)
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

    return {
        "updated": updated,
        "missing": missing,
        "requested": len(isbns),
        "fields": list(patch.keys()),
    }
