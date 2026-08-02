import re
import uuid
from typing import Optional

from pydantic import BaseModel, Field, model_validator

LOCAL_ID_RE = re.compile(r"^LOCAL-[A-Z0-9]{8,32}$", re.IGNORECASE)


def normalize_isbn(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch.isalnum()).upper()
    if len(cleaned) not in (10, 13):
        raise ValueError("ISBN must be 10 or 13 characters (digits, X allowed for ISBN-10)")
    return cleaned


def is_local_id(value: str) -> bool:
    return bool(LOCAL_ID_RE.match((value or "").strip()))


def generate_local_id() -> str:
    return f"LOCAL-{uuid.uuid4().hex[:12].upper()}"


def normalize_book_key(value: str) -> str:
    """Accept a real ISBN or a LOCAL-* inventory id."""
    raw = (value or "").strip()
    if is_local_id(raw):
        return raw.upper()
    return normalize_isbn(raw)


def normalize_labels(value: Optional[str]) -> str:
    """Normalize ``;``-separated labels (authors, genres): trim empties, join with ``; ``."""
    if value is None:
        return ""
    parts = [part.strip() for part in str(value).split(";")]
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        if not part:
            continue
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)
    return "; ".join(unique)


class BookCreate(BaseModel):
    """Create from ISBN lookup, or manually without ISBN (magazines, manuals, docs)."""

    isbn: Optional[str] = Field(None, max_length=40)
    title: Optional[str] = None
    authors: Optional[str] = None
    publication_year: Optional[int] = None
    genre: Optional[str] = None
    publisher: Optional[str] = None
    cover_url: Optional[str] = None
    description: Optional[str] = None
    location: str = ""
    notes: str = ""
    legal_deposit: str = ""
    collection: str = ""
    volume: str = ""
    original_year: Optional[int] = None
    translators: str = ""
    original_title: str = ""
    favourite: bool = False

    @model_validator(mode="after")
    def validate_identity(self) -> "BookCreate":
        isbn = (self.isbn or "").strip()
        title = (self.title or "").strip()
        self.authors = normalize_labels(self.authors)
        self.genre = normalize_labels(self.genre)
        self.translators = normalize_labels(self.translators)
        self.location = (self.location or "").strip()
        self.notes = (self.notes or "").strip()
        self.collection = (self.collection or "").strip()
        self.volume = (self.volume or "").strip()
        self.original_title = (self.original_title or "").strip()
        self.legal_deposit = (self.legal_deposit or "").strip()
        if self.legal_deposit.lower() in {"n/a", "na", "n.a.", "n.a", "none", "null", "-", "—", "–"}:
            self.legal_deposit = ""

        if not isbn:
            if not title:
                raise ValueError("title is required when creating without ISBN")
            self.isbn = None
            self.title = title
            return self

        if is_local_id(isbn):
            if not title:
                raise ValueError("title is required for items without ISBN")
            self.isbn = isbn.upper()
            self.title = title
            return self

        self.isbn = normalize_isbn(isbn)
        if title:
            self.title = title
        return self


class BookUpdate(BaseModel):
    title: Optional[str] = None
    authors: Optional[str] = None
    publication_year: Optional[int] = None
    genre: Optional[str] = None
    publisher: Optional[str] = None
    cover_url: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    legal_deposit: Optional[str] = None
    collection: Optional[str] = None
    volume: Optional[str] = None
    original_year: Optional[int] = None
    translators: Optional[str] = None
    original_title: Optional[str] = None
    favourite: Optional[bool] = None

    @model_validator(mode="after")
    def normalize_label_fields(self) -> "BookUpdate":
        if self.authors is not None:
            self.authors = normalize_labels(self.authors)
        if self.genre is not None:
            self.genre = normalize_labels(self.genre)
        if self.translators is not None:
            self.translators = normalize_labels(self.translators)
        if self.collection is not None:
            self.collection = (self.collection or "").strip()
        if self.volume is not None:
            self.volume = (self.volume or "").strip()
        if self.original_title is not None:
            self.original_title = (self.original_title or "").strip()
        return self


class BookOut(BaseModel):
    isbn: str
    title: str
    authors: str
    publication_year: Optional[int] = None
    genre: str = ""
    publisher: str = ""
    cover_url: str = ""
    description: str = ""
    location: str = ""
    notes: str = ""
    legal_deposit: str = ""
    collection: str = ""
    volume: str = ""
    original_year: Optional[int] = None
    translators: str = ""
    original_title: str = ""
    favourite: bool = False
    source: str = ""
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @property
    def has_isbn(self) -> bool:
        return not is_local_id(self.isbn)
