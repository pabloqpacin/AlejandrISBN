"""Database layer: PostgreSQL (Docker/self-host) or SQLite (desktop / low-spec).

Resolution order:
1. ``DATABASE_URL`` starting with ``sqlite`` → SQLite
2. ``DATABASE_URL`` starting with ``postgres`` → PostgreSQL
3. ``ALEJANDRISBN_BACKEND=sqlite`` → SQLite at default user data path
4. else → PostgreSQL (Docker-compatible default)
"""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Union
from urllib.parse import unquote

# --- config ------------------------------------------------------------------

_DEFAULT_PG = "postgresql://alejandrisbn:alejandrisbn@localhost:5432/alejandrisbn"


def default_sqlite_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / "AlejandrISBN" / "alejandrisbn.db"


def _sqlite_path_from_url(url: str) -> Path:
    if url.startswith("sqlite:///"):
        raw = url[len("sqlite:///") :]
    elif url.startswith("sqlite://"):
        raw = url[len("sqlite://") :]
    else:
        raw = url
    raw = unquote(raw)
    if raw == ":memory:":
        return Path(":memory:")
    path = Path(raw)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def resolve_backend() -> tuple[str, str]:
    """Return (backend, url_or_path) where backend is 'postgres' | 'sqlite'."""
    url = (os.getenv("DATABASE_URL") or "").strip()
    backend_env = (os.getenv("ALEJANDRISBN_BACKEND") or "").strip().lower()

    if url.lower().startswith("sqlite"):
        return "sqlite", url
    if url.lower().startswith("postgres"):
        return "postgres", url
    if backend_env in {"sqlite", "sqlite3"}:
        path = default_sqlite_path()
        return "sqlite", f"sqlite:///{path.as_posix()}"
    if url:
        return "postgres", url
    return "postgres", _DEFAULT_PG


BACKEND, DATABASE_URL = resolve_backend()
IS_SQLITE = BACKEND == "sqlite"
IS_POSTGRES = BACKEND == "postgres"

pool: Any = None


# --- SQL helpers -------------------------------------------------------------

_PARAM_RE = re.compile(r"\$(\d+)")


def _adapt_sql_sqlite(sql: str) -> str:
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


def _bind_sqlite(sql: str, args: tuple[Any, ...]) -> tuple[str, tuple[Any, ...]]:
    sql = _adapt_sql_sqlite(sql)
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


# --- connection wrappers -----------------------------------------------------


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


class SqliteConnection:
    """Assumes caller serializes access (pool.acquire holds the lock)."""

    def __init__(self, conn: Any, *, autocommit: bool = True) -> None:
        self._conn = conn
        self._autocommit = autocommit

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        sql, params = _bind_sqlite(query, args)
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        description = cursor.description or []
        keys = [col[0] for col in description]
        return [dict(zip(keys, row)) for row in rows]

    async def fetchrow(self, query: str, *args: Any) -> Any:
        rows = await self.fetch(query, *args)
        return rows[0] if rows else None

    async def fetchval(self, query: str, *args: Any) -> Any:
        row = await self.fetchrow(query, *args)
        if row is None:
            return None
        return next(iter(row.values()))

    async def execute(self, query: str, *args: Any) -> str:
        sql, params = _bind_sqlite(query, args)
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
        # isolation_level=None (set on connect) → manual BEGIN/commit/rollback
        await self._conn.execute("BEGIN")
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


DbConnection = Union[PgConnection, SqliteConnection]


class _SqlitePool:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: Any = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        import aiosqlite

        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.path))
        self._conn.row_factory = aiosqlite.Row
        # Manual transactions only (avoids "cannot commit/rollback — no transaction")
        self._conn.isolation_level = None
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[SqliteConnection]:
        if self._conn is None:
            raise RuntimeError("SQLite pool is not initialized")
        async with self._lock:
            yield SqliteConnection(self._conn, autocommit=True)


# --- lifecycle ---------------------------------------------------------------


async def init_pool() -> None:
    global pool, BACKEND, DATABASE_URL, IS_SQLITE, IS_POSTGRES
    BACKEND, DATABASE_URL = resolve_backend()
    IS_SQLITE = BACKEND == "sqlite"
    IS_POSTGRES = BACKEND == "postgres"

    if IS_SQLITE:
        path = _sqlite_path_from_url(DATABASE_URL)
        sqlite_pool = _SqlitePool(path)
        await sqlite_pool.open()
        pool = sqlite_pool
        return

    import asyncpg

    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )


async def close_pool() -> None:
    global pool
    if pool is None:
        return
    await pool.close()
    pool = None


async def get_db() -> AsyncIterator[DbConnection]:
    if pool is None:
        raise RuntimeError("Database pool is not initialized")
    if IS_SQLITE:
        async with pool.acquire() as conn:
            yield conn
        return

    async with pool.acquire() as raw:
        yield PgConnection(raw)


def search_clause(columns: list[str], param_idx: int) -> str:
    if IS_POSTGRES:
        parts = [f"unaccent({col}) ILIKE unaccent(${param_idx})" for col in columns]
    else:
        parts = [f"LOWER(COALESCE({col}, '')) LIKE LOWER(${param_idx})" for col in columns]
    return "(" + " OR ".join(parts) + ")"


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
]


async def init_db() -> None:
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as raw:
        conn: DbConnection = raw if IS_SQLITE else PgConnection(raw)

        if IS_POSTGRES:
            async with conn.transaction():
                await conn.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
                await _ensure_books_schema(conn)
        else:
            # SQLite: DDL auto-commits; avoid wrapping in an explicit transaction.
            await _ensure_books_schema(conn)

    from app.seed import apply_seeds

    await apply_seeds()


async def _ensure_books_schema(conn: DbConnection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            isbn             TEXT PRIMARY KEY,
            title            TEXT NOT NULL,
            authors          TEXT NOT NULL DEFAULT '',
            publication_year INTEGER,
            genre            TEXT NOT NULL DEFAULT '',
            publisher        TEXT NOT NULL DEFAULT '',
            cover_url        TEXT NOT NULL DEFAULT '',
            description      TEXT NOT NULL DEFAULT '',
            location         TEXT NOT NULL DEFAULT '',
            notes            TEXT NOT NULL DEFAULT '',
            source           TEXT NOT NULL DEFAULT '',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    alter_columns = (
        ("location", "TEXT NOT NULL DEFAULT ''"),
        ("favourite", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("legal_deposit", "TEXT NOT NULL DEFAULT ''"),
        ("collection", "TEXT NOT NULL DEFAULT ''"),
        ("volume", "TEXT NOT NULL DEFAULT ''"),
        ("original_year", "INTEGER"),
        ("translators", "TEXT NOT NULL DEFAULT ''"),
        ("original_title", "TEXT NOT NULL DEFAULT ''"),
    )
    for name, typedef in alter_columns:
        await _add_column_if_missing(conn, "books", name, typedef)

    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_books_title ON books (lower(title))",
        "CREATE INDEX IF NOT EXISTS idx_books_authors ON books (lower(authors))",
        "CREATE INDEX IF NOT EXISTS idx_books_isbn ON books (isbn)",
        "CREATE INDEX IF NOT EXISTS idx_books_location ON books (lower(location))",
        "CREATE INDEX IF NOT EXISTS idx_books_favourite ON books (favourite)",
        "CREATE INDEX IF NOT EXISTS idx_books_legal_deposit ON books (lower(legal_deposit))",
        "CREATE INDEX IF NOT EXISTS idx_books_collection ON books (lower(collection))",
        "CREATE INDEX IF NOT EXISTS idx_books_volume ON books (lower(volume))",
    ):
        await conn.execute(stmt)


async def _add_column_if_missing(
    conn: DbConnection, table: str, column: str, typedef: str
) -> None:
    if IS_SQLITE:
        rows = await conn.fetch(f"PRAGMA table_info({table})")
        existing = {row["name"] for row in rows}
        if column in existing:
            return
        await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")
        return

    await conn.execute(
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {typedef}"
    )