"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

from typing import Optional

import httpx

from app.services.isbn_lookup.util import _https, _join, _year_from_text

async def _open_library_books_api(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    try:
        resp = await client.get(
            "https://openlibrary.org/api/books",
            params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None

    data = (resp.json() or {}).get(f"ISBN:{isbn}")
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

    covers = data.get("cover") or {}
    cover = ""
    if isinstance(covers, dict):
        cover = covers.get("large") or covers.get("medium") or covers.get("small") or ""
    if not cover:
        cover = f"https://covers.openlibrary.org/b/isbn/{isbn.replace('-', '')}-L.jpg"

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
        "cover_url": _https(cover),
        "description": description,
        "source": "openlibrary",
    }


async def _open_library_search(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    plain = isbn.replace("-", "")
    try:
        resp = await client.get(
            "https://openlibrary.org/search.json",
            params={"isbn": plain, "limit": 1},
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None

    docs = (resp.json() or {}).get("docs") or []
    if not docs:
        # Fall back to free-text ISBN query
        try:
            resp = await client.get(
                "https://openlibrary.org/search.json",
                params={"q": plain, "limit": 3},
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        docs = (resp.json() or {}).get("docs") or []
        docs = [
            doc
            for doc in docs
            if plain in {str(x).replace("-", "").upper() for x in (doc.get("isbn") or [])}
        ]

    if not docs:
        return None

    doc = docs[0]
    title = (doc.get("title") or "").strip()
    if not title:
        return None

    cover_i = doc.get("cover_i")
    cover = (
        f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg"
        if cover_i
        else f"https://covers.openlibrary.org/b/isbn/{plain}-L.jpg"
    )

    return {
        "title": title,
        "authors": _join([str(a) for a in (doc.get("author_name") or [])]),
        "publication_year": doc.get("first_publish_year") or _year_from_text(doc.get("publish_year")),
        "genre": _join([str(s) for s in (doc.get("subject") or [])[:6]]),
        "publisher": _join([str(p) for p in (doc.get("publisher") or [])[:1]]),
        "cover_url": cover,
        "description": "",
        "source": "openlibrary_search",
    }
