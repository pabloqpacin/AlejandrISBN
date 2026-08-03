"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

import html as html_lib
import re
from typing import Optional
from urllib.parse import quote

import httpx

from app.services.isbn_lookup.util import (
    _clean_text,
    _https,
    _isbn_equal,
    _is_bogus_title,
    _join,
    _usable_hit,
    _year_from_text,
)

def _clean_oszk_person(name: str) -> str:
    """Strip trailing birth years / role noise from OSZK person strings."""
    text = _clean_text(name)
    text = re.sub(r"\s+\d{4}-\s*$", "", text)
    text = re.sub(r"\s+\(\s*szerk\.?\s*\)\s*$", "", text, flags=re.I)
    return text.strip(" ,;")
def _parse_oszk_ris(text: str, plain: str) -> Optional[dict]:
    """Parse VuFind RIS export from Széchényi Híd."""
    fields: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Z0-9]{2})\s+-\s+(.*)$", line)
        if not m:
            continue
        fields.setdefault(m.group(1), []).append(m.group(2).strip())

    title = _clean_text((fields.get("TI") or fields.get("ST") or [""])[0])
    if _is_bogus_title(title):
        return None

    isbn_vals = fields.get("SN") or []
    if isbn_vals and not any(_isbn_equal(v, plain) for v in isbn_vals):
        return None
    if not isbn_vals and plain not in text.replace("-", ""):
        return None

    authors = _join(
        [
            _clean_oszk_person(name)
            for key in ("A1", "AU", "A2", "A3", "ED")
            for name in fields.get(key, [])
            if _clean_oszk_person(name)
        ]
    )

    notes = fields.get("N1") or []
    publisher = ""
    for note in notes:
        m = re.search(r"Közread\.\s*a\s+(.+)$", note, flags=re.I)
        if m:
            publisher = _clean_text(m.group(1))
            break

    year = None
    for note in notes:
        year = _year_from_text(note)
        if year:
            break

    return {
        "title": title,
        "authors": authors,
        "publication_year": year,
        "genre": _join(fields.get("KW") or []),
        "publisher": publisher,
        "cover_url": "",
        "description": "",
        "source": "oszk",
    }


async def _oszk_hu(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    """National Széchényi Library (Hungary) via Széchényi Híd VuFind."""
    plain = isbn.replace("-", "")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
        "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8,es;q=0.7",
    }
    search_url = (
        "https://szechenyihid.oszk.hu/Search/Results"
        f"?lookfor={quote(plain)}&type=ISN"
    )
    try:
        search = await client.get(search_url, headers=headers, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if search.status_code != 200:
        return None

    record_ids = re.findall(r'href="/Record/(\d+)', search.text)
    if not record_ids:
        return None
    record_id = record_ids[0]

    export_url = (
        f"https://szechenyihid.oszk.hu/Record/{record_id}/Export?style=RIS"
    )
    try:
        export = await client.get(export_url, headers=headers, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if export.status_code != 200:
        return None

    # VuFind sometimes wraps RIS in HTML; prefer raw RIS body.
    body = export.text
    if "TY  - " not in body and "TI  - " not in body:
        # Try EndNote as fallback
        try:
            endnote = await client.get(
                f"https://szechenyihid.oszk.hu/Record/{record_id}/Export?style=EndNote",
                headers=headers,
                follow_redirects=True,
            )
        except httpx.HTTPError:
            return None
        if endnote.status_code != 200 or "%T " not in endnote.text:
            return None
        # Convert minimal EndNote → dict
        title = ""
        authors: list[str] = []
        isbn_val = ""
        for line in endnote.text.splitlines():
            if line.startswith("%T "):
                title = line[3:].strip()
            elif line.startswith("%E ") or line.startswith("%A "):
                authors.append(_clean_oszk_person(line[3:]))
            elif line.startswith("%@ "):
                isbn_val = line[3:].strip()
        if isbn_val and not _isbn_equal(isbn_val, plain):
            return None
        if _is_bogus_title(title):
            return None
        return {
            "title": title,
            "authors": _join(authors),
            "publication_year": None,
            "genre": "",
            "publisher": "",
            "cover_url": "",
            "description": "",
            "source": "oszk",
        }

    # If HTML wrapper, extract pre/plaintext RIS
    if "<html" in body.lower():
        pre = re.search(r"<pre[^>]*>(.*?)</pre>", body, flags=re.I | re.S)
        if pre:
            body = html_lib.unescape(pre.group(1))
        else:
            # Export page may require posting; fall back to EndNote above already handled
            return None

    parsed = _parse_oszk_ris(body, plain)
    if _usable_hit(parsed):
        return parsed
    return None
