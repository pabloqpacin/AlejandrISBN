"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

import json
import re
from typing import Optional

import httpx

from app.services.isbn_lookup.util import (
    _author_names,
    _https,
    _is_bogus_title,
    _join,
    _usable_hit,
    _year_from_text,
    to_isbn10,
)

def _parse_goodreads_ldjson(html: str, plain: str) -> Optional[dict]:
    """Parse Goodreads book page JSON-LD (schema.org Book)."""
    plain = plain.replace("-", "")
    for block in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    ):
        raw = block.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if str(node.get("@type", "")).lower() != "book":
                continue
            isbn = str(node.get("isbn") or "").replace("-", "")
            if isbn and isbn != plain and isbn != (to_isbn10(plain) or ""):
                continue
            # Some pages omit isbn in ld+json; require ISBN somewhere on page.
            if not isbn and plain not in html.replace("-", ""):
                continue
            title = (node.get("name") or "").strip()
            if _is_bogus_title(title):
                continue
            authors = _join(_author_names(node.get("author")))
            # Drop imprint-as-author noise when a real author is present
            if ", " in authors:
                parts = [p for p in authors.split(", ") if not re.search(
                    r"\b(press|publishing|publisher|editions?)\b", p, flags=re.I
                )]
                if parts:
                    authors = _join(parts)
            cover = ""
            image = node.get("image")
            if isinstance(image, list) and image:
                cover = str(image[0])
            elif isinstance(image, str):
                cover = image
            publisher = ""
            pub_m = re.search(r'"publisher"\s*:\s*"([^"]+)"', html)
            if pub_m:
                publisher = pub_m.group(1).strip()
            year = _year_from_text(node.get("datePublished"))
            if year is None:
                # Goodreads often has "Published ... Month D, YYYY" in body text.
                ym = re.search(
                    r'itemprop="publicationInfo"[^>]*>.*?((?:19|20)\d{2})',
                    html,
                    flags=re.I | re.S,
                )
                if ym:
                    year = int(ym.group(1))
            return {
                "title": title,
                "authors": authors,
                "publication_year": year,
                "genre": "",
                "publisher": publisher,
                "cover_url": _https(cover),
                "description": "",
                "source": "goodreads",
            }
    return None


async def _goodreads(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    """Goodreads ISBN landing page — solid for Amazon/KDP 979 editions."""
    plain = isbn.replace("-", "")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    }
    url = f"https://www.goodreads.com/book/isbn/{plain}"
    try:
        resp = await client.get(url, headers=headers, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    # Search/empty pages are not usable
    if "/book/show/" not in str(resp.url) and plain not in resp.text:
        return None
    parsed = _parse_goodreads_ldjson(resp.text, plain)
    if _usable_hit(parsed):
        return parsed
    # og:title fallback when ld+json missing but ISBN is confirmed on page
    if plain in resp.text.replace("-", ""):
        og = re.search(r'property="og:title" content="([^"]+)"', resp.text, flags=re.I)
        if og and not _is_bogus_title(og.group(1)):
            img = re.search(r'property="og:image" content="([^"]+)"', resp.text, flags=re.I)
            return {
                "title": og.group(1).strip(),
                "authors": "",
                "publication_year": None,
                "genre": "",
                "publisher": "",
                "cover_url": _https(img.group(1)) if img else "",
                "description": "",
                "source": "goodreads",
            }
    return None
