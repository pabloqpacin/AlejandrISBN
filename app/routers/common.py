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
    return ItemOut(**data)


# Back-compat
row_to_book = row_to_item
