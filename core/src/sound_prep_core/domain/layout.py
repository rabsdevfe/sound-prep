"""Output layouts: ``<dir>/<title>/<title>.mp3``, the clip ``<start>_<end>.mp3`` or ``stems/``.

Out of scope on purpose, shared with ``title``: constructors do no runtime type checks (inputs are
typed and mypy runs in strict mode; runtime input arrives through the contract models), and
unassigned or private-use characters and directory length are left to the filesystem.
"""

import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

from sound_prep_core.domain.errors import InvalidTitleError, OutputDirUnavailableError
from sound_prep_core.domain.stems import Stem
from sound_prep_core.domain.time_range import TimeRange
from sound_prep_core.domain.title import FORBIDDEN_CATEGORIES, Title


def _validated_folder(folder: PurePosixPath) -> PurePosixPath:
    """NFC-normalize ``folder`` and check it is an absolute path ending in a valid title."""
    text = unicodedata.normalize("NFC", str(folder))
    if any(unicodedata.category(ch) in FORBIDDEN_CATEGORIES for ch in text):
        raise OutputDirUnavailableError(
            "Output directory contains control or invisible formatting characters"
        )
    folder = PurePosixPath(text)
    if not folder.is_absolute():
        raise OutputDirUnavailableError(f"Output directory must be absolute: {text!r}")
    if ".." in folder.parts:
        raise OutputDirUnavailableError(f"Output directory must not contain '..': {text!r}")
    try:
        valid_name = Title(folder.name).name == folder.name
    except InvalidTitleError:
        valid_name = False
    if not valid_name:
        raise OutputDirUnavailableError(f"Output folder has no valid title name: {text!r}")
    return folder


@dataclass(frozen=True, slots=True)
class StemsLayout:
    """``<dir>/<title>/<title>.mp3`` and the stems under ``<dir>/<title>/stems/``."""

    folder: PurePosixPath

    def __post_init__(self) -> None:
        object.__setattr__(self, "folder", _validated_folder(self.folder))

    @property
    def full_track(self) -> PurePosixPath:
        return self.folder / f"{self.folder.name}.mp3"

    @property
    def stems_dir(self) -> PurePosixPath:
        return self.folder / "stems"

    def stem(self, stem: Stem) -> PurePosixPath:
        return self.stems_dir / stem.filename

    @classmethod
    def compute(cls, output_dir: str, title: Title) -> "StemsLayout":
        return cls(PurePosixPath(unicodedata.normalize("NFC", output_dir)) / title.name)


@dataclass(frozen=True, slots=True)
class OutputLayout:
    """The output paths of one request, derived from the folder and the time range.

    ``folder`` is ``<output_dir>/<title>``. The file paths are computed from it, so an invalid file
    name cannot be constructed. Construction NFC-normalizes the folder and validates it: absolute,
    no ``..``, no control or invisible characters, and a last component that is a valid title.
    """

    folder: PurePosixPath
    time_range: TimeRange

    def __post_init__(self) -> None:
        folder = _validated_folder(self.folder)
        object.__setattr__(self, "folder", folder)
        if self.clip == self.full_track:
            # The title is what makes the clip name equal the track name, hence a title error.
            # Cutting the clip would overwrite the full track, which must never happen.
            raise InvalidTitleError(f"Title {folder.name!r} collides with the clip file name")

    @property
    def full_track(self) -> PurePosixPath:
        return self.folder / f"{self.folder.name}.mp3"

    @property
    def clip(self) -> PurePosixPath:
        return self.folder / f"{self.time_range.file_stem}.mp3"

    @classmethod
    def compute(cls, output_dir: str, title: Title, time_range: TimeRange) -> "OutputLayout":
        text = unicodedata.normalize("NFC", output_dir)
        return cls(PurePosixPath(text) / title.name, time_range)
