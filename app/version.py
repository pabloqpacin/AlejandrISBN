"""App version for desktop updates and /api/health.

Docker / Linux git workflows are unaffected: default is ``0.0.0-dev``.
Windows CI writes a ``VERSION`` file into the PyInstaller bundle from the git tag.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_VERSION = "0.0.0-dev"
DEFAULT_GITHUB_REPO = "pabloqpacin/AlejandrISBN"


def _candidates() -> list[Path]:
    paths: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        paths.append(Path(sys._MEIPASS) / "VERSION")
    here = Path(__file__).resolve().parent
    paths.append(here.parent / "VERSION")
    if getattr(sys, "frozen", False):
        paths.append(Path(sys.executable).resolve().parent / "VERSION")
    return paths


def get_version() -> str:
    env = (os.getenv("ALEJANDRISBN_VERSION") or "").strip()
    if env:
        return env
    for path in _candidates():
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return DEFAULT_VERSION


def get_github_repo() -> str:
    return (os.getenv("ALEJANDRISBN_GITHUB_REPO") or DEFAULT_GITHUB_REPO).strip()


def normalize_version(value: str) -> str:
    return (value or "").strip().lstrip("vV")


def version_tuple(value: str) -> tuple[int, ...]:
    """Best-effort numeric tuple for comparison (ignores +build / -prerelease suffix)."""
    core = normalize_version(value).split("+", 1)[0].split("-", 1)[0]
    parts: list[int] = []
    for piece in core.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    return version_tuple(remote) > version_tuple(local)
