"""SQLite backend (Windows desktop build / ALEJANDRISBN_BACKEND=sqlite)."""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

_PARAM_RE = re.compile(r"\$(\d+)")


def adapt_sql(sql: str) -> str:
    adapted = sql
    adapted = re.sub(r"\bNOW\s*\(\s*\)", "(datetime('now'))", adapted, flags=re.IGNORECASE)
    adapted = re.sub(r"\bTIMESTAMPTZ\b", "TEXT", adapted, flags=re.IGNORECASE)
    adapted = re.sub(r"\bBOOLEAN\b", "INTEGER", adapted, flags=re.IGNORECASE)
    adapted = re.sub(r"\bFALSE\b", "0", adapted, flags=re.IGNORECASE)
    adapted = re.sub(r"\bTRUE\b", "1", adapted, flags=re.IGNORECASE)
    adapted = re.sub(
        r"COUNT\s*\(\s*\*\s*\)\s*::\s*int",
        "CAST(COUNT(*) AS INTEGER)",
        adapted,
        flags=re.IGNORECASE,
    )
    adapted = re.sub(r"::\s*int\b", "", adapted, flags=re.IGNORECASE)
    return adapted


def bind_sql(sql: str, args: tuple[Any, ...]) -> tuple[str, tuple[Any, ...]]:
    sql = adapt_sql(sql)
    bound: list[Any] = []

    def repl(match: re.Match[str]) -> str:
        idx = int(match.group(1)) - 1
        if idx < 0 or idx >= len(args):
            raise IndexError(f"SQL placeholder ${idx + 1} out of range ({len(args)} args)")
        value = args[idx]
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif isinstance(value, bool):
            value = int(value)
        bound.append(value)
        return "?"

    return _PARAM_RE.sub(repl, sql), tuple(bound)


class SqliteConnection:
    """Wrapper around a short-lived aiosqlite connection (one per acquire)."""

    def __init__(self, conn: Any, *, autocommit: bool = True) -> None:
        self._conn = conn
        self._autocommit = autocommit

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        sql, params = bind_sql(query, args)
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        description = cursor.description or []
        keys = [col[0] for col in description]
        result = [dict(zip(keys, row)) for row in rows]
        # INSERT/UPDATE … RETURNING go through fetch; commit or they vanish on close.
        if self._autocommit:
            await self._conn.commit()
        return result

    async def fetchrow(self, query: str, *args: Any) -> Any:
        rows = await self.fetch(query, *args)
        return rows[0] if rows else None

    async def fetchval(self, query: str, *args: Any) -> Any:
        row = await self.fetchrow(query, *args)
        if row is None:
            return None
        return next(iter(row.values()))

    async def execute(self, query: str, *args: Any) -> str:
        sql, params = bind_sql(query, args)
        cursor = await self._conn.execute(sql, params)
        if self._autocommit:
            await self._conn.commit()
        rowcount = cursor.rowcount if cursor.rowcount is not None else 0
        upper = sql.lstrip().upper()
        if upper.startswith("DELETE"):
            return f"DELETE {rowcount}"
        if upper.startswith("INSERT"):
            return f"INSERT 0 {max(rowcount, 0)}"
        if upper.startswith("UPDATE"):
            return f"UPDATE {rowcount}"
        return f"OK {rowcount}"

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["SqliteConnection"]:
        txn = SqliteConnection(self._conn, autocommit=False)
        try:
            yield txn
            await self._conn.commit()
        except Exception:
            try:
                await self._conn.rollback()
            except Exception:
                pass
            raise


class SqlitePool:
    """
    Opens a **new** aiosqlite connection per acquire (serialized with a lock).
    Avoids sharing one sqlite3 connection across Uvicorn/thread boundaries.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._ready = False

    async def open(self) -> None:
        import aiosqlite

        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)

        conn = await aiosqlite.connect(str(self.path), check_same_thread=False)
        try:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.commit()
        finally:
            await conn.close()
        self._ready = True

    async def close(self) -> None:
        self._ready = False

    async def _connect(self) -> Any:
        import aiosqlite

        conn = await aiosqlite.connect(str(self.path), check_same_thread=False)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[SqliteConnection]:
        if not self._ready:
            raise RuntimeError("SQLite pool is not initialized")
        async with self._lock:
            conn = await self._connect()
            try:
                yield SqliteConnection(conn, autocommit=True)
            finally:
                await conn.close()


def search_clause(columns: list[str], param_idx: int) -> str:
    parts = [f"LOWER(COALESCE({col}, '')) LIKE LOWER(${param_idx})" for col in columns]
    return "(" + " OR ".join(parts) + ")"


async def add_column_if_missing(
    conn: SqliteConnection, table: str, column: str, typedef: str
) -> None:
    rows = await conn.fetch(f"PRAGMA table_info({table})")
    existing = {row["name"] for row in rows}
    if column in existing:
        return
    await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")
