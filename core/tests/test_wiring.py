"""The composition root and the real entrypoint, with real ffmpeg and a faked yt-dlp boundary."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Self

import pytest
from jsonschema import Draft202012Validator

from sound_prep_core import composition
from sound_prep_core.adapters.ffmpeg import locate_ffmpeg
from sound_prep_core.adapters.ipc.server import serve
from sound_prep_core.composition import FFMPEG_ENV, build_handler_factory

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "core"
VALIDATOR = Draft202012Validator(json.loads((ROOT / "contracts" / "ipc.schema.json").read_text()))


def _system_ffmpeg() -> Path:
    # /usr/bin/ffmpeg exists for Linux CI only; the locator itself is tested with fakes.
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if Path(candidate).exists():
            return Path(candidate)
    pytest.fail("ffmpeg is required for these tests (CI installs it)")


@pytest.fixture(scope="module")
def ffmpeg() -> Path:
    return _system_ffmpeg()


def _make_mp3(ffmpeg: Path, path: Path, seconds: int = 10) -> Path:
    cmd = [str(ffmpeg), "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i"]
    cmd += [f"sine=frequency=440:duration={seconds}", "-c:a", "libmp3lame", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def _request(out: Path, request_id: str = "w1", **params: str) -> bytes:
    body = {
        "v": 1,
        "id": request_id,
        "type": "prepare_clip",
        "params": {
            "url": "https://youtu.be/abc",
            "title": "Song",
            "output_dir": str(out),
            "start": "2",
            "end": "5",
            **params,
        },
    }
    return json.dumps(body).encode() + b"\n"


def _messages(raw: bytes) -> list[dict[str, Any]]:
    messages = [json.loads(line) for line in raw.splitlines()]
    assert all(VALIDATOR.is_valid(m) for m in messages), messages
    return messages


class FakeYoutubeDL:
    """The downloader boundary: writes a real MP3 where yt-dlp's post-processing would."""

    source: Path
    calls: list[str] = []  # noqa: RUF012

    def __init__(self, opts: dict[str, Any]) -> None:
        self.staging = Path(opts["paths"]["home"])

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(
        self, url: str, download: bool = False, process: bool = False
    ) -> dict[str, Any]:
        FakeYoutubeDL.calls.append(url)
        return {"id": "abc"}

    def process_ie_result(self, info: dict[str, Any], download: bool = True) -> dict[str, Any]:
        (self.staging / "track.mp3").write_bytes(self.source.read_bytes())
        return info


def test_full_request_through_real_ffmpeg_with_the_downloader_faked(
    ffmpeg: Path, tmp_path: Path
) -> None:
    FakeYoutubeDL.source = _make_mp3(ffmpeg, tmp_path / "source.mp3")
    FakeYoutubeDL.calls = []
    out = tmp_path / "out"
    out.mkdir()
    factory = build_handler_factory({FFMPEG_ENV: str(ffmpeg)}, FakeYoutubeDL)
    sink = io.BytesIO()
    assert serve(io.BytesIO(_request(out)), sink, factory) == 0
    messages = _messages(sink.getvalue())
    assert [m["type"] for m in messages] == ["progress", "progress", "result"]
    assert [m["stage"] for m in messages[:2]] == ["downloading", "cutting"]
    assert messages[2]["clip"] == str(out / "Song" / "2_5.mp3")
    assert (out / "Song" / "Song.mp3").is_file()
    assert (out / "Song" / "2_5.mp3").stat().st_size > 0
    assert FakeYoutubeDL.calls == ["https://youtu.be/abc"]


def _last_error(factory: Any, tmp_path: Path, request_id: str = "x") -> dict[str, Any]:
    sink = io.BytesIO()
    assert serve(io.BytesIO(_request(tmp_path, request_id)), sink, factory) == 0
    last = _messages(sink.getvalue())[-1]
    assert (last["id"], last["type"], last["code"]) == (request_id, "error", "download_failed")
    return last


def test_ffmpeg_not_found_is_a_clear_download_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real = locate_ffmpeg
    monkeypatch.setattr(
        composition,
        "locate_ffmpeg",
        lambda configured=None: real(configured, candidates=[Path("/nonexistent/ffmpeg")]),
    )
    last = _last_error(build_handler_factory({}, FakeYoutubeDL), tmp_path)
    assert last["message"].startswith(
        "Download failed: ffmpeg not found (tried /nonexistent/ffmpeg"
    )
    assert "configure a path" in last["message"]


def test_ffmpeg_configured_but_missing_is_a_clear_download_error(tmp_path: Path) -> None:
    factory = build_handler_factory({FFMPEG_ENV: "/nonexistent/ffmpeg"}, FakeYoutubeDL)
    message = _last_error(factory, tmp_path)["message"]
    assert message.startswith("Download failed: Configured ffmpeg is unusable: /nonexistent/ffmpeg")


def test_ffmpeg_unusable_binary_is_a_clear_download_error(tmp_path: Path) -> None:
    fake = tmp_path / "ffmpeg"
    fake.write_text("#!/bin/sh\necho not ffmpeg\n")
    fake.chmod(0o755)
    message = _last_error(build_handler_factory({FFMPEG_ENV: str(fake)}, FakeYoutubeDL), tmp_path)
    assert f"{fake} is not a working ffmpeg" in message["message"]


def test_missing_ffmpeg_keeps_the_loop_serving(tmp_path: Path) -> None:
    factory = build_handler_factory({FFMPEG_ENV: "/nonexistent/ffmpeg"}, FakeYoutubeDL)
    data = (
        _request(tmp_path, "a") + _request(tmp_path, "b", url="ftp://x") + _request(tmp_path, "c")
    )
    sink = io.BytesIO()
    assert serve(io.BytesIO(data), sink, factory) == 0
    messages = _messages(sink.getvalue())
    terminals = [(m["id"], m["code"]) for m in messages if m["type"] == "error"]
    assert terminals == [("a", "download_failed"), ("b", "invalid_url"), ("c", "download_failed")]


def test_ffmpeg_resolution_is_retried_after_a_failure(ffmpeg: Path, tmp_path: Path) -> None:
    link = tmp_path / "ffmpeg-link"
    factory = build_handler_factory({FFMPEG_ENV: str(link)}, FakeYoutubeDL)
    FakeYoutubeDL.source = _make_mp3(ffmpeg, tmp_path / "source.mp3")
    out = tmp_path / "out"
    out.mkdir()
    sink = io.BytesIO()
    serve(io.BytesIO(_request(out, "first")), sink, factory)
    assert _messages(sink.getvalue())[-1]["code"] == "download_failed"
    link.symlink_to(ffmpeg)
    sink = io.BytesIO()
    serve(io.BytesIO(_request(out, "second")), sink, factory)
    assert _messages(sink.getvalue())[-1]["type"] == "result"


def test_relative_ffmpeg_path_is_refused(tmp_path: Path) -> None:
    factory = build_handler_factory({FFMPEG_ENV: "ffmpeg"}, FakeYoutubeDL)
    sink = io.BytesIO()
    serve(io.BytesIO(_request(tmp_path)), sink, factory)
    last = _messages(sink.getvalue())[-1]
    assert last["code"] == "download_failed"
    assert "absolute" in last["message"]


def test_real_entrypoint_cuts_a_clip_from_an_existing_track(ffmpeg: Path, tmp_path: Path) -> None:
    # No network: the full track is already in place, so the downloader is never called.
    folder = tmp_path / "out" / "Song"
    folder.mkdir(parents=True)
    _make_mp3(ffmpeg, folder / "Song.mp3")
    result = subprocess.run(
        [sys.executable, "-m", "sound_prep_core"],
        input=_request(tmp_path / "out"),
        capture_output=True,
        timeout=120,
        cwd="/",
        env={**os.environ, FFMPEG_ENV: str(ffmpeg), "PYTHONPATH": str(CORE / "src")},
        check=False,
    )
    assert result.returncode == 0
    messages = _messages(result.stdout)
    assert [m["type"] for m in messages] == ["progress", "result"]
    assert (folder / "2_5.mp3").stat().st_size > 0
