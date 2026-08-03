"""Process-wide DB lifecycle: pick backend, open pool, FastAPI ``get_db``."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from app.db.config import resolve_backend, sqlite_path_from_url
from app.db.postgres import PgConnection, create_pool as create_pg_pool
from app.db.postgres import search_clause as pg_search_clause
from app.db.schema import ensure_books_schema
from app.db.sqlite import SqlitePool
from app.db.sqlite import search_clause as sqlite_search_clause

BACKEND, DATABASE_URL = resolve_backend()
IS_SQLITE = BACKEND == "sqlite"
IS_POSTGRES = BACKEND == "postgres"

pool: Any = None


def wrap_connection(raw: Any) -> Any:
    """Normalize pool.acquire() output to a DbConnection-like wrapper."""
    if IS_SQLITE:
        return raw
    return PgConnection(raw)


@asynccontextmanager
async def acquire() -> AsyncIterator[Any]:
    """Yield a wrapped connection; always reads the current ``pool``."""
    if pool is None:
        raise RuntimeError("Database pool is not initialized")
    async with pool.acquire() as raw:
        yield wrap_connection(raw)


async def init_pool() -> None:
    global pool, BACKEND, DATABASE_URL, IS_SQLITE, IS_POSTGRES
    BACKEND, DATABASE_URL = resolve_backend()
    IS_SQLITE = BACKEND == "sqlite"
    IS_POSTGRES = BACKEND == "postgres"

    if IS_SQLITE:
        path = sqlite_path_from_url(DATABASE_URL)
        sqlite_pool = SqlitePool(path)
        await sqlite_pool.open()
        pool = sqlite_pool
        return

    pool = await create_pg_pool(DATABASE_URL)


async def close_pool() -> None:
    global pool
    if pool is None:
        return
    await pool.close()
    pool = None


async def get_db() -> AsyncIterator[Any]:
    async with acquire() as conn:
        yield conn


def search_clause(columns: list[str], param_idx: int) -> str:
    if IS_POSTGRES:
        return pg_search_clause(columns, param_idx)
    return sqlite_search_clause(columns, param_idx)


async def init_db() -> None:
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with acquire() as conn:
        if IS_POSTGRES:
            async with conn.transaction():
                await conn.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
                await ensure_books_schema(conn, is_sqlite=False)
        else:
            # SQLite: DDL auto-commits; avoid wrapping in an explicit transaction.
            await ensure_books_schema(conn, is_sqlite=True)
