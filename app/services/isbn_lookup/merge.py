"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

import asyncio
from typing import Optional

from app.services.isbn_lookup.util import (
    _clean_text,
    _empty_result,
    _human_genre,
    _is_bogus_title,
    _mostly_cjk,
    _usable_hit,
)

def _merge(*parts: Optional[dict]) -> dict:
    merged = _empty_result()
    sources: list[str] = []
    text_keys = {"title", "authors", "genre", "publisher", "description", "cover_url"}
    for part in parts:
        if not part or _is_bogus_title(part.get("title")):
            continue
        src = part.get("source")
        if src:
            sources.append(str(src))
        for key, value in part.items():
            if key in {"source", "_detail_url"}:
                continue
            if key in text_keys and isinstance(value, str):
                value = _clean_text(value)
            if key == "genre" and value:
                value = _human_genre(value)
            if key == "title" and _is_bogus_title(value):
                continue
            current = merged.get(key)
            empty = current is None or current == ""
            if empty and value not in (None, ""):
                merged[key] = value
                continue
            # Prefer Latin-script author names over CJK-only catalog forms.
            if (
                key == "authors"
                and current
                and value
                and _mostly_cjk(str(current))
                and not _mostly_cjk(str(value))
            ):
                merged[key] = value
    merged["source"] = "+".join(dict.fromkeys(sources))
    return merged


async def _first_hit(coros) -> Optional[dict]:
    """Run coroutines concurrently; return first useful metadata dict."""
    tasks = [asyncio.create_task(coro) for coro in coros]
    try:
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
            except Exception:
                continue
            if _usable_hit(result):
                for other in tasks:
                    other.cancel()
                return result
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
    return None
