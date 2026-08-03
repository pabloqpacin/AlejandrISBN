"""Database backends for AlejandrISBN.

Two implementations (selected in ``init_pool`` via ``app.db.config``):

* **postgres** — Docker Compose / self-host (``DATABASE_URL=postgresql://…``)
* **sqlite** — Windows desktop build, or ``ALEJANDRISBN_BACKEND=sqlite``

Public API lives here; dialect code is in ``postgres.py`` / ``sqlite.py``.
"""

from __future__ import annotations

from typing import Any

from app.db.common import SEARCH_COLUMNS, DbConnection, record_to_dict
from app.db.config import default_sqlite_path, resolve_backend
from app.db.postgres import PgConnection
from app.db.runtime import (
    acquire,
    close_pool,
    get_db,
    init_db,
    init_pool,
    search_clause,
    wrap_connection,
)
from app.db.sqlite import SqliteConnection

__all__ = [
    "BACKEND",
    "DATABASE_URL",
    "IS_POSTGRES",
    "IS_SQLITE",
    "SEARCH_COLUMNS",
    "DbConnection",
    "PgConnection",
    "SqliteConnection",
    "acquire",
    "close_pool",
    "default_sqlite_path",
    "get_db",
    "init_db",
    "init_pool",
    "pool",
    "record_to_dict",
    "resolve_backend",
    "search_clause",
    "wrap_connection",
]


def __getattr__(name: str) -> Any:
    """Live bindings for process state mutated by ``init_pool``."""
    if name in {"BACKEND", "DATABASE_URL", "IS_POSTGRES", "IS_SQLITE", "pool"}:
        from app.db import runtime as rt

        return getattr(rt, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
