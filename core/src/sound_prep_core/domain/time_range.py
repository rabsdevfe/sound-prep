"""Clip times and ranges, using the time grammar of the IPC contract (``ClipTime``)."""

import re
from dataclasses import dataclass

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

    ``text`` is kept as typed because the clip filename uses it.
    """

    text: str
    seconds: int

    @classmethod
    def parse(cls, text: str) -> "ClipTime":
        if len(text) > _MAX_TEXT_LENGTH or not _CLIP_TIME.fullmatch(text):
            raise InvalidTimeRangeError(f"Invalid time {text!r}: use SS, MM:SS or HH:MM:SS")
        seconds = 0
        for field in text.split(":"):
            seconds = seconds * 60 + int(field)
        if seconds > MAX_SECONDS:
            raise InvalidTimeRangeError(f"Time {text!r} is beyond the 24 hour limit")
        return cls(text=text, seconds=seconds)


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
