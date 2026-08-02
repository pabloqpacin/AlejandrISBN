"""Fetch bibliographic metadata from multiple free public catalogs."""

from __future__ import annotations

import asyncio
import html as html_lib
import json
import os
import re
from typing import Any, Optional
from urllib.parse import quote, unquote

import httpx

TIMEOUT = httpx.Timeout(15.0, connect=6.0)
USER_AGENT = (
    "AlejandrISBN/1.0 (library-inventory; +https://github.com/alejandrisbn)"
)
GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY", "").strip()


def _year_from_text(value: Any) -> Optional[int]:
    if value is None:
        return None
    match = re.search(r"(19|20)\d{2}", str(value))
    return int(match.group(0)) if match else None


def _join(values: list[str], sep: str = "; ") -> str:
    cleaned = [v.strip() for v in values if v and str(v).strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for item in cleaned:
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return sep.join(unique)


def _isbn10_check_digit(body9: str) -> str:
    total = sum((10 - i) * (10 if ch == "X" else int(ch)) for i, ch in enumerate(body9))
    remainder = total % 11
    check = (11 - remainder) % 11
    return "X" if check == 10 else str(check)


def _isbn13_check_digit(body12: str) -> str:
    total = sum((1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(body12))
    return str((10 - (total % 10)) % 10)


def to_isbn13(isbn: str) -> Optional[str]:
    isbn = isbn.upper()
    if len(isbn) == 13 and isbn.isdigit():
        return isbn
    if len(isbn) != 10:
        return None
    body = "978" + isbn[:9]
    return body + _isbn13_check_digit(body)


def to_isbn10(isbn: str) -> Optional[str]:
    isbn = isbn.upper()
    if len(isbn) == 10:
        return isbn
    if len(isbn) != 13 or not isbn.isdigit() or not isbn.startswith("978"):
        return None
    body = isbn[3:12]
    return body + _isbn10_check_digit(body)


def hyphenate_isbn13(isbn13: str) -> str:
    """Best-effort hyphenation for Spanish-looking ISBNs; else plain groups."""
    if len(isbn13) != 13:
        return isbn13
    # 978-84-XX-XXXXX-X is common for Spain (group 84)
    if isbn13.startswith("97884"):
        return f"{isbn13[:3]}-{isbn13[3:5]}-{isbn13[5:7]}-{isbn13[7:12]}-{isbn13[12]}"
    return isbn13


def isbn_variants(isbn: str) -> list[str]:
    """Return unique ISBN forms to query (raw, ISBN-13, ISBN-10, hyphenated)."""
    clean = "".join(ch for ch in isbn if ch.isalnum()).upper()
    variants: list[str] = []
    for candidate in (
        clean,
        to_isbn13(clean) or "",
        to_isbn10(clean) or "",
    ):
        if candidate and candidate not in variants:
            variants.append(candidate)
    isbn13 = to_isbn13(clean)
    if isbn13 and isbn13.startswith("97884"):
        hyp = hyphenate_isbn13(isbn13)
        if hyp not in variants:
            variants.append(hyp)
    return variants


def _empty_result() -> dict:
    return {
        "title": "",
        "authors": "",
        "publication_year": None,
        "genre": "",
        "publisher": "",
        "cover_url": "",
        "description": "",
        "source": "",
    }


def _https(url: str) -> str:
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


def _clean_text(value: Any) -> str:
    """Unescape HTML entities and normalize whitespace from scraped fields."""
    if value is None:
        return ""
    text = html_lib.unescape(str(value)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _isbn_equal(a: str, b: str) -> bool:
    """True when two ISBN strings refer to the same edition (10/13 aware)."""
    left = (a or "").replace("-", "").upper()
    right = (b or "").replace("-", "").upper()
    if not left or not right:
        return False
    if left == right:
        return True

    def forms(value: str) -> set[str]:
        out = {value}
        as13 = to_isbn13(value)
        as10 = to_isbn10(value)
        if as13:
            out.add(as13.upper())
        if as10:
            out.add(as10.upper())
        return out

    return bool(forms(left) & forms(right))


_BOGUS_TITLE_RE = re.compile(
    r"(please\s+verify|verify\s+to\s+continue|just\s+a\s+moment|"
    r"attention\s+required|access\s+denied|captcha|cloudflare|"
    r"are\s+you\s+a\s+robot|enable\s+javascript|checking\s+your\s+browser|"
    r"security\s+check|one\s+more\s+step)",
    flags=re.I,
)


def _is_bogus_title(title: Any) -> bool:
    """Reject CAPTCHA / bot-wall pages scraped as book titles."""
    if not title or not str(title).strip():
        return True
    text = str(title).strip()
    if _BOGUS_TITLE_RE.search(text):
        return True
    # Real book titles are rarely this short challenge phrase
    if text.casefold() in {
        "please verify",
        "please verify to continue",
        "verify to continue",
        "access denied",
        "forbidden",
        "error",
        "not found",
    }:
        return True
    return False


def _usable_hit(result: Optional[dict]) -> bool:
    return bool(result and not _is_bogus_title(result.get("title")))


def _author_names(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        name = value.get("name")
        return [name] if name else []
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            names.extend(_author_names(item))
        return names
    return []


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


def _clean_oszk_person(name: str) -> str:
    """Strip trailing birth years / role noise from OSZK person strings."""
    text = _clean_text(name)
    text = re.sub(r"\s+\d{4}-\s*$", "", text)
    text = re.sub(r"\s+\(\s*szerk\.?\s*\)\s*$", "", text, flags=re.I)
    return text.strip(" ,;")


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


def _mostly_cjk(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    cjk = sum(
        1
        for ch in letters
        if "\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff"
    )
    return cjk >= max(1, (len(letters) + 1) // 2)


def _human_genre(value: str) -> str:
    """Keep readable genres; drop Open Library machine tags like franchise:/form:."""
    parts: list[str] = []
    for raw in value.split(","):
        piece = raw.strip()
        if not piece:
            continue
        if ":" in piece:
            key, _, rest = piece.partition(":")
            if key.casefold() in {"genre", "subject", "category"} and rest.strip():
                parts.append(rest.strip())
            continue
        parts.append(piece)
    return _join(parts)


def _merge(*parts: Optional[dict]) -> dict:
    merged = _empty_result()
    sources: list[str] = []
    text_keys = {"title", "authors", "genre", "publisher", "description", "cover_url"}
    for part in parts:
        if not part or _is_bogus_title(part.get("title")):
            continue
        src = part.get("source")
        if src:
            sources.append(str(src))
        for key, value in part.items():
            if key in {"source", "_detail_url"}:
                continue
            if key in text_keys and isinstance(value, str):
                value = _clean_text(value)
            if key == "genre" and value:
                value = _human_genre(value)
            if key == "title" and _is_bogus_title(value):
                continue
            current = merged.get(key)
            empty = current is None or current == ""
            if empty and value not in (None, ""):
                merged[key] = value
                continue
            # Prefer Latin-script author names over CJK-only catalog forms.
            if (
                key == "authors"
                and current
                and value
                and _mostly_cjk(str(current))
                and not _mostly_cjk(str(value))
            ):
                merged[key] = value
    merged["source"] = "+".join(dict.fromkeys(sources))
    return merged


async def _first_hit(coros) -> Optional[dict]:
    """Run coroutines concurrently; return first useful metadata dict."""
    tasks = [asyncio.create_task(coro) for coro in coros]
    try:
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
            except Exception:
                continue
            if _usable_hit(result):
                for other in tasks:
                    other.cancel()
                return result
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
    return None


async def lookup_isbn(isbn: str) -> dict:
    """Resolve ISBN metadata across catalogs. Raises ValueError if not found."""
    variants = isbn_variants(isbn)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json,text/html,*/*"}

    plain_variants = [v.replace("-", "") for v in variants]
    plain_variants = list(dict.fromkeys(plain_variants))
    primary_isbn = plain_variants[0] if plain_variants else isbn.replace("-", "")
    italian = primary_isbn.startswith("97888") or primary_isbn.startswith("97912")
    # 978-963-… legacy Hungarian group; 978-615-… current group
    hungarian = primary_isbn.startswith("978963") or primary_isbn.startswith("978615")
    # 978-84-… Spain (incl. Galician imprints often only in RBGalicia)
    spanish = primary_isbn.startswith("97884") or primary_isbn.startswith("97913")

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers, follow_redirects=True) as client:
        # Italian: IBS. Hungarian: OSZK. Spanish: TTL + RBGalicia. Always race Open Library.
        lead = []
        if italian:
            lead.extend(_ibs_it(client, v) for v in plain_variants[:2])
        elif hungarian:
            lead.extend(_oszk_hu(client, v) for v in plain_variants[:2])
        else:
            lead.extend(_todos_tus_libros(client, v) for v in plain_variants[:2])
            if spanish:
                lead.extend(_rbgalicia(client, v) for v in plain_variants[:2])
        lead.extend(_open_library_books_api(client, v) for v in plain_variants[:2])

        primary = await _first_hit(lead)

        fillers = await asyncio.gather(
            *[_open_library_search(client, v) for v in plain_variants[:2]],
            *[_google_books(client, v) for v in plain_variants[:2]],
            *[_open_library_books_api(client, v) for v in plain_variants[:2]],
            *[_ibs_it(client, v) for v in plain_variants[:1]],
            *[_todos_tus_libros(client, v) for v in plain_variants[:1]],
            *[_rbgalicia(client, v) for v in plain_variants[:1]],
            *[_isbnsearch_org(client, v) for v in plain_variants[:1]],
            *[_abebooks(client, v) for v in plain_variants[:1]],
            *[_goodreads(client, v) for v in plain_variants[:1]],
            *[_buybook_tw(client, v) for v in plain_variants[:1]],
            *[_oszk_hu(client, v) for v in plain_variants[:1]],
            return_exceptions=True,
        )

    filler_dicts = [r for r in fillers if isinstance(r, dict)]
    merged = _merge(primary, *filler_dicts)

    if not merged.get("title"):
        # Last resort: sequential deeper search over all variants / catalogs
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers, follow_redirects=True) as client:
            fetchers = (
                _rbgalicia,
                _oszk_hu,
                _buybook_tw,
                _goodreads,
                _abebooks,
                _isbnsearch_org,
                _ibs_it,
                _todos_tus_libros,
                _open_library_search,
                _google_books,
            )
            for variant in variants:
                for fetcher in fetchers:
                    hit = await fetcher(client, variant)
                    if _usable_hit(hit):
                        merged = _merge(merged, hit)
                        break
                if not _is_bogus_title(merged.get("title")):
                    break

    if _is_bogus_title(merged.get("title")):
        tried = ", ".join(variants)
        raise ValueError(f"No bibliographic data found for ISBN {isbn} (tried: {tried})")

    if not merged.get("cover_url"):
        plain = (to_isbn13(isbn) or isbn).replace("-", "")
        merged["cover_url"] = f"https://covers.openlibrary.org/b/isbn/{plain}-L.jpg"
    return merged
