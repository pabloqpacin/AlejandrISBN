"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import quote

import httpx

from app.services.isbn_lookup.merge import _merge
from app.services.isbn_lookup.util import (
    _author_names,
    _clean_text,
    _https,
    _isbn_equal,
    _join,
    _year_from_text,
    hyphenate_isbn13,
    to_isbn13,
)

def _parse_ttl_book_ldjson(html: str) -> Optional[dict]:
    blocks = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    )
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for node in candidates:
            if not isinstance(node, dict):
                continue
            types = node.get("@type")
            type_set = {types} if isinstance(types, str) else set(types or [])
            if "Book" not in type_set:
                continue

            title = _clean_text(node.get("name"))
            if not title:
                continue

            authors = [_clean_text(a) for a in _author_names(node.get("author"))]
            cover = node.get("image") or ""
            description = _clean_text(node.get("description"))
            year = _year_from_text(node.get("datePublished"))
            publisher = ""
            genre = ""

            examples = node.get("workExample") or []
            if isinstance(examples, dict):
                examples = [examples]
            for example in examples:
                if not isinstance(example, dict):
                    continue
                year = year or _year_from_text(example.get("datePublished"))
                if example.get("isbn") and not cover:
                    pass

            brand = re.search(r'item_brand:\s*"([^"]+)"', html)
            if brand:
                publisher = _clean_text(brand.group(1))

            crumb = re.search(
                r"todostuslibros\.com/categoria/[^\"]+\"\s*,\s*\"name\":\s*\"([^\"]+)\"",
                html,
            )
            if crumb:
                genre = _clean_text(crumb.group(1))

            editorial = re.search(
                r'todostuslibros\.com/editoriales/[^"]+"[^>]*>\s*([^<]+)\s*<',
                html,
                flags=re.I,
            )
            if editorial and not publisher:
                publisher = _clean_text(editorial.group(1))

            if not year:
                fecha = re.search(r"(\d{2}-\d{2}-(19|20)\d{2})", html)
                if fecha:
                    year = _year_from_text(fecha.group(1))

            return {
                "title": title,
                "authors": _join(authors),
                "publication_year": year,
                "genre": genre,
                "publisher": publisher,
                "cover_url": _https(str(cover)),
                "description": description,
                "source": "todostuslibros",
            }
    return None


def _parse_ttl_search(html: str, isbn: str) -> Optional[dict]:
    plain = isbn.replace("-", "").upper()
    li_tags = list(
        re.finditer(
            r"<li\s+class=\"book-col\"([^>]*)>(.*?)</li>",
            html,
            flags=re.I | re.S,
        )
    )

    chosen_attrs = ""
    chosen_body = ""
    for match in li_tags:
        attrs, body = match.group(1), match.group(2)
        isbn_hit = re.search(r'data-gtm-isbn="([^"]+)"', attrs)
        raw = isbn_hit.group(1) if isbn_hit else ""
        # Exact edition only — TTL search often returns near-miss ISBNs.
        if raw and _isbn_equal(raw, plain):
            chosen_attrs, chosen_body = attrs, body
            break

    if not chosen_attrs:
        return None

    title = re.search(r'data-gtm-titulo="([^"]+)"', chosen_attrs)
    if not title:
        title = re.search(r'class="title">\s*<a[^>]*>\s*([^<]+)', chosen_body)
    publisher = re.search(r'data-gtm-editorial="([^"]+)"', chosen_attrs)
    authors = re.search(r'class="author">\s*([^<]+)', chosen_body)
    href = re.search(r'href="(https://www\.todostuslibros\.com/libros/[^"]+)"', chosen_body)
    img = re.search(r'<img[^>]+src="([^"]+)"', chosen_body)
    if not title:
        return None
    return {
        "title": _clean_text(title.group(1)),
        "authors": _clean_text(authors.group(1) if authors else ""),
        "publication_year": None,
        "genre": "",
        "publisher": _clean_text(publisher.group(1) if publisher else ""),
        "cover_url": _https(img.group(1)) if img else "",
        "description": "",
        "source": "todostuslibros",
        "_detail_url": href.group(1) if href else "",
    }


async def _todos_tus_libros(client: httpx.AsyncClient, isbn: str) -> Optional[dict]:
    """Spanish retail/catalog aggregate (CEGAL) — strong for local ISBNs."""
    plain = isbn.replace("-", "")
    candidates = [
        f"https://www.todostuslibros.com/isbn/{plain}",
        f"https://www.todostuslibros.com/isbn/{hyphenate_isbn13(to_isbn13(plain) or plain)}",
        f"https://www.todostuslibros.com/busquedas?keyword={quote(plain)}",
    ]
    # de-dupe while preserving order
    seen: set[str] = set()
    urls = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            urls.append(url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }

    for url in urls:
        try:
            resp = await client.get(url, headers=headers, follow_redirects=True)
        except httpx.HTTPError:
            continue
        if resp.status_code != 200:
            continue
        html = resp.text
        parsed = _parse_ttl_book_ldjson(html)
        if parsed and parsed.get("title"):
            return parsed

        search_hit = _parse_ttl_search(html, plain)
        if not search_hit:
            continue

        detail_url = search_hit.pop("_detail_url", "")
        if detail_url:
            try:
                detail = await client.get(detail_url, headers=headers, follow_redirects=True)
                if detail.status_code == 200:
                    rich = _parse_ttl_book_ldjson(detail.text)
                    if rich and rich.get("title"):
                        return _merge(rich, search_hit)
            except httpx.HTTPError:
                pass
        return search_hit

    return None
