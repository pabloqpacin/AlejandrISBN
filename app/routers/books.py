"""Book CRUD, search, and field suggestions."""

from __future__ import annotations

from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.db import SEARCH_COLUMNS, get_db, search_clause
from app.routers.common import ALLOWED_UPDATE_FIELDS, row_to_book
from app.schemas import (
    BookCreate,
    BookOut,
    BookUpdate,
    generate_local_id,
    is_local_id,
    normalize_book_key,
)
from app.services.isbn_lookup import lookup_isbn

router = APIRouter(tags=["books"])


@router.get("/api/books", response_model=list[BookOut])
async def list_books(
    q: Optional[list[str]] = Query(
        None,
        description="Search terms (repeat param). Match any term; OR across terms.",
    ),
    favourite: Optional[bool] = Query(None, description="Filter by favourite flag"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
) -> list[BookOut]:
    clauses: list[str] = []
    params: list = []

    terms = [term.strip() for term in (q or []) if term and term.strip()]
    term_clauses: list[str] = []
    for term in terms:
        params.append(f"%{term}%")
        term_clauses.append(search_clause(SEARCH_COLUMNS, len(params)))
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


@router.get("/api/suggestions")
async def field_suggestions(db=Depends(get_db)) -> dict:
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
            SELECT {column} AS raw
            FROM books
            WHERE TRIM(COALESCE({column}, '')) <> ''
            """
        )
        counts: Counter[str] = Counter()
        for row in rows:
            for part in str(row["raw"] or "").split(";"):
                label = part.strip()
                if label:
                    counts[label] += 1
        return [
            {"value": value, "count": count}
            for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    return {
        "authors": await label_values_for("authors"),
        "genre": await label_values_for("genre"),
        "location": await values_for("location"),
        "collection": await values_for("collection"),
        "translators": await label_values_for("translators"),
    }


@router.get("/api/books/{isbn}", response_model=BookOut)
async def get_book(isbn: str, db=Depends(get_db)) -> BookOut:
    try:
        clean = normalize_book_key(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = await db.fetchrow("SELECT * FROM books WHERE isbn = $1", clean)
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")
    return row_to_book(row)


@router.post("/api/books", response_model=BookOut, status_code=201)
async def create_book(payload: BookCreate, db=Depends(get_db)) -> BookOut:
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
                cover_url, description, location, notes, legal_deposit, collection, volume,
                original_year, translators, original_title, favourite, source
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
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
            payload.volume or "",
            payload.original_year,
            payload.translators or "",
            payload.original_title or "",
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
        exclude={
            "isbn",
            "location",
            "notes",
            "legal_deposit",
            "collection",
            "volume",
            "original_year",
            "translators",
            "original_title",
            "favourite",
        },
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
            cover_url, description, location, notes, legal_deposit, collection, volume,
            original_year, translators, original_title, favourite, source
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
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
        payload.volume or "",
        payload.original_year,
        payload.translators or "",
        payload.original_title or "",
        payload.favourite,
        meta.get("source") or "",
    )
    return row_to_book(row)


@router.patch("/api/books/{isbn}", response_model=BookOut)
async def update_book(isbn: str, payload: BookUpdate, db=Depends(get_db)) -> BookOut:
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


@router.delete("/api/books/{isbn}", status_code=204, response_class=Response)
async def delete_book(isbn: str, db=Depends(get_db)) -> Response:
    try:
        clean = normalize_book_key(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = await db.execute("DELETE FROM books WHERE isbn = $1", clean)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Book not found")
    return Response(status_code=204)
