"""Fetch bibliographic metadata from free public catalogs."""

from __future__ import annotations

import re
from typing import Any, Optional

import httpx

TIMEOUT = httpx.Timeout(12.0, connect=5.0)
USER_AGENT = "AlejandrISBN/1.0 (library-inventory; +https://github.com/alejandrisbn)"


def _year_from_text(value: Any) -> Optional[int]:
    if value is None:
        return None
    match = re.search(r"(19|20)\d{2}", str(value))
    return int(match.group(0)) if match else None


def _join(values: list[str], sep: str = ", ") -> str:
    cleaned = [v.strip() for v in values if v and str(v).strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for item in cleaned:
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return sep.join(unique)


def _empty_result() -> dict:
    return {
        "title": "",
        "authors": "",
        "publication_year": None,
        "genre": "",
        "publisher": "",
        "cover_url": "",
        "description": "",
        "source": "",
    }


async def _open_library_books_api(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    """Single-call OL endpoint with authors + subjects inline."""
    url = "https://openlibrary.org/api/books"
    try:
        resp = await client.get(
            url,
            params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None

    payload = resp.json() or {}
    data = payload.get(f"ISBN:{isbn}")
    if not data:
        return None

    title = (data.get("title") or "").strip()
    if not title:
        return None

    authors = [a.get("name", "") for a in (data.get("authors") or []) if isinstance(a, dict)]
    subjects = [s.get("name", "") for s in (data.get("subjects") or [])[:6] if isinstance(s, dict)]
    publishers = data.get("publishers") or []
    publisher = ""
    if publishers and isinstance(publishers[0], dict):
        publisher = publishers[0].get("name") or ""
    elif publishers:
        publisher = str(publishers[0])

    cover = ""
    covers = data.get("cover") or {}
    if isinstance(covers, dict):
        cover = covers.get("large") or covers.get("medium") or covers.get("small") or ""
    if not cover:
        cover = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"

    excerpts = data.get("excerpts") or []
    description = ""
    if excerpts and isinstance(excerpts[0], dict):
        description = (excerpts[0].get("text") or "").strip()
    notes = data.get("notes")
    if not description and isinstance(notes, str):
        description = notes.strip()

    return {
        "title": title,
        "authors": _join(authors),
        "publication_year": _year_from_text(data.get("publish_date")),
        "genre": _join(subjects),
        "publisher": publisher,
        "cover_url": cover,
        "description": description,
        "source": "openlibrary",
    }


async def _open_library_search(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    try:
        resp = await client.get(
            "https://openlibrary.org/search.json",
            params={"isbn": isbn, "limit": 1},
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None

    docs = (resp.json() or {}).get("docs") or []
    if not docs:
        return None
    doc = docs[0]
    title = (doc.get("title") or "").strip()
    if not title:
        return None

    cover_i = doc.get("cover_i")
    cover = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg" if cover_i else f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"

    return {
        "title": title,
        "authors": _join([str(a) for a in (doc.get("author_name") or [])]),
        "publication_year": doc.get("first_publish_year") or _year_from_text(doc.get("publish_year")),
        "genre": _join([str(s) for s in (doc.get("subject") or [])[:10]]),
        "publisher": _join([str(p) for p in (doc.get("publisher") or [])[:1]]),
        "cover_url": cover,
        "description": "",
        "source": "openlibrary_search",
    }


async def _google_books(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    try:
        resp = await client.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{isbn}"},
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None

    items = (resp.json() or {}).get("items") or []
    if not items:
        return None

    info = items[0].get("volumeInfo") or {}
    title = (info.get("title") or "").strip()
    if not title:
        return None

    image_links = info.get("imageLinks") or {}
    cover = image_links.get("thumbnail") or image_links.get("smallThumbnail") or ""
    if cover.startswith("http://"):
        cover = "https://" + cover[len("http://") :]

    return {
        "title": title,
        "authors": _join([str(a) for a in (info.get("authors") or [])]),
        "publication_year": _year_from_text(info.get("publishedDate")),
        "genre": _join([str(c) for c in (info.get("categories") or [])]),
        "publisher": (info.get("publisher") or "").strip(),
        "cover_url": cover,
        "description": (info.get("description") or "").strip(),
        "source": "google_books",
    }


def _merge(*parts: Optional[dict]) -> dict:
    merged = _empty_result()
    sources: list[str] = []
    for part in parts:
        if not part:
            continue
        src = part.get("source")
        if src:
            sources.append(str(src))
        for key, value in part.items():
            if key == "source":
                continue
            current = merged.get(key)
            empty = current is None or current == ""
            if empty and value not in (None, ""):
                merged[key] = value
    merged["source"] = "+".join(dict.fromkeys(sources))
    return merged


async def lookup_isbn(isbn: str) -> dict:
    """Resolve ISBN metadata. Raises ValueError if nothing useful is found."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers, follow_redirects=True) as client:
        primary = await _open_library_books_api(client, isbn)
        search = None if primary and primary.get("authors") else await _open_library_search(client, isbn)
        google = await _google_books(client, isbn)

    merged = _merge(primary, search, google)
    if not merged.get("title"):
        raise ValueError(f"No bibliographic data found for ISBN {isbn}")
    if not merged.get("cover_url"):
        merged["cover_url"] = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
    return merged
