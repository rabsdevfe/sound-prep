"""The stems a track is separated into: the file names of the ``stems`` folder."""

from enum import StrEnum


class Stem(StrEnum):
    DRUMS = "drums"
    BASS = "bass"
    VOCALS = "vocals"
    GUITAR = "guitar"
    OTHER = "other"

    @property
    def filename(self) -> str:
        return f"{self.value}.wav"
