from contextlib import asynccontextmanager
from csv import DictWriter
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Optional

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.database import close_pool, get_db, init_db, init_pool, record_to_dict
from app.schemas import (
    BookCreate,
    BookOut,
    BookUpdate,
    generate_local_id,
    is_local_id,
    normalize_book_key,
    normalize_isbn,
)
from app.services.isbn_lookup import lookup_isbn

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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
        {"name": "ui", "description": "Frontend estático"},
    ],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def disable_static_cache(request, call_next):
    """Avoid stale UI after rebuilds (browser F5 was keeping old app.js)."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


def row_to_book(row: asyncpg.Record) -> BookOut:
    return BookOut(**record_to_dict(row))


@app.get("/", tags=["ui"], include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health", tags=["health"])
async def health(db: asyncpg.Connection = Depends(get_db)) -> dict:
    await db.fetchval("SELECT 1")
    return {"status": "ok", "app": "AlejandrISBN", "db": "postgres"}


@app.get("/api/books", response_model=list[BookOut], tags=["books"])
async def list_books(
    q: Optional[list[str]] = Query(
        None,
        description="Search terms (repeat param). Match any term; OR across terms.",
    ),
    favourite: Optional[bool] = Query(None, description="Filter by favourite flag"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: asyncpg.Connection = Depends(get_db),
) -> list[BookOut]:
    clauses: list[str] = []
    params: list = []

    terms = [term.strip() for term in (q or []) if term and term.strip()]
    term_clauses: list[str] = []
    for term in terms:
        params.append(f"%{term}%")
        idx = len(params)
        term_clauses.append(
            f"""(
                unaccent(isbn) ILIKE unaccent(${idx})
                OR unaccent(title) ILIKE unaccent(${idx})
                OR unaccent(authors) ILIKE unaccent(${idx})
                OR unaccent(genre) ILIKE unaccent(${idx})
                OR unaccent(publisher) ILIKE unaccent(${idx})
                OR unaccent(location) ILIKE unaccent(${idx})
                OR unaccent(notes) ILIKE unaccent(${idx})
                OR unaccent(legal_deposit) ILIKE unaccent(${idx})
                OR unaccent(collection) ILIKE unaccent(${idx})
            )"""
        )
    if term_clauses:
        clauses.append(f"({' OR '.join(term_clauses)})")

    if favourite is not None:
        params.append(favourite)
        clauses.append(f"favourite = ${len(params)}")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    order = "title ASC" if terms else "created_at DESC"
    rows = await db.fetch(
        f"""
        SELECT * FROM books
        {where}
        ORDER BY {order}
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """,
        *params,
    )
    return [row_to_book(row) for row in rows]


@app.get("/api/suggestions", tags=["books"])
async def field_suggestions(
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Distinct authors / genre / location / collection values for form autocomplete.

    Authors and genre are treated as ``;``-separated labels (one suggestion per label).
    """

    async def values_for(column: str) -> list[dict]:
        rows = await db.fetch(
            f"""
            SELECT TRIM({column}) AS value, COUNT(*)::int AS count
            FROM books
            WHERE TRIM({column}) <> ''
            GROUP BY TRIM({column})
            ORDER BY count DESC, value ASC
            """
        )
        return [{"value": row["value"], "count": row["count"]} for row in rows]

    async def label_values_for(column: str) -> list[dict]:
        rows = await db.fetch(
            f"""
            SELECT TRIM(label) AS value, COUNT(*)::int AS count
            FROM books,
            LATERAL unnest(string_to_array({column}, ';')) AS label
            WHERE TRIM(COALESCE({column}, '')) <> ''
              AND TRIM(label) <> ''
            GROUP BY TRIM(label)
            ORDER BY count DESC, value ASC
            """
        )
        return [{"value": row["value"], "count": row["count"]} for row in rows]

    return {
        "authors": await label_values_for("authors"),
        "genre": await label_values_for("genre"),
        "location": await values_for("location"),
        "collection": await values_for("collection"),
    }


@app.get("/api/export/books", tags=["export"])
async def export_books(
    format: str = Query("json", pattern="^(json|csv)$"),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    """Download full inventory as JSON (seed) or CSV (Sheets/Excel)."""
    rows = await db.fetch("SELECT * FROM books ORDER BY title ASC")
    books = []
    for row in rows:
        item = record_to_dict(row)
        books.append(
            {
                "isbn": item["isbn"],
                "title": item["title"],
                "authors": item.get("authors") or "",
                "publication_year": item.get("publication_year"),
                "genre": item.get("genre") or "",
                "publisher": item.get("publisher") or "",
                "cover_url": item.get("cover_url") or "",
                "description": item.get("description") or "",
                "location": item.get("location") or "",
                "notes": item.get("notes") or "",
                "legal_deposit": item.get("legal_deposit") or "",
                "collection": item.get("collection") or "",
                "favourite": bool(item.get("favourite")),
                "source": item.get("source") or "",
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    if format == "csv":
        fieldnames = [
            "isbn",
            "title",
            "authors",
            "publication_year",
            "genre",
            "publisher",
            "location",
            "notes",
            "legal_deposit",
            "collection",
            "favourite",
            "cover_url",
            "description",
            "source",
            "created_at",
            "updated_at",
        ]
        buffer = StringIO()
        writer = DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for book in books:
            writer.writerow(book)
        filename = f"alejandrisbn-books-{stamp}.csv"
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    filename = f"alejandrisbn-books-{stamp}.json"
    response = JSONResponse(content={"books": books})
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.get("/api/books/{isbn}", response_model=BookOut, tags=["books"])
async def get_book(
    isbn: str,
    db: asyncpg.Connection = Depends(get_db),
) -> BookOut:
    try:
        clean = normalize_book_key(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = await db.fetchrow("SELECT * FROM books WHERE isbn = $1", clean)
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")
    return row_to_book(row)


@app.post("/api/books", response_model=BookOut, status_code=201, tags=["books"])
async def create_book(
    payload: BookCreate,
    db: asyncpg.Connection = Depends(get_db),
) -> BookOut:
    # Manual entry (no ISBN): magazines, manuals, documents, etc.
    if payload.isbn is None or is_local_id(payload.isbn):
        key = payload.isbn or generate_local_id()
        existing = await db.fetchval("SELECT isbn FROM books WHERE isbn = $1", key)
        if existing:
            raise HTTPException(status_code=409, detail="Item already in inventory")

        row = await db.fetchrow(
            """
            INSERT INTO books (
                isbn, title, authors, publication_year, genre, publisher,
                cover_url, description, location, notes, legal_deposit, collection, favourite, source
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
            )
            RETURNING *
            """,
            key,
            (payload.title or "").strip(),
            (payload.authors or "").strip(),
            payload.publication_year,
            (payload.genre or "").strip(),
            (payload.publisher or "").strip(),
            (payload.cover_url or "").strip(),
            (payload.description or "").strip(),
            payload.location or "",
            payload.notes or "",
            payload.legal_deposit or "",
            payload.collection or "",
            payload.favourite,
            "manual",
        )
        return row_to_book(row)

    existing = await db.fetchval("SELECT isbn FROM books WHERE isbn = $1", payload.isbn)
    if existing:
        raise HTTPException(status_code=409, detail="Book already in inventory")

    try:
        meta = await lookup_isbn(payload.isbn)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    overrides = payload.model_dump(
        exclude={"isbn", "location", "notes", "legal_deposit", "collection", "favourite"},
        exclude_none=True,
    )
    for key, value in overrides.items():
        if isinstance(value, str):
            value = value.strip()
        if value not in (None, ""):
            meta[key] = value

    row = await db.fetchrow(
        """
        INSERT INTO books (
            isbn, title, authors, publication_year, genre, publisher,
            cover_url, description, location, notes, legal_deposit, collection, favourite, source
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        RETURNING *
        """,
        payload.isbn,
        meta["title"],
        meta.get("authors") or "",
        meta.get("publication_year"),
        meta.get("genre") or "",
        meta.get("publisher") or "",
        meta.get("cover_url") or "",
        meta.get("description") or "",
        payload.location or "",
        payload.notes or "",
        payload.legal_deposit or "",
        payload.collection or "",
        payload.favourite,
        meta.get("source") or "",
    )
    return row_to_book(row)


ALLOWED_UPDATE_FIELDS = {
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
    "favourite",
}


@app.patch("/api/books/{isbn}", response_model=BookOut, tags=["books"])
async def update_book(
    isbn: str,
    payload: BookUpdate,
    db: asyncpg.Connection = Depends(get_db),
) -> BookOut:
    try:
        clean = normalize_book_key(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = await db.fetchrow("SELECT * FROM books WHERE isbn = $1", clean)
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")

    data = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if key in ALLOWED_UPDATE_FIELDS
    }
    if not data:
        return row_to_book(row)

    assignments = []
    values: list = []
    for index, (key, value) in enumerate(data.items(), start=1):
        assignments.append(f"{key} = ${index}")
        values.append(value)
    values.append(clean)
    isbn_param = len(values)

    row = await db.fetchrow(
        f"""
        UPDATE books
        SET {', '.join(assignments)}, updated_at = NOW()
        WHERE isbn = ${isbn_param}
        RETURNING *
        """,
        *values,
    )
    return row_to_book(row)


@app.delete("/api/books/{isbn}", status_code=204, tags=["books"])
async def delete_book(
    isbn: str,
    db: asyncpg.Connection = Depends(get_db),
) -> None:
    try:
        clean = normalize_book_key(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = await db.execute("DELETE FROM books WHERE isbn = $1", clean)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Book not found")


@app.get("/api/lookup/{isbn}", tags=["lookup"])
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
