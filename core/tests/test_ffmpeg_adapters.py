"""Adapter tests that run the REAL ffmpeg on generated audio (no skips: CI installs ffmpeg)."""

import hashlib
import os
import stat
import subprocess
from pathlib import Path, PurePosixPath

import pytest

from sound_prep_core.adapters.cutter import FfmpegClipCutter
from sound_prep_core.adapters.ffmpeg import FfmpegUnavailableError, locate_ffmpeg
from sound_prep_core.adapters.filesystem import LocalFileSystem
from sound_prep_core.domain.errors import CutFailedError, OutputDirUnavailableError
from sound_prep_core.domain.time_range import TimeRange


@pytest.fixture(scope="session")
def ffmpeg() -> Path:
    return locate_ffmpeg(configured=_system_ffmpeg())


def _system_ffmpeg() -> Path | None:
    # The /usr/bin fallback exists only for Linux CI (apt installs there), so CI does not
    # exercise the macOS default candidates; those are covered by the locator tests with fakes.
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if Path(candidate).exists():
            return Path(candidate)
    return None


def _make_source(ffmpeg: Path, path: Path, seconds: int = 10) -> Path:
    subprocess.run(
        [
            str(ffmpeg),
            "-nostdin",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:a",
            "libmp3lame",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _duration(ffmpeg: Path, path: Path) -> float:
    out = subprocess.run(
        [str(ffmpeg), "-i", str(path), "-f", "null", "-"], capture_output=True, text=True
    ).stderr.replace("\r", "\n")
    last = [line for line in out.split("\n") if "time=" in line][-1]
    h, m, s = last.split("time=")[1].split()[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _posix(path: Path) -> PurePosixPath:
    return PurePosixPath(path)


def test_cut_has_the_requested_duration(ffmpeg: Path, tmp_path: Path) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3")
    clip = tmp_path / "clip.mp3"
    FfmpegClipCutter(ffmpeg).cut(_posix(source), _posix(clip), TimeRange.parse("2", "5"))
    assert _duration(ffmpeg, clip) == pytest.approx(3, abs=0.2)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clip.mp3", "full.mp3"]


def test_cut_leaves_the_source_untouched(ffmpeg: Path, tmp_path: Path) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3")
    before = (_sha(source), source.stat().st_mtime_ns)
    FfmpegClipCutter(ffmpeg).cut(
        _posix(source), _posix(tmp_path / "clip.mp3"), TimeRange.parse("1", "3")
    )
    assert (_sha(source), source.stat().st_mtime_ns) == before


def test_cut_replaces_an_existing_clip(ffmpeg: Path, tmp_path: Path) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3")
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(b"old")
    FfmpegClipCutter(ffmpeg).cut(_posix(source), _posix(clip), TimeRange.parse("0", "2"))
    assert clip.read_bytes() != b"old"
    assert _duration(ffmpeg, clip) == pytest.approx(2, abs=0.2)


def test_failed_cut_keeps_the_previous_clip_and_leaves_no_temp_file(
    ffmpeg: Path, tmp_path: Path
) -> None:
    broken = tmp_path / "full.mp3"
    broken.write_bytes(b"not audio at all")
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(b"previous")
    with pytest.raises(CutFailedError):
        FfmpegClipCutter(ffmpeg).cut(_posix(broken), _posix(clip), TimeRange.parse("0", "2"))
    assert clip.read_bytes() == b"previous"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clip.mp3", "full.mp3"]


def test_range_starting_beyond_the_track_fails(ffmpeg: Path, tmp_path: Path) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3", seconds=5)
    clip = tmp_path / "clip.mp3"
    with pytest.raises(CutFailedError):
        FfmpegClipCutter(ffmpeg).cut(_posix(source), _posix(clip), TimeRange.parse("20", "30"))
    assert not clip.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["full.mp3"]


def test_missing_source_fails(ffmpeg: Path, tmp_path: Path) -> None:
    with pytest.raises(CutFailedError):
        FfmpegClipCutter(ffmpeg).cut(
            _posix(tmp_path / "nope.mp3"), _posix(tmp_path / "clip.mp3"), TimeRange.parse("0", "2")
        )


def test_destination_equal_to_source_is_refused(ffmpeg: Path, tmp_path: Path) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3")
    before = _sha(source)
    with pytest.raises(CutFailedError):
        FfmpegClipCutter(ffmpeg).cut(_posix(source), _posix(source), TimeRange.parse("0", "2"))
    assert _sha(source) == before


def test_unusable_ffmpeg_fails_the_cut(ffmpeg: Path, tmp_path: Path) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3")
    with pytest.raises(CutFailedError):
        FfmpegClipCutter(tmp_path / "missing-ffmpeg").cut(
            _posix(source), _posix(tmp_path / "clip.mp3"), TimeRange.parse("0", "2")
        )
    assert not (tmp_path / "clip.mp3").exists()


def test_configured_path_wins_over_candidates(ffmpeg: Path) -> None:
    assert locate_ffmpeg(configured=ffmpeg, candidates=[Path("/nonexistent/ffmpeg")]) == ffmpeg


def test_candidates_are_tried_in_order_and_unusable_ones_skipped(
    ffmpeg: Path, tmp_path: Path
) -> None:
    bogus = tmp_path / "ffmpeg"
    bogus.write_text("#!/bin/sh\nexit 1\n")
    bogus.chmod(bogus.stat().st_mode | stat.S_IXUSR)
    assert locate_ffmpeg(candidates=[Path("/nonexistent/ffmpeg"), bogus, ffmpeg]) == ffmpeg


def test_configured_unusable_path_is_an_error_without_fallback(
    ffmpeg: Path, tmp_path: Path
) -> None:
    with pytest.raises(FfmpegUnavailableError, match="Configured"):
        locate_ffmpeg(configured=tmp_path / "nope", candidates=[ffmpeg])


def test_relative_configured_path_is_rejected(ffmpeg: Path) -> None:
    with pytest.raises(FfmpegUnavailableError):
        locate_ffmpeg(configured=Path("ffmpeg"), candidates=[ffmpeg])


def test_no_usable_binary_is_a_typed_failure(tmp_path: Path) -> None:
    with pytest.raises(FfmpegUnavailableError, match="not found"):
        locate_ffmpeg(candidates=[tmp_path / "a", tmp_path / "b"])


def test_locator_ignores_path(
    ffmpeg: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "ffmpeg").write_text("#!/bin/sh\necho ffmpeg version fake\n")
    (fake / "ffmpeg").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")
    with pytest.raises(FfmpegUnavailableError):
        locate_ffmpeg(candidates=[tmp_path / "none"])


def test_cutter_prints_nothing_to_stdout(
    ffmpeg: Path, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3")
    capfd.readouterr()
    FfmpegClipCutter(ffmpeg).cut(
        _posix(source), _posix(tmp_path / "clip.mp3"), TimeRange.parse("0", "2")
    )
    captured = capfd.readouterr()
    assert captured.out == "" and captured.err == ""


def test_filesystem_exists_stamp_and_make_dir(tmp_path: Path) -> None:
    fs = LocalFileSystem()
    target = tmp_path / "a" / "b"
    assert not fs.exists(_posix(target))
    assert fs.stamp(_posix(target)) is None
    fs.make_dir(_posix(target))
    fs.make_dir(_posix(target))  # idempotent
    assert fs.exists(_posix(target))
    file = target / "f.mp3"
    file.write_bytes(b"x")
    assert fs.stamp(_posix(file)) == file.stat().st_mtime_ns


def test_make_dir_failure_maps_to_the_domain_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_bytes(b"x")
    with pytest.raises(OutputDirUnavailableError):
        LocalFileSystem().make_dir(_posix(blocker / "sub"))


def test_published_clip_follows_the_umask(ffmpeg: Path, tmp_path: Path) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3")
    clip = tmp_path / "clip.mp3"
    previous = os.umask(0o022)
    try:
        FfmpegClipCutter(ffmpeg).cut(_posix(source), _posix(clip), TimeRange.parse("0", "2"))
    finally:
        os.umask(previous)
    assert stat.S_IMODE(clip.stat().st_mode) == 0o644


def test_range_straddling_the_end_yields_a_short_clip(ffmpeg: Path, tmp_path: Path) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3", seconds=5)
    clip = tmp_path / "clip.mp3"
    FfmpegClipCutter(ffmpeg).cut(_posix(source), _posix(clip), TimeRange.parse("3", "20"))
    assert _duration(ffmpeg, clip) == pytest.approx(2, abs=0.2)


@pytest.fixture
def no_duration_ffmpeg(ffmpeg: Path, tmp_path: Path) -> Path:
    """A wrapper that hides the ``Duration:`` line of probe calls (those without ``-f``)."""
    wrapper = tmp_path / "wrapper" / "ffmpeg"
    wrapper.parent.mkdir()
    wrapper.write_text(
        f'#!/bin/sh\ncase " $* " in *" -f "*) exec "{ffmpeg}" "$@";; esac\n'
        f'"{ffmpeg}" "$@" 2>&1 | sed "s/Duration:/Hidden:/" >&2\n'
    )
    wrapper.chmod(0o755)
    return wrapper


def test_unknown_source_duration_still_cuts(
    ffmpeg: Path, no_duration_ffmpeg: Path, tmp_path: Path
) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3")
    clip = tmp_path / "clip.mp3"
    FfmpegClipCutter(no_duration_ffmpeg).cut(
        _posix(source), _posix(clip), TimeRange.parse("2", "5")
    )
    assert _duration(ffmpeg, clip) == pytest.approx(3, abs=0.2)


def test_unknown_source_duration_still_rejects_a_range_beyond_the_end(
    ffmpeg: Path, no_duration_ffmpeg: Path, tmp_path: Path
) -> None:
    source = _make_source(ffmpeg, tmp_path / "full.mp3", seconds=5)
    clip = tmp_path / "clip.mp3"
    with pytest.raises(CutFailedError):
        FfmpegClipCutter(no_duration_ffmpeg).cut(
            _posix(source), _posix(clip), TimeRange.parse("20", "30")
        )
    assert not clip.exists()
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["full.mp3"]


def test_names_starting_with_a_dash_are_not_taken_as_options(
    ffmpeg: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    source = _make_source(ffmpeg, tmp_path / "-full.mp3")
    FfmpegClipCutter(ffmpeg).cut(
        PurePosixPath("-full.mp3"), PurePosixPath("-clip.mp3"), TimeRange.parse("0", "2")
    )
    assert _duration(ffmpeg, tmp_path / "-clip.mp3") == pytest.approx(2, abs=0.2)
    assert source.exists()
