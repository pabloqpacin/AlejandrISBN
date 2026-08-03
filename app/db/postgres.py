"""PostgreSQL backend (Docker Compose / self-host)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


class PgConnection:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        return await self._conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Any:
        return await self._conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        return await self._conn.fetchval(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        return await self._conn.execute(query, *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["PgConnection"]:
        async with self._conn.transaction():
            yield self


def search_clause(columns: list[str], param_idx: int) -> str:
    parts = [f"unaccent({col}) ILIKE unaccent(${param_idx})" for col in columns]
    return "(" + " OR ".join(parts) + ")"


async def create_pool(database_url: str) -> Any:
    import asyncpg

    return await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )


async def add_column_if_missing(
    conn: PgConnection, table: str, column: str, typedef: str
) -> None:
    await conn.execute(
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {typedef}"
    )
