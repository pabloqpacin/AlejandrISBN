from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import get_db, init_db
from app.schemas import BookCreate, BookOut, BookUpdate, normalize_isbn
from app.services.isbn_lookup import lookup_isbn

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="AlejandrISBN",
    description="Inventario de biblioteca por ISBN",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def row_to_book(row: aiosqlite.Row) -> BookOut:
    return BookOut(**dict(row))


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "app": "AlejandrISBN"}


@app.get("/api/books", response_model=list[BookOut])
async def list_books(
    q: Optional[str] = Query(None, description="Search title, author, ISBN, genre, publisher"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[BookOut]:
    if q and q.strip():
        term = f"%{q.strip()}%"
        cursor = await db.execute(
            """
            SELECT * FROM books
            WHERE isbn LIKE ? COLLATE NOCASE
               OR title LIKE ? COLLATE NOCASE
               OR authors LIKE ? COLLATE NOCASE
               OR genre LIKE ? COLLATE NOCASE
               OR publisher LIKE ? COLLATE NOCASE
               OR notes LIKE ? COLLATE NOCASE
            ORDER BY title COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            (term, term, term, term, term, term, limit, offset),
        )
    else:
        cursor = await db.execute(
            """
            SELECT * FROM books
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
    rows = await cursor.fetchall()
    return [row_to_book(row) for row in rows]


@app.get("/api/books/{isbn}", response_model=BookOut)
async def get_book(
    isbn: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> BookOut:
    try:
        clean = normalize_isbn(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cursor = await db.execute("SELECT * FROM books WHERE isbn = ?", (clean,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")
    return row_to_book(row)


@app.post("/api/books", response_model=BookOut, status_code=201)
async def create_book(
    payload: BookCreate,
    db: aiosqlite.Connection = Depends(get_db),
) -> BookOut:
    existing = await db.execute("SELECT isbn FROM books WHERE isbn = ?", (payload.isbn,))
    if await existing.fetchone():
        raise HTTPException(status_code=409, detail="Book already in inventory")

    try:
        meta = await lookup_isbn(payload.isbn)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await db.execute(
        """
        INSERT INTO books (
            isbn, title, authors, publication_year, genre, publisher,
            cover_url, description, notes, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.isbn,
            meta["title"],
            meta.get("authors") or "",
            meta.get("publication_year"),
            meta.get("genre") or "",
            meta.get("publisher") or "",
            meta.get("cover_url") or "",
            meta.get("description") or "",
            payload.notes or "",
            meta.get("source") or "",
        ),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM books WHERE isbn = ?", (payload.isbn,))
    row = await cursor.fetchone()
    return row_to_book(row)


@app.patch("/api/books/{isbn}", response_model=BookOut)
async def update_book(
    isbn: str,
    payload: BookUpdate,
    db: aiosqlite.Connection = Depends(get_db),
) -> BookOut:
    try:
        clean = normalize_isbn(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cursor = await db.execute("SELECT * FROM books WHERE isbn = ?", (clean,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return row_to_book(row)

    fields = []
    values = []
    for key, value in data.items():
        fields.append(f"{key} = ?")
        values.append(value)
    fields.append("updated_at = datetime('now')")
    values.append(clean)

    await db.execute(
        f"UPDATE books SET {', '.join(fields)} WHERE isbn = ?",
        values,
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM books WHERE isbn = ?", (clean,))
    return row_to_book(await cursor.fetchone())


@app.delete("/api/books/{isbn}", status_code=204)
async def delete_book(
    isbn: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    try:
        clean = normalize_isbn(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cursor = await db.execute("DELETE FROM books WHERE isbn = ?", (clean,))
    await db.commit()
    if cursor.rowcount == 0:
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
