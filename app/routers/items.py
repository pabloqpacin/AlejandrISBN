"""Item CRUD, search, suggestions, and inventory stats."""

from __future__ import annotations

from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.db import SEARCH_COLUMNS, get_db, search_clause
from app.routers.common import ALLOWED_UPDATE_FIELDS, row_to_item
from app.schemas import (
    ItemCreate,
    ItemOut,
    ItemUpdate,
    MediaType,
    RoomStat,
    FurnitureStat,
    StatsOut,
    generate_item_id,
    is_print_media,
    resolve_placement,
)
from app.services.isbn_lookup import lookup_isbn

router = APIRouter(tags=["items"])

SEARCH_COLUMNS_ITEMS = [*SEARCH_COLUMNS, "media_type"]


@router.get("/api/stats", response_model=StatsOut)
async def inventory_stats(db=Depends(get_db)) -> StatsOut:
    total = int(await db.fetchval("SELECT COUNT(*) FROM items") or 0)
    type_rows = await db.fetch(
        """
        SELECT media_type AS value, COUNT(*)::int AS count
        FROM items
        GROUP BY media_type
        ORDER BY count DESC, media_type ASC
        """
    )
    by_media_type = {str(row["value"]): int(row["count"]) for row in type_rows}
    for media in MediaType:
        by_media_type.setdefault(media.value, 0)

    room_rows = await db.fetch(
        """
        SELECT
            CASE WHEN TRIM(COALESCE(room, '')) = '' THEN '(sin habitación)'
                 ELSE TRIM(room)
            END AS room,
            CASE WHEN TRIM(COALESCE(furniture, '')) = '' THEN '(sin mueble)'
                 ELSE TRIM(furniture)
            END AS furniture,
            COUNT(*)::int AS count
        FROM items
        GROUP BY 1, 2
        ORDER BY 1 ASC, count DESC, 2 ASC
        """
    )
    rooms: dict[str, RoomStat] = {}
    for row in room_rows:
        room_name = str(row["room"])
        count = int(row["count"])
        if room_name not in rooms:
            rooms[room_name] = RoomStat(value=room_name, count=0, furniture=[])
        rooms[room_name].count += count
        rooms[room_name].furniture.append(
            FurnitureStat(value=str(row["furniture"]), count=count)
        )
    by_room = sorted(rooms.values(), key=lambda item: (-item.count, item.value))

    # Legacy flat list (composed placement) for older clients.
    by_location = [
        {
            "value": room.value
            if not room.furniture
            else (
                room.value
                if len(room.furniture) == 1 and room.furniture[0].value == "(sin mueble)"
                else room.value
            ),
            "count": room.count,
        }
        for room in by_room
    ]

    return StatsOut(
        total=total,
        by_media_type=by_media_type,
        by_room=by_room,
        by_location=by_location,
    )


@router.get("/api/items", response_model=list[ItemOut])
async def list_items(
    q: Optional[list[str]] = Query(
        None,
        description="Search terms (repeat param). Match any term; OR across terms.",
    ),
    media_type: Optional[str] = Query(None, description="Filter by media type"),
    favourite: Optional[bool] = Query(None, description="Filter by favourite flag"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
) -> list[ItemOut]:
    clauses: list[str] = []
    params: list = []

    terms = [term.strip() for term in (q or []) if term and term.strip()]
    term_clauses: list[str] = []
    for term in terms:
        params.append(f"%{term}%")
        term_clauses.append(search_clause(SEARCH_COLUMNS_ITEMS, len(params)))
    if term_clauses:
        clauses.append(f"({' OR '.join(term_clauses)})")

    if media_type:
        clean_type = media_type.strip().lower()
        try:
            MediaType(clean_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid media_type: {media_type}") from exc
        params.append(clean_type)
        clauses.append(f"media_type = ${len(params)}")

    if favourite is not None:
        params.append(favourite)
        clauses.append(f"favourite = ${len(params)}")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    order = "title ASC" if terms else "created_at DESC"
    rows = await db.fetch(
        f"""
        SELECT * FROM items
        {where}
        ORDER BY {order}
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """,
        *params,
    )
    return [row_to_item(row) for row in rows]


@router.get("/api/suggestions")
async def field_suggestions(db=Depends(get_db)) -> dict:
    """Distinct authors / genre / location / collection values for form autocomplete."""

    async def values_for(column: str) -> list[dict]:
        rows = await db.fetch(
            f"""
            SELECT TRIM({column}) AS value, COUNT(*)::int AS count
            FROM items
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
            FROM items
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
        "room": await values_for("room"),
        "furniture": await values_for("furniture"),
        "location": await values_for("location"),
        "collection": await values_for("collection"),
        "translators": await label_values_for("translators"),
    }


@router.get("/api/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: str, db=Depends(get_db)) -> ItemOut:
    row = await db.fetchrow("SELECT * FROM items WHERE id = $1", item_id.strip())
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return row_to_item(row)


@router.post("/api/items", response_model=ItemOut, status_code=201)
async def create_item(payload: ItemCreate, db=Depends(get_db)) -> ItemOut:
    item_id = generate_item_id()

    # Manual entry (no ISBN lookup): any media type, or print without ISBN.
    if payload.isbn is None:
        row = await db.fetchrow(
            """
            INSERT INTO items (
                id, media_type, isbn, title, authors, publication_year, genre, publisher,
                cover_url, description, location, room, furniture, notes, legal_deposit,
                collection, volume, original_year, translators, original_title, favourite, source
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22
            )
            RETURNING *
            """,
            item_id,
            payload.media_type.value,
            None,
            (payload.title or "").strip(),
            (payload.authors or "").strip(),
            payload.publication_year,
            (payload.genre or "").strip(),
            (payload.publisher or "").strip(),
            (payload.cover_url or "").strip(),
            (payload.description or "").strip(),
            payload.location or "",
            payload.room or "",
            payload.furniture or "",
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
        return row_to_item(row)

    if not is_print_media(payload.media_type):
        raise HTTPException(status_code=400, detail="ISBN lookup only applies to books and magazines")

    existing = await db.fetchval("SELECT id FROM items WHERE isbn = $1", payload.isbn)
    if existing:
        raise HTTPException(status_code=409, detail="Item with this ISBN already in inventory")

    try:
        meta = await lookup_isbn(payload.isbn)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    overrides = payload.model_dump(
        exclude={
            "isbn",
            "media_type",
            "location",
            "room",
            "furniture",
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

    try:
        row = await db.fetchrow(
            """
            INSERT INTO items (
                id, media_type, isbn, title, authors, publication_year, genre, publisher,
                cover_url, description, location, room, furniture, notes, legal_deposit,
                collection, volume, original_year, translators, original_title, favourite, source
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22
            )
            RETURNING *
            """,
            item_id,
            payload.media_type.value,
            payload.isbn,
            meta["title"],
            meta.get("authors") or "",
            meta.get("publication_year"),
            meta.get("genre") or "",
            meta.get("publisher") or "",
            meta.get("cover_url") or "",
            meta.get("description") or "",
            payload.location or "",
            payload.room or "",
            payload.furniture or "",
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
    except Exception as exc:
        # Unique isbn race
        if "unique" in str(exc).lower() or "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail="Item with this ISBN already in inventory") from exc
        raise
    return row_to_item(row)


@router.patch("/api/items/{item_id}", response_model=ItemOut)
async def update_item(item_id: str, payload: ItemUpdate, db=Depends(get_db)) -> ItemOut:
    row = await db.fetchrow("SELECT * FROM items WHERE id = $1", item_id.strip())
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    data = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if key in ALLOWED_UPDATE_FIELDS
    }
    if "media_type" in data and isinstance(data["media_type"], MediaType):
        data["media_type"] = data["media_type"].value

    current_type = data.get("media_type") or row["media_type"]
    next_isbn = data["isbn"] if "isbn" in data else row["isbn"]
    if not is_print_media(current_type):
        if next_isbn:
            raise HTTPException(status_code=400, detail="isbn only applies to books and magazines")
        data["isbn"] = None
        if "legal_deposit" not in data:
            pass
        elif data.get("legal_deposit"):
            data["legal_deposit"] = ""

    if "room" in data or "furniture" in data:
        room, furniture, composed = resolve_placement(
            room=data["room"] if "room" in data else row["room"],
            furniture=data["furniture"] if "furniture" in data else row["furniture"],
        )
        data["room"] = room
        data["furniture"] = furniture
        data["location"] = composed
    elif "location" in data:
        room, furniture, composed = resolve_placement(location=data.get("location"))
        data["room"] = room
        data["furniture"] = furniture
        data["location"] = composed

    if not data:
        return row_to_item(row)

    if "isbn" in data and data["isbn"]:
        other = await db.fetchval(
            "SELECT id FROM items WHERE isbn = $1 AND id <> $2",
            data["isbn"],
            item_id.strip(),
        )
        if other:
            raise HTTPException(status_code=409, detail="Item with this ISBN already in inventory")

    assignments = []
    values: list = []
    for index, (key, value) in enumerate(data.items(), start=1):
        assignments.append(f"{key} = ${index}")
        values.append(value)
    values.append(item_id.strip())
    id_param = len(values)

    try:
        row = await db.fetchrow(
            f"""
            UPDATE items
            SET {', '.join(assignments)}, updated_at = NOW()
            WHERE id = ${id_param}
            RETURNING *
            """,
            *values,
        )
    except Exception as exc:
        if "unique" in str(exc).lower() or "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail="Item with this ISBN already in inventory") from exc
        raise
    return row_to_item(row)


@router.delete("/api/items/{item_id}", status_code=204, response_class=Response)
async def delete_item(item_id: str, db=Depends(get_db)) -> Response:
    result = await db.execute("DELETE FROM items WHERE id = $1", item_id.strip())
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Item not found")
    return Response(status_code=204)
