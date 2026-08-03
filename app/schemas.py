import re
import uuid
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

LOCAL_ID_RE = re.compile(r"^LOCAL-[A-Z0-9]{8,32}$", re.IGNORECASE)

PRINT_MEDIA_TYPES = frozenset({"book", "magazine"})
MediaTypeName = Literal["book", "magazine", "cd", "dvd", "vhs", "cassette"]


class MediaType(str, Enum):
    book = "book"
    magazine = "magazine"
    cd = "cd"
    dvd = "dvd"
    vhs = "vhs"
    cassette = "cassette"


def generate_item_id() -> str:
    return str(uuid.uuid4())


def normalize_isbn(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch.isalnum()).upper()
    if len(cleaned) not in (10, 13):
        raise ValueError("ISBN must be 10 or 13 characters (digits, X allowed for ISBN-10)")
    return cleaned


def is_local_id(value: str) -> bool:
    return bool(LOCAL_ID_RE.match((value or "").strip()))


def generate_local_id() -> str:
    """Deprecated identity helper — kept for legacy import normalization only."""
    return f"LOCAL-{uuid.uuid4().hex[:12].upper()}"


def normalize_book_key(value: str) -> str:
    """Legacy helper: accept a real ISBN or a LOCAL-* inventory id."""
    raw = (value or "").strip()
    if is_local_id(raw):
        return raw.upper()
    return normalize_isbn(raw)


def is_print_media(media_type: str | MediaType | None) -> bool:
    value = media_type.value if isinstance(media_type, MediaType) else str(media_type or "")
    return value in PRINT_MEDIA_TYPES


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


_AUTHOR_SEP_RE = re.compile(r"\s*[;/]\s*")
_COLLECTIVE_AUTHOR_RE = re.compile(
    r"^(aa\.?\s*v\.?v\.?|aavv|vv\.?\s*aa\.?|various authors|varios autores)$",
    re.IGNORECASE,
)
_MIDDLE_INITIAL_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]\.?$")
# Common compound given names (Spanish / frequent Western pairs), casefolded.
_COMPOUND_GIVEN = {
    ("ana", "maría"),
    ("ana", "maria"),
    ("carlos", "alberto"),
    ("charles", "henri"),
    ("jean", "paul"),
    ("jean", "pierre"),
    ("josé", "antonio"),
    ("jose", "antonio"),
    ("josé", "luis"),
    ("jose", "luis"),
    ("josé", "maría"),
    ("jose", "maria"),
    ("juan", "antonio"),
    ("juan", "carlos"),
    ("juan", "josé"),
    ("juan", "jose"),
    ("juan", "luis"),
    ("juan", "manuel"),
    ("juan", "pablo"),
    ("luis", "miguel"),
    ("maría", "josé"),
    ("maria", "jose"),
    ("maría", "luisa"),
    ("maria", "luisa"),
    ("maría", "teresa"),
    ("maria", "teresa"),
    ("miguel", "ángel"),
    ("miguel", "angel"),
}


def _given_token_count(tokens: list[str]) -> int:
    if len(tokens) < 3:
        return 1
    if (tokens[0].casefold(), tokens[1].casefold()) in _COMPOUND_GIVEN:
        return 2
    if _MIDDLE_INITIAL_RE.fullmatch(tokens[1]):
        return 2
    return 1


def invert_person_name(person: str) -> str:
    """Turn ``Name Surname…`` into ``Surname…, Name``. Leave tidy ``Surname, Name`` as-is."""
    text = re.sub(r"\s+", " ", (person or "").strip())
    if not text:
        return ""
    if _COLLECTIVE_AUTHOR_RE.match(text):
        return "AA. VV."

    if "," in text:
        left, _, right = text.partition(",")
        left, right = left.strip(), right.strip()
        if not left or not right:
            return text
        left_tokens = left.split(" ")
        right_tokens = right.split(" ")
        # Repair prior over-split: "Carlos Berrio…, Juan" → "Berrio…, Juan Carlos"
        if (
            len(right_tokens) == 1
            and len(left_tokens) >= 2
            and (right_tokens[0].casefold(), left_tokens[0].casefold()) in _COMPOUND_GIVEN
        ):
            given = f"{right_tokens[0]} {left_tokens[0]}"
            surname = " ".join(left_tokens[1:])
            return f"{surname}, {given}"
        # Repair "K. Dick, Philip" / "R TOLKIEN, J R" → "Dick, Philip K." / "TOLKIEN, J R R"
        if len(left_tokens) >= 2:
            i = 0
            while i < len(left_tokens) and _MIDDLE_INITIAL_RE.fullmatch(left_tokens[i]):
                i += 1
            if 1 <= i < len(left_tokens) and right_tokens:
                right_all_initials = all(_MIDDLE_INITIAL_RE.fullmatch(t) for t in right_tokens)
                if right_all_initials or len(right_tokens) == 1:
                    initials = left_tokens[:i]
                    surname = " ".join(left_tokens[i:])
                    given = " ".join([*right_tokens, *initials])
                    return f"{surname}, {given}"
        return f"{left}, {right}"

    tokens = text.split(" ")
    if len(tokens) < 2:
        return text
    n_given = _given_token_count(tokens)
    given = " ".join(tokens[:n_given])
    surname = " ".join(tokens[n_given:])
    if not surname:
        return text
    return f"{surname}, {given}"


def normalize_authors(value: Optional[str]) -> str:
    """Split on ``;`` / ``/``, invert ``Name Surname`` → ``Surname, Name``, join with ``; ``."""
    if value is None:
        return ""
    seen: set[str] = set()
    unique: list[str] = []
    for raw in _AUTHOR_SEP_RE.split(str(value)):
        person = invert_person_name(raw)
        if not person:
            continue
        key = person.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(person)
    return "; ".join(unique)


def format_placement(room: str = "", furniture: str = "", legacy_location: str = "") -> str:
    """Compose a single display string: ``Habitación · Mueble``."""
    room_text = (room or "").strip()
    furniture_text = (furniture or "").strip()
    if room_text and furniture_text:
        return f"{room_text} · {furniture_text}"
    if room_text or furniture_text:
        return room_text or furniture_text
    return (legacy_location or "").strip()


def resolve_placement(
    *,
    room: Optional[str] = None,
    furniture: Optional[str] = None,
    location: Optional[str] = None,
) -> tuple[str, str, str]:
    """Normalize room/furniture; legacy ``location`` fills ``room`` when room is empty."""
    room_text = (room or "").strip()
    furniture_text = (furniture or "").strip()
    legacy = (location or "").strip()
    if not room_text and legacy:
        # Avoid duplicating an already-composed location into room.
        if " · " in legacy and not furniture_text:
            left, _, right = legacy.partition(" · ")
            room_text, furniture_text = left.strip(), right.strip()
        else:
            room_text = legacy
    composed = format_placement(room_text, furniture_text)
    return room_text, furniture_text, composed


class ItemCreate(BaseModel):
    """Create from ISBN lookup (print), or manually for any media type."""

    media_type: MediaType = MediaType.book
    isbn: Optional[str] = Field(None, max_length=40)
    title: Optional[str] = None
    authors: Optional[str] = None
    publication_year: Optional[int] = None
    genre: Optional[str] = None
    publisher: Optional[str] = None
    cover_url: Optional[str] = None
    description: Optional[str] = None
    room: str = ""
    furniture: str = ""
    location: str = ""  # legacy; mapped into room/furniture when needed
    notes: str = ""
    legal_deposit: str = ""
    collection: str = ""
    volume: str = ""
    original_year: Optional[int] = None
    translators: str = ""
    original_title: str = ""
    favourite: bool = False

    @model_validator(mode="after")
    def validate_identity(self) -> "ItemCreate":
        isbn = (self.isbn or "").strip()
        title = (self.title or "").strip()
        self.authors = normalize_authors(self.authors)
        self.genre = normalize_labels(self.genre)
        self.translators = normalize_authors(self.translators)
        self.room, self.furniture, self.location = resolve_placement(
            room=self.room, furniture=self.furniture, location=self.location
        )
        self.notes = (self.notes or "").strip()
        self.collection = (self.collection or "").strip()
        self.volume = (self.volume or "").strip()
        self.original_title = (self.original_title or "").strip()
        self.legal_deposit = (self.legal_deposit or "").strip()
        if self.legal_deposit.lower() in {"n/a", "na", "n.a.", "n.a", "none", "null", "-", "—", "–"}:
            self.legal_deposit = ""

        if not is_print_media(self.media_type):
            if isbn:
                raise ValueError("isbn only applies to books and magazines")
            if not title:
                raise ValueError("title is required")
            self.isbn = None
            self.title = title
            self.legal_deposit = ""
            return self

        if not isbn or is_local_id(isbn):
            if not title:
                raise ValueError("title is required when creating without ISBN")
            self.isbn = None
            self.title = title
            return self

        self.isbn = normalize_isbn(isbn)
        if title:
            self.title = title
        return self


class ItemUpdate(BaseModel):
    media_type: Optional[MediaType] = None
    isbn: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    publication_year: Optional[int] = None
    genre: Optional[str] = None
    publisher: Optional[str] = None
    cover_url: Optional[str] = None
    description: Optional[str] = None
    room: Optional[str] = None
    furniture: Optional[str] = None
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
    def normalize_label_fields(self) -> "ItemUpdate":
        if self.authors is not None:
            self.authors = normalize_authors(self.authors)
        if self.genre is not None:
            self.genre = normalize_labels(self.genre)
        if self.translators is not None:
            self.translators = normalize_authors(self.translators)
        if self.collection is not None:
            self.collection = (self.collection or "").strip()
        if self.volume is not None:
            self.volume = (self.volume or "").strip()
        if self.original_title is not None:
            self.original_title = (self.original_title or "").strip()
        if self.room is not None:
            self.room = (self.room or "").strip()
        if self.furniture is not None:
            self.furniture = (self.furniture or "").strip()
        if self.location is not None:
            self.location = (self.location or "").strip()
        if self.legal_deposit is not None:
            text = (self.legal_deposit or "").strip()
            if text.lower() in {"n/a", "na", "n.a.", "n.a", "none", "null", "-", "—", "–"}:
                text = ""
            self.legal_deposit = text
        if self.isbn is not None:
            raw = (self.isbn or "").strip()
            if not raw or is_local_id(raw):
                self.isbn = None
            else:
                self.isbn = normalize_isbn(raw)
        return self


class ItemOut(BaseModel):
    id: str
    media_type: MediaTypeName = "book"
    isbn: Optional[str] = None
    title: str
    authors: str
    publication_year: Optional[int] = None
    genre: str = ""
    publisher: str = ""
    cover_url: str = ""
    description: str = ""
    room: str = ""
    furniture: str = ""
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
        isbn = (self.isbn or "").strip()
        return bool(isbn) and not is_local_id(isbn)


class FurnitureStat(BaseModel):
    value: str
    count: int


class RoomStat(BaseModel):
    value: str
    count: int
    furniture: list[FurnitureStat] = []


class StatsOut(BaseModel):
    total: int
    by_media_type: dict[str, int]
    by_room: list[RoomStat] = []
    by_location: list[dict[str, int | str]] = []  # legacy flat list for older UI


# Back-compat aliases
BookCreate = ItemCreate
BookUpdate = ItemUpdate
BookOut = ItemOut
