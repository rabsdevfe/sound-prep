"""Clip times and ranges, using the time grammar of the IPC contract (``ClipTime``).

Out of scope on purpose: constructors do no runtime type checks (inputs are typed and mypy runs in
strict mode; runtime input arrives through the contract models).
"""

import re
from dataclasses import dataclass, field

from sound_prep_core.domain.errors import InvalidTimeRangeError

# Same grammar as the contract: SS, MM:SS or HH:MM:SS. Only the leading field is unbounded.
# Explicit [0-9] (not \d) so non-ASCII digits are rejected; fullmatch so a trailing newline is too.
_CLIP_TIME = re.compile(r"[0-9]+|[0-9]+:[0-5][0-9]|[0-9]+:[0-5][0-9]:[0-5][0-9]")


# Domain rule, stricter than the contract (which bounds nothing): a track is at most 24 hours long.
# It also keeps int() far from Python's digit limit, so no input can escape as a ValueError.
MAX_SECONDS = 24 * 3600
_MAX_TEXT_LENGTH = 32


@dataclass(frozen=True, slots=True)
class ClipTime:
    """A moment in the track, from 0 up to ``MAX_SECONDS`` (24 hours).

    ``text`` is kept as typed because the clip filename uses it. Construction validates it, so
    an invalid ``ClipTime`` cannot exist; ``seconds`` is derived.
    """

    text: str
    seconds: int = field(init=False)

    def __post_init__(self) -> None:
        text = self.text
        if len(text) > _MAX_TEXT_LENGTH or not _CLIP_TIME.fullmatch(text):
            raise InvalidTimeRangeError(f"Invalid time {text!r}: use SS, MM:SS or HH:MM:SS")
        seconds = 0
        for part in text.split(":"):
            seconds = seconds * 60 + int(part)
        if seconds > MAX_SECONDS:
            raise InvalidTimeRangeError(f"Time {text!r} is beyond the 24 hour limit")
        object.__setattr__(self, "seconds", seconds)

    @classmethod
    def parse(cls, text: str) -> "ClipTime":
        # Alias of the constructor, kept for call-site clarity and symmetry with TimeRange.parse.
        return cls(text)


@dataclass(frozen=True, slots=True)
class TimeRange:
    start: ClipTime
    end: ClipTime

    def __post_init__(self) -> None:
        if self.end.seconds <= self.start.seconds:
            raise InvalidTimeRangeError(
                f"End {self.end.text!r} must be after start {self.start.text!r}"
            )

    @classmethod
    def parse(cls, start: str, end: str) -> "TimeRange":
        return cls(ClipTime.parse(start), ClipTime.parse(end))

    @property
    def duration_seconds(self) -> int:
        return self.end.seconds - self.start.seconds

    @property
    def file_stem(self) -> str:
        """Clip file name without extension, e.g. ``1-30_2-15`` for 1:30 to 2:15."""
        return f"{self.start.text.replace(':', '-')}_{self.end.text.replace(':', '-')}"
