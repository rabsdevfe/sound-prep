"""Downloader tests with an injected fake of the yt-dlp boundary (no network)."""

import importlib
import os
import ssl
import stat
import subprocess
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Any, Self, cast

import certifi
import pytest
import yt_dlp
from yt_dlp.utils import DownloadError

from sound_prep_core.adapters.downloader import YtDlpTrackDownloader
from sound_prep_core.adapters.ffmpeg import locate_ffmpeg
from sound_prep_core.domain.errors import DownloadFailedError

FFMPEG = Path("/fake/ffmpeg")


class FakeYoutubeDL:
    """Behaves like yt-dlp: writes ``<outtmpl with %(ext)s>`` files, may fail midway."""

    def __init__(
        self,
        opts: dict[str, Any],
        files: dict[str, bytes],
        fail: BaseException | None,
        info: dict[str, Any] | None,
    ):
        self.opts = opts
        self.files = files
        self.fail = fail
        self.info = info

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def extract_info(
        self, url: str, download: bool = True, process: bool = True
    ) -> dict[str, Any] | None:
        return self.info

    def process_ie_result(self, ie_result: dict[str, Any], download: bool = True) -> dict[str, Any]:
        # Resolve file names with the real yt-dlp, so hostile templates would show up here.
        with yt_dlp.YoutubeDL(cast(Any, self.opts)) as real:
            for ext, data in self.files.items():
                Path(real.prepare_filename({"id": "x", "title": "T", "ext": ext})).write_bytes(data)
        if self.fail is not None:
            raise self.fail
        return ie_result


def _downloader(
    files: dict[str, bytes],
    fail: BaseException | None = None,
    seen: list[dict[str, Any]] | None = None,
    info: dict[str, Any] | None = None,
) -> YtDlpTrackDownloader:
    def factory(opts: dict[str, Any]) -> FakeYoutubeDL:
        if seen is not None:
            seen.append(opts)
        return FakeYoutubeDL(opts, files, fail, {"_type": "video"} if info is None else info)

    return YtDlpTrackDownloader(FFMPEG, factory)


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_publishes_exactly_at_the_destination_and_cleans_up(tmp_path: Path) -> None:
    dest = tmp_path / "Song.mp3"
    # yt-dlp leaves the original download next to the converted file until it removes it.
    _downloader({"mp3": b"audio", "webm": b"original"}).download(
        "https://example.com/v", PurePosixPath(dest)
    )
    assert dest.read_bytes() == b"audio"
    assert _names(tmp_path) == ["Song.mp3"]


def test_title_with_dots_keeps_its_extension_handling(tmp_path: Path) -> None:
    dest = tmp_path / "Vol. 2 (live).mp3"
    _downloader({"mp3": b"audio"}).download("u", PurePosixPath(dest))
    assert _names(tmp_path) == ["Vol. 2 (live).mp3"]


def test_non_mp3_result_is_a_failure_and_leaves_nothing(tmp_path: Path) -> None:
    with pytest.raises(DownloadFailedError):
        _downloader({"webm": b"original"}).download("u", PurePosixPath(tmp_path / "Song.mp3"))
    assert _names(tmp_path) == []


def test_empty_mp3_is_a_failure(tmp_path: Path) -> None:
    with pytest.raises(DownloadFailedError):
        _downloader({"mp3": b""}).download("u", PurePosixPath(tmp_path / "Song.mp3"))
    assert _names(tmp_path) == []


def test_download_error_is_mapped_and_nothing_is_published(tmp_path: Path) -> None:
    downloader = _downloader({"part": b"half"}, fail=DownloadError("HTTP 403"))
    with pytest.raises(DownloadFailedError, match="403"):
        downloader.download("u", PurePosixPath(tmp_path / "Song.mp3"))
    assert _names(tmp_path) == []


def test_interruption_leaves_nothing_and_propagates(tmp_path: Path) -> None:
    with pytest.raises(KeyboardInterrupt):
        _downloader({"part": b"half"}, fail=KeyboardInterrupt()).download(
            "u", PurePosixPath(tmp_path / "Song.mp3")
        )
    assert _names(tmp_path) == []


def test_failure_keeps_a_previous_file_untouched(tmp_path: Path) -> None:
    dest = tmp_path / "Song.mp3"
    dest.write_bytes(b"previous")
    with pytest.raises(DownloadFailedError):
        _downloader({}, fail=DownloadError("boom")).download("u", PurePosixPath(dest))
    assert dest.read_bytes() == b"previous"
    assert _names(tmp_path) == ["Song.mp3"]


def test_unwritable_destination_folder_is_a_download_failure(tmp_path: Path) -> None:
    with pytest.raises(DownloadFailedError):
        _downloader({"mp3": b"a"}).download("u", PurePosixPath(tmp_path / "missing" / "Song.mp3"))


def test_pure_playlist_is_rejected_and_nothing_is_downloaded(tmp_path: Path) -> None:
    playlist = {"_type": "playlist", "entries": [{}, {}]}
    with pytest.raises(DownloadFailedError, match="playlist"):
        _downloader({"mp3": b"a"}, info=playlist).download(
            "https://youtube.com/playlist?list=x", PurePosixPath(tmp_path / "Song.mp3")
        )
    assert _names(tmp_path) == []


def test_unresolvable_url_is_a_failure(tmp_path: Path) -> None:
    downloader = YtDlpTrackDownloader(FFMPEG, lambda opts: FakeYoutubeDL(opts, {}, None, None))
    with pytest.raises(DownloadFailedError):
        downloader.download("u", PurePosixPath(tmp_path / "Song.mp3"))


def test_options_pin_ffmpeg_single_video_mp3_and_isolation(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    _downloader({"mp3": b"a"}, seen=seen).download("u", PurePosixPath(tmp_path / "Song.mp3"))
    opts = seen[0]
    assert opts["ffmpeg_location"] == str(FFMPEG)
    assert opts["noplaylist"] is True and opts["playlist_items"] == "1"
    assert opts["postprocessors"][0]["preferredcodec"] == "mp3"
    assert opts["quiet"] is True and "logger" in opts and opts["consoletitle"] is False
    assert opts["cachedir"] is False
    assert opts["cookiefile"] is None and opts["cookiesfrombrowser"] is None
    assert opts["nocheckcertificate"] is False


def test_real_yt_dlp_accepts_the_options_and_verifies_with_certifi(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    _downloader({"mp3": b"a"}, seen=seen).download("u", PurePosixPath(tmp_path / "Song.mp3"))
    # certifi must be importable, or yt-dlp falls back to the system store (missing when frozen).
    assert Path(certifi.where()).is_file()
    assert importlib.import_module("yt_dlp.dependencies").certifi is not None
    with yt_dlp.YoutubeDL(cast(Any, seen[0])) as ydl:
        assert cast(Any, ydl.params)["cachedir"] is False
        assert not ydl.cache.enabled
        assert ydl.params["nocheckcertificate"] is False


def test_published_file_follows_the_umask(tmp_path: Path) -> None:
    dest = tmp_path / "Song.mp3"
    previous = os.umask(0o022)
    try:
        _downloader({"mp3": b"a"}).download("u", PurePosixPath(dest))
    finally:
        os.umask(previous)
    assert stat.S_IMODE(dest.stat().st_mode) == 0o644


def test_prints_nothing(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    _downloader({"mp3": b"a"}).download("u", PurePosixPath(tmp_path / "Song.mp3"))
    captured = capfd.readouterr()
    assert captured.out == "" and captured.err == ""


@pytest.mark.network
def test_real_download_of_a_short_public_video(tmp_path: Path) -> None:
    ffmpeg = locate_ffmpeg(
        candidates=[
            Path(p)
            for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg")
        ]
    )
    dest = tmp_path / "Zoo.mp3"
    previous = os.umask(0o022)
    try:
        YtDlpTrackDownloader(ffmpeg).download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", PurePosixPath(dest)
        )
    finally:
        os.umask(previous)
    assert stat.S_IMODE(dest.stat().st_mode) == 0o644
    probe = subprocess.run([str(ffmpeg), "-i", str(dest)], capture_output=True, text=True)
    assert "Audio: mp3" in probe.stderr
    assert _names(tmp_path) == ["Zoo.mp3"]


HOSTILE = ["Vol $HOME x", "a%(title)s", "100% $PATH ~ %(id)s", "$$ ${HOME}"]


@pytest.mark.parametrize("name", HOSTILE)
def test_hostile_titles_in_the_destination_do_not_reach_yt_dlp_templates(
    tmp_path: Path, name: str
) -> None:
    folder = tmp_path / name
    folder.mkdir()
    dest = folder / f"{name}.mp3"
    seen: list[dict[str, Any]] = []
    _downloader({"mp3": b"audio", "webm": b"x"}, seen=seen).download("u", PurePosixPath(dest))
    assert _names(folder) == [dest.name]
    assert _names(tmp_path) == [name]
    assert dest.read_bytes() == b"audio"
    # Nothing user-derived is in what yt-dlp templates, and the staging area is removed.
    assert name not in str(seen[0]["paths"]) + str(seen[0]["outtmpl"])
    assert not Path(seen[0]["paths"]["home"]).exists()


@pytest.mark.parametrize("error", [ValueError("x"), KeyError("k"), AttributeError("a")])
def test_any_exception_is_mapped_keeping_the_cause(tmp_path: Path, error: Exception) -> None:
    with pytest.raises(DownloadFailedError) as raised:
        _downloader({"part": b"h"}, fail=error).download("u", PurePosixPath(tmp_path / "S.mp3"))
    assert raised.value.__cause__ is error
    assert _names(tmp_path) == []


def test_system_exit_propagates_and_cleans_up(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        _downloader({"part": b"h"}, fail=SystemExit(1)).download(
            "u", PurePosixPath(tmp_path / "S.mp3")
        )
    assert _names(tmp_path) == []


def test_yt_dlp_ssl_context_loads_the_certifi_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[object] = []
    original = ssl.SSLContext.load_verify_locations

    def spy(self: ssl.SSLContext, *args: Any, **kwargs: Any) -> None:
        loaded.append(kwargs.get("cafile"))
        original(self, *args, **kwargs)

    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", spy)
    helper = importlib.import_module("yt_dlp.networking._helper")
    context = helper.make_ssl_context(verify=True)
    assert certifi.where() in loaded
    assert context.verify_mode == ssl.CERT_REQUIRED
