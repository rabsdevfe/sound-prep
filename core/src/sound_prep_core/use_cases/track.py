"""Steps shared by the use cases: URL validation, port-error mapping and the download step."""

import unicodedata
from collections.abc import Callable
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from sound_prep_core.domain.errors import (
    DomainError,
    DownloadFailedError,
    InvalidUrlError,
    OutputDirUnavailableError,
)
from sound_prep_core.domain.ports import FileSystem, ProgressStage, TrackDownloader
from sound_prep_core.domain.title import FORBIDDEN_CATEGORIES


def validate_url(url: str) -> str:
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


def mapped[T](step: Callable[[], T], error: type[DomainError], what: str) -> T:
    """Run a port call; wrap anything that is not already a domain error, keeping the cause."""
    try:
        return step()
    except DomainError:
        raise
    except Exception as exc:
        raise error(f"{what}: {exc}") from exc


def exists(fs: FileSystem, path: PurePosixPath) -> bool:
    return mapped(lambda: fs.exists(path), OutputDirUnavailableError, "Filesystem")


def ensure_track(
    downloader: TrackDownloader,
    fs: FileSystem,
    report: Callable[[ProgressStage], None],
    url: str,
    track: PurePosixPath,
) -> None:
    """Download ``track`` unless it already exists; it is never deleted or overwritten."""
    if exists(fs, track):
        return
    report(ProgressStage.DOWNLOADING)
    mapped(lambda: downloader.download(url, track), DownloadFailedError, "Download failed")
    if not exists(fs, track):
        raise DownloadFailedError(f"Download did not produce {track.name!r}")
