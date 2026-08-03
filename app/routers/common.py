"""Shared helpers for HTTP routers."""

from __future__ import annotations

from typing import Any

from app.db import record_to_dict
from app.schemas import BookOut

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
    "volume",
    "original_year",
    "translators",
    "original_title",
    "favourite",
}


def row_to_book(row: Any) -> BookOut:
    return BookOut(**record_to_dict(row))
