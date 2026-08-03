"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

import re
from typing import Optional

import httpx

from app.services.isbn_lookup.util import _https, _is_bogus_title, _usable_hit, to_isbn10, to_isbn13

def _parse_abebooks(html: str, plain: str) -> Optional[dict]:
    """Parse AbeBooks / Iberlibro ISBN search results (same marketplace HTML)."""
    plain = plain.replace("-", "").upper()
    isbn10 = (to_isbn10(plain) or "").upper()
    # Empty / related-results pages still mention the query ISBN — reject them.
    if re.search(
        r"no results|we couldn.?t find|did not match any|0 results",
        html,
        flags=re.I,
    ):
        return None

    # Prefer a listing that explicitly links this ISBN (not “related” items).
    listing = None
    for m in re.finditer(
        r'data-test-id="listing-title"[^>]*>([^<]+).{0,2500}?'
        r'(?:data-csa-c-navigate-identifier="ISBN-(\d+)"|isbn[=/"\s-](\d{10,13}))',
        html,
        flags=re.I | re.S,
    ):
        title_cand = m.group(1).strip()
        listed = (m.group(2) or m.group(3) or "").replace("-", "").upper()
        if listed in {plain, isbn10} and not _is_bogus_title(title_cand):
            listing = m
            break

    title = ""
    authors = ""
    publisher = ""
    year: Optional[int] = None
    cover = ""

    if listing:
        title = listing.group(1).strip()
        chunk_start = max(0, listing.start() - 500)
        chunk = html[chunk_start : listing.end() + 1200]
        am = re.search(
            r'data-test-id="listing-author".{0,400}?<a[^>]*>([^<]+)',
            chunk,
            flags=re.I | re.S,
        )
        if am:
            authors = am.group(1).strip()
        pm = re.search(
            r'data-test-id="publisher-\d+"[^>]*>\s*Published by\s*([^<]+)',
            chunk,
            flags=re.I,
        )
        if pm:
            pub_line = pm.group(1).strip()
            ym = re.search(r",\s*((?:19|20)\d{2})\s*$", pub_line)
            if ym:
                year = int(ym.group(1))
                publisher = pub_line[: ym.start()].strip(" .,")
            else:
                publisher = pub_line.strip(" .,")
        cm = re.search(
            rf'src="(https://pictures\.abebooks\.com/isbn/{re.escape(plain)}[^"]*)"',
            chunk,
            flags=re.I,
        )
        if not cm and isbn10:
            cm = re.search(
                rf'src="(https://pictures\.abebooks\.com/isbn/{re.escape(isbn10)}[^"]*)"',
                chunk,
                flags=re.I,
            )
        if cm:
            cover = cm.group(1)
    else:
        # Title-tag fallback only when it names the book (not bare ISBN pages).
        m = re.search(
            r"<title>\s*\d[\d-]{8,16}\s*-\s*(.+?)\s+by\s+(.+?)\s*[–-]\s*(?:AbeBooks|Iberlibro)",
            html,
            flags=re.I,
        )
        if not m:
            return None
        title = m.group(1).strip().rstrip(".")
        authors = m.group(2).strip()
        if _is_bogus_title(title):
            return None
        # Require a cover or ISBN link for this exact ISBN so related hits don't slip in.
        if plain not in html and isbn10 not in html:
            return None
        cm = re.search(
            rf'src="(https://pictures\.abebooks\.com/isbn/{re.escape(plain)}[^"]*)"',
            html,
            flags=re.I,
        )
        if cm:
            cover = cm.group(1)

    if _is_bogus_title(title):
        return None

    return {
        "title": title,
        "authors": authors,
        "publication_year": year,
        "genre": "",
        "publisher": publisher,
        "cover_url": _https(cover),
        "description": "",
        "source": "abebooks",
    }


async def _abebooks(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    """Marketplace catalog — good for OOP / club editions missing from retail APIs."""
    plain = (to_isbn13(isbn.replace("-", "")) or isbn.replace("-", "")).upper()
    if not plain.isdigit():
        plain = isbn.replace("-", "").upper()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    urls = [
        f"https://www.abebooks.com/servlet/SearchResults?isbn={plain}",
        f"https://www.iberlibro.com/servlet/SearchResults?isbn={plain}",
    ]
    isbn10 = to_isbn10(plain)
    if isbn10 and isbn10 != plain:
        urls.append(f"https://www.abebooks.com/servlet/SearchResults?isbn={isbn10}")

    for url in urls:
        try:
            resp = await client.get(url, headers=headers, follow_redirects=True)
        except httpx.HTTPError:
            continue
        if resp.status_code != 200:
            continue
        parsed = _parse_abebooks(resp.text, plain)
        if _usable_hit(parsed):
            return parsed
    return None
