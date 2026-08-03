"""Health check."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db import get_db
from app.db import runtime as db_runtime

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health(db=Depends(get_db)) -> dict:
    from app.version import get_version

    await db.fetchval("SELECT 1")
    return {
        "status": "ok",
        "app": "AlejandrISBN",
        "db": db_runtime.BACKEND,
        "version": get_version(),
    }
