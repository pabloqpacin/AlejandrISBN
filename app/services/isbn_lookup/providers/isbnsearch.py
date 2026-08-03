"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

import re
from typing import Optional

import httpx

from app.services.isbn_lookup.util import (
    _BOGUS_TITLE_RE,
    _https,
    _is_bogus_title,
    _usable_hit,
    _year_from_text,
    to_isbn10,
)

def _parse_isbnsearch(html: str) -> Optional[dict]:
    """Parse isbnsearch.org book page."""
    # Bot walls often say "Please Verify to Continue" in <h1>
    if _BOGUS_TITLE_RE.search(html) and "ISBN-13" not in html:
        return None

    title = re.search(r"<h1[^>]*>\s*(.*?)\s*</h1>", html, flags=re.I | re.S)
    if not title:
        return None
    # strip tags just in case
    name = re.sub(r"<[^>]+>", "", title.group(1)).strip()
    if _is_bogus_title(name):
        return None

    def labeled(label: str) -> str:
        m = re.search(
            rf"<strong>\s*{re.escape(label)}\s*:?\s*</strong>\s*([^<]+)",
            html,
            flags=re.I,
        )
        return m.group(1).strip() if m else ""

    authors = labeled("Author") or labeled("Authors")
    # Author may be wrapped in <a>
    if not authors:
        m = re.search(
            r"<strong>\s*Author:?\s*</strong>\s*(?:<a[^>]*>)?([^<]+)",
            html,
            flags=re.I,
        )
        authors = m.group(1).strip() if m else ""

    publisher = labeled("Publisher")
    # Real book pages always expose ISBN-13 + at least author or publisher
    if "ISBN-13" not in html:
        return None
    if not authors and not publisher:
        return None

    year = _year_from_text(labeled("Published") or labeled("Publication date"))
    cover = ""
    img = re.search(
        r'<div class="image">\s*<img[^>]+src="([^"]+)"',
        html,
        flags=re.I,
    )
    if img:
        cover = img.group(1)

    return {
        "title": name,
        "authors": authors,
        "publication_year": year,
        "genre": "",
        "publisher": publisher,
        "cover_url": _https(cover),
        "description": "",
        "source": "isbnsearch",
    }


async def _isbnsearch_org(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    """Broad ISBN aggregator — fills gaps for editions missing from OL/TTL/Google/IBS."""
    plain = isbn.replace("-", "")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    }
    url = f"https://isbnsearch.org/isbn/{plain}"
    try:
        resp = await client.get(url, headers=headers, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    # Confirm page is about this ISBN (avoid soft-404 search pages)
    if plain not in resp.text and (to_isbn10(plain) or "") not in resp.text:
        return None
    parsed = _parse_isbnsearch(resp.text)
    if _usable_hit(parsed):
        return parsed
    return None
