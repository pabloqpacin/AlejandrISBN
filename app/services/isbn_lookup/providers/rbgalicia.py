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

def _clean_rbgalicia_person(name: str) -> str:
    """Normalize Koha RIS person strings like 'Pérez Álvarez,Xurxo ('."""
    text = _clean_text(name)
    text = re.sub(r"\s*\(\s*\d{4}-?\s*\)?\s*$", "", text)
    text = text.rstrip(" (")
    # Koha often omits the space after the surname comma.
    text = re.sub(r",(\S)", r", \1", text)
    return text.strip(" ,;")


def _parse_rbgalicia_ris(text: str, plain: str) -> Optional[dict]:
    """Parse Koha RIS export from Rede de Bibliotecas de Galicia."""
    fields: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Z0-9]{2})\s+-\s+(.*)$", line)
        if not m:
            continue
        fields.setdefault(m.group(1), []).append(m.group(2).strip())

    title = _clean_text((fields.get("TI") or fields.get("T1") or [""])[0])
    if _is_bogus_title(title):
        return None

    isbn_vals = fields.get("SN") or []
    if isbn_vals and not any(_isbn_equal(v, plain) for v in isbn_vals):
        return None
    if not isbn_vals and plain not in text.replace("-", ""):
        return None

    authors = _join(
        [
            _clean_rbgalicia_person(name)
            for key in ("A1", "AU", "A2", "A3", "ED")
            for name in fields.get(key, [])
            if _clean_rbgalicia_person(name)
        ]
    )

    publisher = _clean_text((fields.get("PB") or [""])[0])
    publisher = re.sub(r"^[:\s]+", "", publisher).strip(" []")

    year = None
    for key in ("PY", "Y1", "DA"):
        for raw in fields.get(key, []):
            year = _year_from_text(raw)
            if year:
                break
        if year:
            break

    description = _clean_text((fields.get("N2") or fields.get("AB") or [""])[0])

    return {
        "title": title,
        "authors": authors,
        "publication_year": year,
        "genre": _join(fields.get("KW") or []),
        "publisher": publisher,
        "cover_url": "",
        "description": description,
        "source": "rbgalicia",
    }


async def _rbgalicia(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    """Rede de Bibliotecas de Galicia (Koha OPAC) — strong for Galician/Spanish ISBNs."""
    plain = isbn.replace("-", "")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
        "Accept-Language": "gl-ES,gl;q=0.9,es;q=0.8,en;q=0.7",
    }
    base = "https://catalogo-rbgalicia.xunta.gal"
    search_url = f"{base}/cgi-bin/koha/opac-search.pl?idx=nb&q={quote(plain)}"
    try:
        search = await client.get(search_url, headers=headers, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if search.status_code != 200:
        return None

    biblionumbers = re.findall(r"biblionumber=(\d+)", search.text)
    if not biblionumbers:
        return None
    biblionumber = biblionumbers[0]

    export_url = (
        f"{base}/cgi-bin/koha/opac-export.pl"
        f"?op=export&bib={biblionumber}&format=ris"
    )
    try:
        export = await client.get(export_url, headers=headers, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if export.status_code != 200:
        return None

    body = export.text
    if "TY  - " not in body and "TI  - " not in body:
        return None
    if "<html" in body.lower():
        pre = re.search(r"<pre[^>]*>(.*?)</pre>", body, flags=re.I | re.S)
        if not pre:
            return None
        body = html_lib.unescape(pre.group(1))

    parsed = _parse_rbgalicia_ris(body, plain)
    if _usable_hit(parsed):
        return parsed
    return None
