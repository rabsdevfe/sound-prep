"""Titles and the folder/file name derived from them (macOS-safe).

Out of scope on purpose: constructors do no runtime type checks (inputs are typed and mypy runs in
strict mode; runtime input arrives through the contract models), and unassigned or private-use
characters and name length beyond the byte limit are left to the filesystem.
"""

import unicodedata
from dataclasses import dataclass

from sound_prep_core.domain.errors import InvalidTitleError

# Limit in UTF-8 bytes: APFS allows 255-byte names and the full track adds ".mp3".
MAX_NAME_BYTES = 200
# Control, format (zero-width, bidi), lone surrogate, line and paragraph separator characters.
# Shared with the output directory check.
FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
_NEUTRALIZED = {"/": "-", ":": "-"}  # same replacement the original script applies


@dataclass(frozen=True, slots=True)
class Title:
    """A title reduced to a name that is safe as both folder name and file stem.

    Construction normalizes (NFC; "/" and ":" become "-"; surrounding whitespace is trimmed) and
    validates, so an unsafe ``Title`` cannot exist. Control, format (zero-width, bidi) and
    line/paragraph separator characters, leading dots (hidden files, "." and ".."), an empty
    result and over-long names are rejected.
    """

    name: str

    def __post_init__(self) -> None:
        text = unicodedata.normalize("NFC", self.name)
        name = "".join(_NEUTRALIZED.get(ch, ch) for ch in text).strip()
        if not name:
            raise InvalidTitleError("Title is empty")
        if any(unicodedata.category(ch) in FORBIDDEN_CATEGORIES for ch in name):
            raise InvalidTitleError("Title contains control or invisible formatting characters")
        if name.startswith("."):
            raise InvalidTitleError("Title must not start with a dot")
        if len(name.encode("utf-8")) > MAX_NAME_BYTES:
            raise InvalidTitleError(f"Title is longer than {MAX_NAME_BYTES} bytes")
        object.__setattr__(self, "name", name)

    @classmethod
    def parse(cls, raw: str) -> "Title":
        # Alias of the constructor, kept for symmetry with ClipTime.parse and call-site clarity.
        return cls(raw)
