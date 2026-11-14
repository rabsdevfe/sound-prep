"""``TrackDownloader`` backed by yt-dlp used as a library."""

import os
import secrets
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Any, Protocol, Self, cast

import yt_dlp

from sound_prep_core.domain.errors import DownloadFailedError

_STAGED_STEM = "track"


class YoutubeDLLike(Protocol):
    """The slice of ``yt_dlp.YoutubeDL`` used here: the seam tests replace with a fake."""

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> object: ...

    def extract_info(
        self, url: str, download: bool = ..., process: bool = ...
    ) -> dict[str, Any] | None: ...

    def process_ie_result(
        self, ie_result: dict[str, Any], download: bool = ...
    ) -> dict[str, Any]: ...


YoutubeDLFactory = Callable[[dict[str, Any]], YoutubeDLLike]


def _real_youtube_dl(opts: dict[str, Any]) -> YoutubeDLLike:
    return cast(YoutubeDLLike, yt_dlp.YoutubeDL(cast(Any, opts)))


class _SilentLogger:
    """Keeps yt-dlp from printing: stdout will carry the IPC protocol."""

    def debug(self, msg: str) -> None: ...

    def info(self, msg: str) -> None: ...

    def warning(self, msg: str) -> None: ...

    def error(self, msg: str) -> None: ...


_COLLECTION_TYPES = ("playlist", "multi_video")


def _require_single_video(info: dict[str, Any] | None) -> None:
    if info is None:
        raise DownloadFailedError("No video found at that URL")
    if info.get("_type") in _COLLECTION_TYPES:
        raise DownloadFailedError("The URL is a playlist; provide the URL of a single video")


class YtDlpTrackDownloader:
    def __init__(self, ffmpeg: Path, youtube_dl: YoutubeDLFactory = _real_youtube_dl) -> None:
        self._ffmpeg = ffmpeg
        self._youtube_dl = youtube_dl

    def _options(self, staging: Path) -> dict[str, Any]:
        # yt-dlp expands `$VAR`, `~` and `%(field)s` in output templates and paths, so nothing
        # derived from the user's title or folder may reach them: `staging` is a neutral
        # temporary directory and the template is a constant.
        return {
            "format": "bestaudio/best",
            # One video per request: a watch URL with a list parameter is the single video, and
            # download() additionally rejects pure playlists and caps any playlist at one item.
            "noplaylist": True,
            "playlist_items": "1",
            "paths": {"home": str(staging)},
            "outtmpl": f"{_STAGED_STEM}.%(ext)s",
            "ffmpeg_location": str(self._ffmpeg),
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}
            ],
            "logger": _SilentLogger(),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "consoletitle": False,
            # Isolated from the user's environment: no cache dir, no cookies. Certificates are
            # verified against the certifi bundle (a dependency; yt-dlp picks it up on import).
            "cachedir": False,
            "cookiefile": None,
            "cookiesfrombrowser": None,
            "nocheckcertificate": False,
            "color": {"stdout": "never", "stderr": "never"},
        }

    def download(self, url: str, destination: PurePosixPath) -> None:
        dest = Path(destination)
        staging: Path | None = None
        temp: Path | None = None
        try:
            # Everything yt-dlp and ffmpeg write stays in a private staging folder under the
            # system temporary directory, so a failure leaves nothing next to the destination.
            staging = Path(tempfile.mkdtemp(prefix="sound-prep-dl-"))
            with self._youtube_dl(self._options(staging)) as ydl:
                info = ydl.extract_info(url, download=False, process=False)
                _require_single_video(info)
                assert info is not None
                _require_single_video(ydl.process_ie_result(info, download=True))
            produced = staging / f"{_STAGED_STEM}.mp3"
            if not produced.is_file() or produced.stat().st_size == 0:
                raise DownloadFailedError("The download produced no MP3 file")
            # Copy into the destination folder, then rename: the rename is atomic only within one
            # filesystem. O_CREAT with 0o666 lets the umask decide the permissions, like the
            # reference script's output.
            temp = dest.parent / f".{secrets.token_hex(8)}.tmp"
            fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
            with os.fdopen(fd, "wb") as out, produced.open("rb") as source:
                shutil.copyfileobj(source, out)
            temp.replace(dest)
            temp = None
        except DownloadFailedError:
            raise
        except Exception as error:  # yt-dlp and its extractors raise many unrelated types
            raise DownloadFailedError(f"Download failed: {error}") from error
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
