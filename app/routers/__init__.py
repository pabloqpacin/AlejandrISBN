"""HTTP route modules (FastAPI APIRouter)."""

from __future__ import annotations

from fastapi import FastAPI

from app.routers import (
    batch,
    enrich,
    export,
    health,
    import_books,
    items,
    lookup,
    ui,
)


def include_routers(app: FastAPI) -> None:
    """Register all API / UI routers on the FastAPI app."""
    app.include_router(ui.router)
    app.include_router(health.router)
    app.include_router(items.router)
    app.include_router(lookup.router)
    app.include_router(export.router)
    app.include_router(import_books.router)
    app.include_router(enrich.router)
    app.include_router(batch.router)
