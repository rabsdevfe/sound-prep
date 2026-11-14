"""Titles and the folder/file name derived from them (macOS-safe)."""

import unicodedata
from dataclasses import dataclass

from sound_prep_core.domain.errors import InvalidTitleError

# Limit in UTF-8 bytes: APFS allows 255-byte names and the full track adds ".mp3".
MAX_NAME_BYTES = 200
_NEUTRALIZED = {"/": "-", ":": "-"}  # same replacement the original script applies


@dataclass(frozen=True, slots=True)
class Title:
    """A title reduced to a name that is safe as both folder name and file stem.

    Path separators and ":" become "-". Control and line/paragraph separator characters, leading
    dots (hidden files, "." and ".."), an empty result and over-long names are rejected.
    """

    name: str

    @classmethod
    def parse(cls, raw: str) -> "Title":
        name = "".join(_NEUTRALIZED.get(ch, ch) for ch in raw).strip()
        if not name:
            raise InvalidTitleError("Title is empty")
        if any(unicodedata.category(ch) in {"Cc", "Zl", "Zp"} for ch in name):
            raise InvalidTitleError("Title contains control characters")
        if name.startswith("."):
            raise InvalidTitleError("Title must not start with a dot")
        if len(name.encode("utf-8")) > MAX_NAME_BYTES:
            raise InvalidTitleError(f"Title is longer than {MAX_NAME_BYTES} bytes")
        return cls(name)
