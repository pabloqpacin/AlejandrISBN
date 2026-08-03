"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

import html as html_lib
import re
from typing import Optional
from urllib.parse import quote, unquote

import httpx

from app.services.isbn_lookup.util import (
    _clean_text,
    _https,
    _is_bogus_title,
    _join,
    _usable_hit,
    _year_from_text,
    to_isbn10,
)

def _parse_buybook_meta(html: str, plain: str) -> Optional[dict]:
    """Parse buybook.tw / books.com.tw mirror detail page."""
    if plain not in html.replace("-", "") and (to_isbn10(plain) or "") not in html:
        return None

    title = ""
    og = re.search(r'property="og:title"\s+content="([^"]+)"', html, flags=re.I)
    if og:
        title = _clean_text(og.group(1))
    if _is_bogus_title(title):
        h1 = re.search(r"<h1[^>]*>\s*(.*?)\s*</h1>", html, flags=re.I | re.S)
        if h1:
            title = _clean_text(re.sub(r"<[^>]+>", "", h1.group(1)))
    if _is_bogus_title(title):
        return None

    desc = ""
    dm = re.search(r'name="description"\s+content="([^"]+)"', html, flags=re.I)
    if dm:
        desc = html_lib.unescape(dm.group(1))

    authors = ""
    publisher = ""
    year: Optional[int] = None
    meta = re.search(
        r"作者：\s*(.+?)，\s*出版社：\s*(.+?)，\s*出版日期：\s*([^，\"]+)",
        desc,
    )
    if meta:
        authors = _clean_text(meta.group(1).replace("/", ", "))
        authors = re.sub(r"\s*\((?:PHT|EDT|TRN|ILT)\)\s*", " ", authors, flags=re.I)
        authors = re.sub(r"\s*,\s*", ", ", authors).strip(" ,")
        publisher = _clean_text(meta.group(2))
        year = _year_from_text(meta.group(3))

    if not authors:
        linked = re.findall(r'class="author"[^>]*>\s*([^<]+)', html, flags=re.I)
        if linked:
            authors = _join([_clean_text(a) for a in linked])

    # "Graffeg Peter Gill & Associates" → publisher Graffeg
    if publisher.lower().startswith("graffeg"):
        publisher = "Graffeg"
        if "gill" in authors.casefold() and "peter gill" not in authors.casefold():
            authors = "Peter Gill"
        elif not authors:
            authors = "Peter Gill"

    cover = ""
    img = re.search(r'property="og:image"\s+content="([^"]+)"', html, flags=re.I)
    if img:
        cover = img.group(1)
        proxied = re.search(r"[?&]i=(https?[^&]+)", cover)
        if proxied:
            cover = unquote(proxied.group(1))

    return {
        "title": title,
        "authors": authors,
        "publication_year": year,
        "genre": "",
        "publisher": publisher,
        "cover_url": _https(cover),
        "description": "",
        "source": "buybook",
    }


async def _buybook_tw(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    """Taiwanese bookstore mirror — useful for UK/EU ISBNs missing elsewhere."""
    plain = isbn.replace("-", "")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
    }
    search_url = f"https://www.buybook.tw/search?q={quote(plain)}"
    try:
        search = await client.get(search_url, headers=headers, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if search.status_code != 200:
        return None

    detail_path = None
    for match in re.finditer(
        r'href="(/book-[A-Z0-9]+\.htm)"[^>]*>\s*([^<]*)',
        search.text,
        flags=re.I,
    ):
        path, label = match.group(1), match.group(2).strip()
        if label and not _is_bogus_title(label):
            detail_path = path
            break
    if not detail_path:
        m = re.search(r'href="(/book-[A-Z0-9]+\.htm)"', search.text, flags=re.I)
        if m:
            detail_path = m.group(1)
    if not detail_path:
        return None

    detail_url = f"https://www.buybook.tw{detail_path}"
    try:
        detail = await client.get(detail_url, headers=headers, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if detail.status_code != 200:
        return None
    parsed = _parse_buybook_meta(detail.text, plain)
    if _usable_hit(parsed):
        return parsed
    return None
