"""Serve the SPA shell."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.paths import STATIC_DIR

router = APIRouter(tags=["ui"])


@router.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
