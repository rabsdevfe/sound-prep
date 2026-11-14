"""Output layout: ``<dir>/<title>/<title>.mp3`` and ``<dir>/<title>/<start>_<end>.mp3``."""

from dataclasses import dataclass
from pathlib import PurePosixPath

from sound_prep_core.domain.errors import InvalidTitleError, OutputDirUnavailableError
from sound_prep_core.domain.time_range import TimeRange
from sound_prep_core.domain.title import Title


@dataclass(frozen=True, slots=True)
class OutputLayout:
    folder: PurePosixPath
    full_track: PurePosixPath
    clip: PurePosixPath

    @classmethod
    def compute(cls, output_dir: str, title: Title, time_range: TimeRange) -> "OutputLayout":
        base = PurePosixPath(output_dir)
        if not base.is_absolute() or ".." in base.parts:
            raise OutputDirUnavailableError(f"Output directory must be absolute: {output_dir!r}")
        folder = base / title.name
        full_track = folder / f"{title.name}.mp3"
        clip = folder / f"{time_range.file_stem}.mp3"
        if clip == full_track:
            # Cutting the clip would overwrite the full track, which must never happen.
            raise InvalidTitleError(f"Title {title.name!r} collides with the clip file name")
        return cls(folder=folder, full_track=full_track, clip=clip)
