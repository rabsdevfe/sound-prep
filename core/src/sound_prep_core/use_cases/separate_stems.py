"""Use case: download a track (unless already present) and separate it into stems."""

import contextlib
from dataclasses import dataclass

from sound_prep_core.domain.errors import OutputDirUnavailableError, SeparationFailedError
from sound_prep_core.domain.layout import StemsLayout
from sound_prep_core.domain.ports import (
    FileSystem,
    ProgressReporter,
    ProgressStage,
    StemSeparator,
    TrackDownloader,
)
from sound_prep_core.domain.stems import Stem
from sound_prep_core.domain.title import Title
from sound_prep_core.use_cases.track import ensure_track, mapped, validate_url


@dataclass(frozen=True, slots=True)
class SeparateStemsRequest:
    url: str
    title: str
    output_dir: str


class SeparateStems:
    """Reuses or downloads the full track as ``PrepareClip`` does, then writes the five stems.

    Re-running replaces the stems. Non-domain exceptions from the separator become
    ``separation_failed``. The ``stems`` folder may exist, empty, after a failure. Succeeds only
    when every stem file was written (its timestamp changed) by the separation.
    A failing progress reporter never aborts the job.
    """

    def __init__(
        self,
        downloader: TrackDownloader,
        separator: StemSeparator,
        filesystem: FileSystem,
        progress: ProgressReporter,
    ) -> None:
        self._downloader = downloader
        self._separator = separator
        self._fs = filesystem
        self._progress = progress

    def _report(self, stage: ProgressStage, percent: int | None = None) -> None:
        with contextlib.suppress(Exception):
            self._progress.report(stage, percent)

    def _stamps(self, layout: StemsLayout) -> dict[Stem, int | None]:
        def stamp(stem: Stem) -> int | None:
            return mapped(
                lambda: self._fs.stamp(layout.stem(stem)), OutputDirUnavailableError, "Filesystem"
            )

        return {stem: stamp(stem) for stem in Stem}

    def execute(self, request: SeparateStemsRequest) -> StemsLayout:
        title = Title(request.title)
        url = validate_url(request.url)
        layout = StemsLayout.compute(request.output_dir, title)
        fs = self._fs

        mapped(lambda: fs.make_dir(layout.folder), OutputDirUnavailableError, "Filesystem")
        ensure_track(self._downloader, fs, self._report, url, layout.full_track)

        self._report(ProgressStage.SEPARATING)
        before = self._stamps(layout)
        mapped(
            lambda: self._separator.separate(
                layout.full_track,
                layout.stems_dir,
                lambda percent: self._report(ProgressStage.SEPARATING, percent),
            ),
            SeparationFailedError,
            "Separation failed",
        )
        after = self._stamps(layout)
        stale = [s.value for s in Stem if after[s] is None or after[s] == before[s]]
        if stale:  # a missing stem, or a previous run's stem the separator left untouched
            raise SeparationFailedError(f"Separation did not write: {', '.join(stale)}")
        return layout
