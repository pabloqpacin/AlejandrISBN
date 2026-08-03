"""AlejandrISBN FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import close_pool, init_db, init_pool
from app.paths import STATIC_DIR
from app.routers import include_routers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_pool()
    await init_db()
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(
    title="AlejandrISBN",
    description=(
        "Inventario personal de biblioteca por ISBN.\n\n"
        "- UI: `/`\n"
        "- OpenAPI JSON (portable): `/openapi.json`\n"
        "- Swagger UI: `/docs`\n"
        "- ReDoc: `/redoc`"
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "health", "description": "Estado del servicio y de la base de datos"},
        {"name": "books", "description": "CRUD e inventario"},
        {"name": "lookup", "description": "Metadatos online por ISBN (sin guardar)"},
        {"name": "export", "description": "Descargas del inventario"},
        {"name": "import", "description": "Importar inventario (JSON/CSV, sin red)"},
        {"name": "enrich", "description": "Completar campos vacíos vía catálogos online"},
        {"name": "batch", "description": "Operaciones sobre varios registros"},
        {"name": "ui", "description": "Frontend estático"},
    ],
)

include_routers(app)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def disable_static_cache(request, call_next):
    """Avoid stale UI after rebuilds (browser F5 was keeping old app.js)."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response
