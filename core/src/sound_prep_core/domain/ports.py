"""Ports: what the use cases need from the outside world. Adapters implement them.

Implementations signal failure with the domain errors documented on each method. The use cases
also map any other exception a port raises (``OSError``, adapter-specific errors) to the error of
the failing step, keeping the cause.

Publication is atomic: a file is written under a temporary name in the destination folder and
renamed into place only on success, so the final name never holds a partial file. Temporary files
are never treated as the track or the clip.
"""

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Protocol

from sound_prep_core.domain.time_range import TimeRange


class ProgressStage(StrEnum):
    """Values match the ``stage`` of the IPC progress event."""

    DOWNLOADING = "downloading"
    CUTTING = "cutting"


class TrackDownloader(Protocol):
    def download(self, url: str, destination: PurePosixPath) -> None:
        """Download the track as MP3 to ``destination``. Raises ``DownloadFailedError``.

        Must publish atomically (temporary name, then rename on success): an interrupted download
        must leave nothing at ``destination``, because an existing track is reused as complete.
        The adapter must publish exactly at ``destination``: a tool such as yt-dlp that appends its
        own extension to the output name must be configured or post-processed to end up there.
        """
        ...


class ClipCutter(Protocol):
    def cut(self, source: PurePosixPath, destination: PurePosixPath, time_range: TimeRange) -> None:
        """Write the clip to ``destination``, replacing it. Raises ``CutFailedError``.

        Must publish atomically (temporary name, then rename over any existing clip on success) and
        must never write to ``source``. It must raise rather than succeed without writing.
        """
        ...


class FileSystem(Protocol):
    """Deliberately has no delete or overwrite operation: the full track is never removed."""

    def exists(self, path: PurePosixPath) -> bool: ...

    def stamp(self, path: PurePosixPath) -> int | None:
        """Modification time in nanoseconds, or ``None`` when ``path`` does not exist.

        Lets the use case notice that a cutter left a stale clip untouched. It relies on the
        filesystem's timestamp resolution: an atomic rename of a freshly written file gets a new
        stamp on APFS (nanosecond resolution).
        """
        ...

    def make_dir(self, path: PurePosixPath) -> None:
        """Create the directory and its parents if missing. Raises ``OutputDirUnavailableError``."""
        ...


class ProgressReporter(Protocol):
    def report(self, stage: ProgressStage) -> None:
        """Best effort: the use case ignores any exception raised here and carries on."""
        ...
