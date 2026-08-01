from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import close_pool, get_db, init_db, init_pool, record_to_dict
from app.schemas import BookCreate, BookOut, BookUpdate, normalize_isbn
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
    description="Inventario de biblioteca por ISBN",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def row_to_book(row: asyncpg.Record) -> BookOut:
    return BookOut(**record_to_dict(row))


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health(db: asyncpg.Connection = Depends(get_db)) -> dict:
    await db.fetchval("SELECT 1")
    return {"status": "ok", "app": "AlejandrISBN", "db": "postgres"}


@app.get("/api/books", response_model=list[BookOut])
async def list_books(
    q: Optional[str] = Query(None, description="Search title, author, ISBN, genre, publisher"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: asyncpg.Connection = Depends(get_db),
) -> list[BookOut]:
    if q and q.strip():
        term = f"%{q.strip()}%"
        rows = await db.fetch(
            """
            SELECT * FROM books
            WHERE isbn ILIKE $1
               OR title ILIKE $1
               OR authors ILIKE $1
               OR genre ILIKE $1
               OR publisher ILIKE $1
               OR location ILIKE $1
               OR notes ILIKE $1
            ORDER BY title ASC
            LIMIT $2 OFFSET $3
            """,
            term,
            limit,
            offset,
        )
    else:
        rows = await db.fetch(
            """
            SELECT * FROM books
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return [row_to_book(row) for row in rows]


@app.get("/api/books/{isbn}", response_model=BookOut)
async def get_book(
    isbn: str,
    db: asyncpg.Connection = Depends(get_db),
) -> BookOut:
    try:
        clean = normalize_isbn(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = await db.fetchrow("SELECT * FROM books WHERE isbn = $1", clean)
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")
    return row_to_book(row)


@app.post("/api/books", response_model=BookOut, status_code=201)
async def create_book(
    payload: BookCreate,
    db: asyncpg.Connection = Depends(get_db),
) -> BookOut:
    existing = await db.fetchval("SELECT isbn FROM books WHERE isbn = $1", payload.isbn)
    if existing:
        raise HTTPException(status_code=409, detail="Book already in inventory")

    try:
        meta = await lookup_isbn(payload.isbn)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    overrides = payload.model_dump(exclude={"isbn", "location", "notes"}, exclude_none=True)
    for key, value in overrides.items():
        if isinstance(value, str):
            value = value.strip()
        if value not in (None, ""):
            meta[key] = value

    row = await db.fetchrow(
        """
        INSERT INTO books (
            isbn, title, authors, publication_year, genre, publisher,
            cover_url, description, location, notes, source
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
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
}


@app.patch("/api/books/{isbn}", response_model=BookOut)
async def update_book(
    isbn: str,
    payload: BookUpdate,
    db: asyncpg.Connection = Depends(get_db),
) -> BookOut:
    try:
        clean = normalize_isbn(isbn)
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


@app.delete("/api/books/{isbn}", status_code=204)
async def delete_book(
    isbn: str,
    db: asyncpg.Connection = Depends(get_db),
) -> None:
    try:
        clean = normalize_isbn(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = await db.execute("DELETE FROM books WHERE isbn = $1", clean)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Book not found")


@app.get("/api/lookup/{isbn}")
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
