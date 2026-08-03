"""Shared ISBN, text, and result helpers."""

from __future__ import annotations

import html as html_lib
import os
import re
from typing import Any, Optional

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
