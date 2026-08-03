"""Shared types and row helpers (backend-agnostic)."""

from __future__ import annotations

from typing import Any, Protocol, Union

from app.db.postgres import PgConnection
from app.db.sqlite import SqliteConnection

DbConnection = Union[PgConnection, SqliteConnection]


class SupportsDbOps(Protocol):
    async def fetch(self, query: str, *args: Any) -> list[Any]: ...
    async def fetchrow(self, query: str, *args: Any) -> Any: ...
    async def fetchval(self, query: str, *args: Any) -> Any: ...
    async def execute(self, query: str, *args: Any) -> str: ...


SEARCH_COLUMNS = [
    "isbn",
    "title",
    "authors",
    "genre",
    "publisher",
    "location",
    "notes",
    "legal_deposit",
    "collection",
    "volume",
    "translators",
    "original_title",
    "media_type",
]


def _row_to_mapping(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return dict(row)


def record_to_dict(row: Any) -> dict[str, Any]:
    data = _row_to_mapping(row)
    for key in ("created_at", "updated_at"):
        value = data.get(key)
        if hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    if "favourite" in data:
        data["favourite"] = bool(data["favourite"])
    return data
