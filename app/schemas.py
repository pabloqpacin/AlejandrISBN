from typing import Optional

from pydantic import BaseModel, Field, field_validator


def normalize_isbn(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch.isalnum()).upper()
    if len(cleaned) not in (10, 13):
        raise ValueError("ISBN must be 10 or 13 characters (digits, X allowed for ISBN-10)")
    return cleaned


class BookCreate(BaseModel):
    """Create from ISBN lookup, with optional manual overrides from the review UI."""

    isbn: str = Field(..., min_length=10, max_length=17)
    title: Optional[str] = None
    authors: Optional[str] = None
    publication_year: Optional[int] = None
    genre: Optional[str] = None
    publisher: Optional[str] = None
    cover_url: Optional[str] = None
    description: Optional[str] = None
    location: str = ""
    notes: str = ""

    @field_validator("isbn")
    @classmethod
    def validate_isbn(cls, value: str) -> str:
        return normalize_isbn(value)


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
    source: str = ""
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
