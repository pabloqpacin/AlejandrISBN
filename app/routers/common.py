"""Shared helpers for HTTP routers."""

from __future__ import annotations

from typing import Any

from app.db import record_to_dict
from app.schemas import ItemOut, MediaType

ALLOWED_UPDATE_FIELDS = {
    "media_type",
    "isbn",
    "title",
    "authors",
    "publication_year",
    "genre",
    "publisher",
    "cover_url",
    "description",
    "room",
    "furniture",
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


def row_to_item(row: Any) -> ItemOut:
    data = record_to_dict(row)
    isbn = data.get("isbn")
    if isbn is not None:
        isbn = str(isbn).strip() or None
    data["isbn"] = isbn
    media = data.get("media_type") or "book"
    if isinstance(media, MediaType):
        data["media_type"] = media.value
    else:
        data["media_type"] = str(media)

    from app.schemas import format_placement

    room = str(data.get("room") or "").strip()
    furniture = str(data.get("furniture") or "").strip()
    legacy = str(data.get("location") or "").strip()
    data["room"] = room
    data["furniture"] = furniture
    data["location"] = format_placement(room, furniture, legacy)
    return ItemOut(**data)


# Back-compat
row_to_book = row_to_item
