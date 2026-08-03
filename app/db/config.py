"""Backend selection from environment.

Triggers (first match wins):

1. ``DATABASE_URL`` starts with ``sqlite`` → SQLite at that path
2. ``DATABASE_URL`` starts with ``postgres`` → PostgreSQL (Docker Compose default)
3. ``ALEJANDRISBN_BACKEND=sqlite`` → SQLite at the OS user-data path
   (Windows build / ``start-desktop.bat`` / Linux desktop-style runs)
4. any other ``DATABASE_URL`` → treated as PostgreSQL
5. nothing set → PostgreSQL localhost default (dev without Compose URL)

What does *not* choose SQLite by itself: simply running on Windows. The
desktop launcher sets ``ALEJANDRISBN_BACKEND=sqlite`` before the API starts.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote

_DEFAULT_PG = "postgresql://alejandrisbn:alejandrisbn@localhost:5432/alejandrisbn"


def default_sqlite_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / "AlejandrISBN" / "alejandrisbn.db"


def sqlite_path_from_url(url: str) -> Path:
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
    """Return ``(backend, url)`` where backend is ``'postgres'`` | ``'sqlite'``."""
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
