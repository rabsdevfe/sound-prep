"""Use case: download a track (unless already present) and cut a clip from it."""

import contextlib
from dataclasses import dataclass

from sound_prep_core.domain.errors import (
    CutFailedError,
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
from sound_prep_core.domain.title import Title
from sound_prep_core.use_cases.track import ensure_track, mapped, validate_url


@dataclass(frozen=True, slots=True)
class PrepareClipRequest:
    url: str
    title: str
    output_dir: str
    start: str
    end: str


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

    def execute(self, request: PrepareClipRequest) -> OutputLayout:
        # Validate everything before touching the filesystem.
        time_range = TimeRange.parse(request.start, request.end)
        title = Title(request.title)
        url = validate_url(request.url)
        layout = OutputLayout.compute(request.output_dir, title, time_range)
        fs = self._fs

        mapped(lambda: fs.make_dir(layout.folder), OutputDirUnavailableError, "Filesystem")
        ensure_track(self._downloader, fs, self._report, url, layout.full_track)

        self._report(ProgressStage.CUTTING)
        before = mapped(lambda: fs.stamp(layout.clip), OutputDirUnavailableError, "Filesystem")
        mapped(
            lambda: self._cutter.cut(layout.full_track, layout.clip, time_range),
            CutFailedError,
            "Cut failed",
        )
        after = mapped(lambda: fs.stamp(layout.clip), OutputDirUnavailableError, "Filesystem")
        if after is None or after == before:
            raise CutFailedError(f"Cut did not write {layout.clip.name!r}")
        return layout
