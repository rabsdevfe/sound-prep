"""Use case: download a track (unless already present) and cut a clip from it."""

import contextlib
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from sound_prep_core.domain.errors import (
    CutFailedError,
    DomainError,
    DownloadFailedError,
    InvalidUrlError,
    OutputDirUnavailableError,
)
from sound_prep_core.domain.layout import OutputLayout
from sound_prep_core.domain.ports import (
    ClipCutter,
    FileSystem,
    ProgressReporter,
    ProgressStage,
    TrackDownloader,
)
from sound_prep_core.domain.time_range import TimeRange
from sound_prep_core.domain.title import FORBIDDEN_CATEGORIES, Title


@dataclass(frozen=True, slots=True)
class PrepareClipRequest:
    url: str
    title: str
    output_dir: str
    start: str
    end: str


def _validate_url(url: str) -> str:
    bad_char = any(ch.isspace() or unicodedata.category(ch) in FORBIDDEN_CATEGORIES for ch in url)
    try:
        if bad_char:
            raise ValueError("forbidden character")
        parts = urlsplit(url)  # raises ValueError on e.g. unbalanced brackets or invalid hosts
        port = parts.port  # raises ValueError outside 0-65535 or when not numeric
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("scheme or host")
        if port == 0:
            raise ValueError("port")
    except ValueError as exc:
        raise InvalidUrlError(f"Invalid URL: {url!r}") from exc
    return url


def _mapped[T](step: Callable[[], T], error: type[DomainError], what: str) -> T:
    """Run a port call; wrap anything that is not already a domain error, keeping the cause."""
    try:
        return step()
    except DomainError:
        raise
    except Exception as exc:
        raise error(f"{what}: {exc}") from exc


class PrepareClip:
    """Validates the request, reuses an existing full track or downloads it, then cuts the clip.

    The full track is only ever created, never deleted or overwritten: it is downloaded when absent
    and otherwise left untouched. Only the clip is (re)cut. The track is keyed by output directory
    and title, not by URL: a different URL with the same title reuses the existing track.
    Ports publish files atomically (see ``ports``), so an existing track is complete. Non-domain
    exceptions from a port become the
    error of its step: download, ``download_failed``; cut, ``cut_failed``; filesystem,
    ``output_dir_unavailable``. A failing progress reporter never aborts the job.
    """

    def __init__(
        self,
        downloader: TrackDownloader,
        cutter: ClipCutter,
        filesystem: FileSystem,
        progress: ProgressReporter,
    ) -> None:
        self._downloader = downloader
        self._cutter = cutter
        self._fs = filesystem
        self._progress = progress

    def _report(self, stage: ProgressStage) -> None:
        with contextlib.suppress(Exception):
            self._progress.report(stage)

    def _exists(self, path: PurePosixPath) -> bool:
        return _mapped(lambda: self._fs.exists(path), OutputDirUnavailableError, "Filesystem")

    def execute(self, request: PrepareClipRequest) -> OutputLayout:
        # Validate everything before touching the filesystem.
        time_range = TimeRange.parse(request.start, request.end)
        title = Title(request.title)
        url = _validate_url(request.url)
        layout = OutputLayout.compute(request.output_dir, title, time_range)
        fs = self._fs

        _mapped(lambda: fs.make_dir(layout.folder), OutputDirUnavailableError, "Filesystem")
        if not self._exists(layout.full_track):
            self._report(ProgressStage.DOWNLOADING)
            _mapped(
                lambda: self._downloader.download(url, layout.full_track),
                DownloadFailedError,
                "Download failed",
            )
            if not self._exists(layout.full_track):
                raise DownloadFailedError(f"Download did not produce {layout.full_track.name!r}")

        self._report(ProgressStage.CUTTING)
        before = _mapped(lambda: fs.stamp(layout.clip), OutputDirUnavailableError, "Filesystem")
        _mapped(
            lambda: self._cutter.cut(layout.full_track, layout.clip, time_range),
            CutFailedError,
            "Cut failed",
        )
        after = _mapped(lambda: fs.stamp(layout.clip), OutputDirUnavailableError, "Filesystem")
        if after is None or after == before:
            raise CutFailedError(f"Cut did not write {layout.clip.name!r}")
        return layout
