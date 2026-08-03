"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

from typing import Optional

import httpx

from app.services.isbn_lookup.util import (
    GOOGLE_BOOKS_API_KEY,
    _https,
    _join,
    _year_from_text,
    to_isbn10,
    to_isbn13,
)

async def _google_books(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    plain = isbn.replace("-", "")
    params: dict[str, str] = {"q": f"isbn:{plain}"}
    if GOOGLE_BOOKS_API_KEY:
        params["key"] = GOOGLE_BOOKS_API_KEY

    try:
        resp = await client.get("https://www.googleapis.com/books/v1/volumes", params=params)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None

    items = (resp.json() or {}).get("items") or []
    if not items:
        # Broader query sometimes finds older Spanish ISBNs
        params["q"] = plain
        try:
            resp = await client.get("https://www.googleapis.com/books/v1/volumes", params=params)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        items = (resp.json() or {}).get("items") or []

    if not items:
        return None

    chosen = None
    for item in items:
        info = item.get("volumeInfo") or {}
        identifiers = {
            str(i.get("identifier", "")).replace("-", "").upper()
            for i in (info.get("industryIdentifiers") or [])
        }
        if plain.upper() in identifiers or any(
            plain.upper() == to_isbn13(i) or plain.upper() == to_isbn10(i)
            for i in identifiers
            if i
        ):
            chosen = info
            break
    info = chosen or (items[0].get("volumeInfo") or {})

    title = (info.get("title") or "").strip()
    if not title:
        return None

    image_links = info.get("imageLinks") or {}
    cover = image_links.get("thumbnail") or image_links.get("smallThumbnail") or ""

    return {
        "title": title,
        "authors": _join([str(a) for a in (info.get("authors") or [])]),
        "publication_year": _year_from_text(info.get("publishedDate")),
        "genre": _join([str(c) for c in (info.get("categories") or [])]),
        "publisher": (info.get("publisher") or "").strip(),
        "cover_url": _https(cover),
        "description": (info.get("description") or "").strip(),
        "source": "google_books",
    }
