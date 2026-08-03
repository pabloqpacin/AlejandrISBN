"""Filesystem roots for static assets (dev + PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    """Repo root in dev; PyInstaller extract dir when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


STATIC_DIR = resource_root() / "static"
