"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.services.isbn_lookup.util import _author_names, _https, _join, _year_from_text

def _props_map(node: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for prop in node.get("additionalProperty") or []:
        if not isinstance(prop, dict):
            continue
        name = str(prop.get("name") or "").strip()
        value = str(prop.get("value") or "").strip()
        if name and value:
            out[name] = value
    return out


def _parse_ibs_ldjson(html: str) -> Optional[dict]:
    """Parse IBS.it / Feltrinelli schema.org Book + Product blocks."""
    blocks = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    )
    book_node: Optional[dict] = None
    product_node: Optional[dict] = None
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        nodes: list[Any]
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            nodes = data["@graph"]
        elif isinstance(data, list):
            nodes = data
        else:
            nodes = [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            types = node.get("@type")
            type_set = {types} if isinstance(types, str) else set(types or [])
            if "Book" in type_set and not book_node:
                book_node = node
            if "Product" in type_set and not product_node:
                product_node = node

    if not book_node and not product_node:
        return None

    props = {}
    props.update(_props_map(product_node or {}))
    props.update(_props_map(book_node or {}))

    title = ((book_node or {}).get("name") or (product_node or {}).get("name") or "").strip()
    if not title:
        return None

    authors = _join(_author_names((book_node or {}).get("author")))
    cover = (book_node or {}).get("image") or (product_node or {}).get("image") or ""
    if isinstance(cover, list):
        cover = cover[0] if cover else ""
    year = _year_from_text(
        (book_node or {}).get("datePublished") or props.get("Anno") or props.get("Year")
    )
    publisher = (
        props.get("Editore")
        or props.get("Publisher")
        or ""
    ).strip()
    # Unescape IBS brand quirks like \\'round midnight
    publisher = publisher.replace("\\'", "'").replace("\\'", "'")

    series = ""
    part = (book_node or {}).get("isPartOf")
    if isinstance(part, list) and part:
        series = str((part[0] or {}).get("name") or "").strip()
    elif isinstance(part, dict):
        series = str(part.get("name") or "").strip()

    return {
        "title": title,
        "authors": authors,
        "publication_year": year,
        "genre": series,
        "publisher": publisher,
        "cover_url": _https(str(cover)),
        "description": "",
        "source": "ibs",
    }


def _parse_ibs_datalayer(html: str) -> Optional[dict]:
    """Fallback: ecommerce item payload embedded in IBS pages."""
    push = re.search(
        r'dataLayer\.push\((\{[^\n]*"item_id"\s*:\s*"(\d{10,13})"[^\n]*\})\)',
        html,
    )
    blob = ""
    if push:
        blob = push.group(1)
    else:
        m2 = re.search(
            r'dataLayer\.push\((\{"event":"view_item".*?\})\)\s*</script>',
            html,
            flags=re.S,
        )
        if m2:
            blob = m2.group(1)
        else:
            m3 = re.search(r'"item_id"\s*:\s*"(\d{10,13})"[^\n]{0,800}', html)
            if m3:
                blob = m3.group(0)

    if not blob:
        return None

    def field(name: str) -> str:
        m = re.search(rf'"{name}"\s*:\s*"((?:\\.|[^"\\])*)"', blob)
        if not m:
            return ""
        return m.group(1).replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")

    title = field("item_name").strip()
    if not title:
        return None
    publisher = field("item_brand").strip()
    return {
        "title": title,
        "authors": field("item_author").strip(),
        "publication_year": _year_from_text(field("year_edition")),
        "genre": field("item_series").strip() or field("item_category3").strip(),
        "publisher": publisher,
        "cover_url": "",
        "description": "",
        "source": "ibs",
    }


async def _ibs_it(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    """Italian retail catalog (IBS / Feltrinelli) — useful for 978-88-* and gaps in OL/TTL."""
    plain = isbn.replace("-", "")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8,es;q=0.7",
        "Accept": "text/html,application/xhtml+xml",
    }
    search_url = f"https://www.ibs.it/search/?ts=as&query={quote(plain)}"
    try:
        search = await client.get(search_url, headers=headers, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if search.status_code != 200:
        return None

    html = search.text
    # Prefer canonical product page when search lists it.
    detail_path = re.search(
        rf'href="(/[^"]+/e/{re.escape(plain)})"',
        html,
        flags=re.I,
    )
    detail_html = html
    if detail_path:
        detail_url = "https://www.ibs.it" + detail_path.group(1)
        try:
            detail = await client.get(detail_url, headers=headers, follow_redirects=True)
            if detail.status_code == 200 and plain in detail.text:
                detail_html = detail.text
        except httpx.HTTPError:
            pass

    parsed = _parse_ibs_ldjson(detail_html) or _parse_ibs_datalayer(detail_html)
    if parsed and parsed.get("title"):
        if not parsed.get("cover_url"):
            parsed["cover_url"] = f"https://www.ibs.it/images/{plain}_0_0_536_0_75.jpg"
        return parsed

    # Last try: datalayer on search results page
    parsed = _parse_ibs_datalayer(html)
    if parsed and parsed.get("title"):
        if not parsed.get("cover_url"):
            parsed["cover_url"] = f"https://www.ibs.it/images/{plain}_0_0_536_0_75.jpg"
        return parsed
    return None
