"""Fetch bibliographic metadata from a public catalog."""

from __future__ import annotations

import asyncio

import httpx

from app.services.isbn_lookup.merge import _first_hit, _merge
from app.services.isbn_lookup.providers.abebooks import _abebooks
from app.services.isbn_lookup.providers.buybook import _buybook_tw
from app.services.isbn_lookup.providers.google_books import _google_books
from app.services.isbn_lookup.providers.goodreads import _goodreads
from app.services.isbn_lookup.providers.ibs import _ibs_it
from app.services.isbn_lookup.providers.isbnsearch import _isbnsearch_org
from app.services.isbn_lookup.providers.openlibrary import (
    _open_library_books_api,
    _open_library_search,
)
from app.services.isbn_lookup.providers.oszk import _oszk_hu
from app.services.isbn_lookup.providers.rbgalicia import _rbgalicia
from app.services.isbn_lookup.providers.todos_tus_libros import _todos_tus_libros
from app.services.isbn_lookup.util import (
    TIMEOUT,
    USER_AGENT,
    _is_bogus_title,
    _usable_hit,
    isbn_variants,
    to_isbn13,
)

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

    # Same display form as after save (Surname, Name; …) so the review UI matches inventory.
    from app.schemas import normalize_authors, normalize_labels

    merged["authors"] = normalize_authors(merged.get("authors"))
    if merged.get("genre"):
        merged["genre"] = normalize_labels(merged.get("genre"))
    return merged
