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
    favourite: bool = False

    @model_validator(mode="after")
    def validate_identity(self) -> "BookCreate":
        isbn = (self.isbn or "").strip()
        title = (self.title or "").strip()

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
    favourite: Optional[bool] = None


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
    favourite: bool = False
    source: str = ""
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @property
    def has_isbn(self) -> bool:
        return not is_local_id(self.isbn)
