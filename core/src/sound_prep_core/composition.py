"""Composition root: wires the real adapters into the prepare-clip use case.

ffmpeg is resolved lazily, the first time a download or a cut needs it, so a missing or broken
ffmpeg never stops the process at startup: the request fails with a clear ``download_failed`` or
``cut_failed`` message after validation, and later requests retry (the user may install it).
Per ADR 0001 PATH is never consulted: the ``SOUND_PREP_FFMPEG`` environment variable (an absolute
path) wins, otherwise the fixed Homebrew candidates are tried.
"""

from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from sound_prep_core.adapters.cutter import FfmpegClipCutter
from sound_prep_core.adapters.downloader import YoutubeDLFactory, YtDlpTrackDownloader
from sound_prep_core.adapters.ffmpeg import locate_ffmpeg
from sound_prep_core.adapters.filesystem import LocalFileSystem
from sound_prep_core.adapters.ipc.server import HandlerFactory, RequestHandler
from sound_prep_core.domain.ports import ProgressReporter
from sound_prep_core.domain.time_range import TimeRange
from sound_prep_core.use_cases.prepare_clip import PrepareClip

FFMPEG_ENV = "SOUND_PREP_FFMPEG"


class _FfmpegResolver:
    """Finds ffmpeg on first use and remembers it; failures are not cached."""

    def __init__(self, configured: Path | None) -> None:
        self._configured = configured
        self._found: Path | None = None

    def get(self) -> Path:
        if self._found is None:
            self._found = locate_ffmpeg(configured=self._configured)  # raises when unusable
        return self._found


class _LazyDownloader:
    def __init__(self, ffmpeg: _FfmpegResolver, youtube_dl: YoutubeDLFactory | None) -> None:
        self._ffmpeg = ffmpeg
        self._youtube_dl = youtube_dl

    def download(self, url: str, destination: PurePosixPath) -> None:
        ffmpeg = self._ffmpeg.get()
        if self._youtube_dl is None:
            downloader = YtDlpTrackDownloader(ffmpeg)
        else:
            downloader = YtDlpTrackDownloader(ffmpeg, self._youtube_dl)
        downloader.download(url, destination)


class _LazyCutter:
    def __init__(self, ffmpeg: _FfmpegResolver) -> None:
        self._ffmpeg = ffmpeg

    def cut(self, source: PurePosixPath, destination: PurePosixPath, time_range: TimeRange) -> None:
        FfmpegClipCutter(self._ffmpeg.get()).cut(source, destination, time_range)


def build_handler_factory(
    env: Mapping[str, str], youtube_dl: YoutubeDLFactory | None = None
) -> HandlerFactory:
    """Handler factory over the real adapters; ``youtube_dl`` is the seam tests replace."""
    configured = env.get(FFMPEG_ENV)
    resolver = _FfmpegResolver(Path(configured) if configured else None)
    downloader = _LazyDownloader(resolver, youtube_dl)
    cutter = _LazyCutter(resolver)
    filesystem = LocalFileSystem()

    def make(progress: ProgressReporter) -> RequestHandler:
        return PrepareClip(downloader, cutter, filesystem, progress)

    return make
