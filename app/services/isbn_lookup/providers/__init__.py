"""Catalog provider implementations used by the ISBN lookup orchestrator."""

from app.services.isbn_lookup.providers.abebooks import _abebooks as abebooks
from app.services.isbn_lookup.providers.buybook import _buybook_tw as buybook
from app.services.isbn_lookup.providers.google_books import _google_books as google_books
from app.services.isbn_lookup.providers.goodreads import _goodreads as goodreads
from app.services.isbn_lookup.providers.ibs import _ibs_it as ibs
from app.services.isbn_lookup.providers.isbnsearch import _isbnsearch_org as isbnsearch
from app.services.isbn_lookup.providers.openlibrary import (
    _open_library_books_api as open_library_books_api,
    _open_library_search as open_library_search,
)
from app.services.isbn_lookup.providers.oszk import _oszk_hu as oszk
from app.services.isbn_lookup.providers.rbgalicia import _rbgalicia as rbgalicia
from app.services.isbn_lookup.providers.todos_tus_libros import (
    _todos_tus_libros as todos_tus_libros,
)

__all__ = [
    "abebooks",
    "buybook",
    "google_books",
    "goodreads",
    "ibs",
    "isbnsearch",
    "open_library_books_api",
    "open_library_search",
    "oszk",
    "rbgalicia",
    "todos_tus_libros",
]
