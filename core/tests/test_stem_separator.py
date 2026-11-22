"""Stem separator tests: a FAKE demucs executable stands in for the real one (not installed in CI);
the stem merge runs the REAL ffmpeg."""

import os
import stat
import sys
import time
import wave
from pathlib import Path, PurePosixPath

import pytest

from sound_prep_core.adapters.ffmpeg import FfmpegUnavailableError, locate_ffmpeg
from sound_prep_core.adapters.separator import DemucsStemSeparator
from sound_prep_core.domain.errors import SeparationFailedError
from sound_prep_core.domain.stems import Stem

FAKE_DEMUCS = """#!{python}
import os, subprocess, sys, time, wave
if {mode!r} == "hang":  # first thing, so the pidfile exists even under a short timeout
    child = subprocess.Popen(["sleep", "60"])  # shares our stderr, like the ffmpeg demucs spawns
    open({pidfile!r}, "w").write(str(child.pid))
    time.sleep(60)
args = sys.argv[1:]
device = args[args.index("-d") + 1]
out = args[args.index("-o") + 1]
mode = {mode!r}
open({log!r}, "a").write(device + " " + os.environ["PATH"].split(os.pathsep)[0] + "\\n")


def bar(pct):
    sys.stderr.write(f" {{pct}}%|#####     | {{pct}}/100 [00:01<00:01, 9seconds/s]\\r")
    sys.stderr.flush()


if mode == "fail" or (mode == "fail_mps" and device == "mps"):
    sys.stderr.write("RuntimeError: boom\\n")
    sys.exit(1)
if mode == "fail_mps_late" and device == "mps":
    bar(0)
    bar(70)
    sys.exit(1)
for pct in (0, 40) if mode == "short_bar" else (0, 0, 40, 40, 100):
    bar(pct)
folder = os.path.join(out, "htdemucs_6s", os.path.splitext(os.path.basename(args[-1]))[0])
os.makedirs(folder)
for stem, level in {levels!r}.items():
    if mode == "incomplete" and stem == "guitar":
        continue
    with wave.open(os.path.join(folder, stem + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(level.to_bytes(2, "little", signed=True) * 800)
"""
LEVELS = {"drums": 1000, "bass": 2000, "vocals": 3000, "guitar": 4000, "piano": 5000, "other": 6000}


@pytest.fixture(scope="session")
def ffmpeg() -> Path:
    candidates = [
        Path(p) for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg")
    ]
    try:
        return locate_ffmpeg(candidates=candidates)
    except FfmpegUnavailableError:
        pytest.skip("ffmpeg is not installed")


def _fake_demucs(tmp_path: Path, mode: str = "ok") -> Path:
    script = tmp_path / "bin" / "demucs"
    script.parent.mkdir(exist_ok=True)
    script.write_text(
        FAKE_DEMUCS.format(
            python=sys.executable,
            mode=mode,
            log=str(tmp_path / "demucs.log"),
            pidfile=str(tmp_path / "child.pid"),
            levels=LEVELS,
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def _separate(
    tmp_path: Path,
    ffmpeg: Path,
    mode: str = "ok",
    devices: tuple[str, ...] = ("cpu",),
    timeout_seconds: float = 60,
) -> tuple[list[int], Path]:
    track = tmp_path / "My Song.mp3"
    track.write_bytes(b"not decoded by the fake")
    separator = DemucsStemSeparator(_fake_demucs(tmp_path, mode), ffmpeg, devices, timeout_seconds)
    percents: list[int] = []
    dest = tmp_path / "out" / "stems"
    separator.separate(PurePosixPath(track), PurePosixPath(dest), percents.append)
    return percents, dest


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def _samples(path: Path) -> list[int]:
    with wave.open(str(path)) as w:
        raw = w.readframes(w.getnframes())
    return [int.from_bytes(raw[i : i + 2], "little", signed=True) for i in range(0, len(raw), 2)]


def test_publishes_five_stems_with_piano_mixed_into_other(tmp_path: Path, ffmpeg: Path) -> None:
    _, dest = _separate(tmp_path, ffmpeg)
    assert _names(dest) == sorted(s.filename for s in Stem)  # no staging left behind
    assert _samples(dest / "drums.wav")[400] == 1000
    other = _samples(dest / "other.wav")
    # normalize=0 sums piano (5000) and other (6000); the limiter keeps it below full scale.
    assert 9000 <= other[400] <= 13000  # about the sum (11000), above either input
    assert max(abs(s) for s in other) < 32768 * 0.99
    with wave.open(str(dest / "other.wav")) as w:
        assert w.getsampwidth() == 2
    umask = os.umask(0)
    os.umask(umask)
    assert {(dest / s.filename).stat().st_mode & 0o777 for s in Stem} == {0o666 & ~umask}


@pytest.mark.parametrize(
    ("mode", "expected"), [("ok", [0, 40, 99, 100]), ("short_bar", [0, 40, 100])]
)
def test_percent_is_capped_while_running_and_a_success_ends_at_100(
    tmp_path: Path, ffmpeg: Path, mode: str, expected: list[int]
) -> None:
    percents, _ = _separate(tmp_path, ffmpeg, mode)
    assert percents == expected
    log = (tmp_path / "demucs.log").read_text()
    assert log.split()[1] == str(ffmpeg.parent)  # demucs finds ffmpeg through PATH


def test_cpu_retry_after_mps_failure_keeps_percent_monotonic(tmp_path: Path, ffmpeg: Path) -> None:
    percents, dest = _separate(tmp_path, ffmpeg, "fail_mps_late", devices=("mps", "cpu"))
    devices = [line.split()[0] for line in (tmp_path / "demucs.log").read_text().splitlines()]
    assert devices == ["mps", "cpu"]
    assert percents == [0, 70, 99, 100]
    assert (dest / "vocals.wav").is_file()


def test_failure_reports_the_cause_and_keeps_existing_stems(tmp_path: Path, ffmpeg: Path) -> None:
    dest = tmp_path / "out" / "stems"
    dest.mkdir(parents=True)
    (dest / "drums.wav").write_bytes(b"old")
    with pytest.raises(SeparationFailedError, match="boom"):
        _separate(tmp_path, ffmpeg, "fail", devices=("mps", "cpu"))
    assert _names(dest) == ["drums.wav"]
    assert (dest / "drums.wav").read_bytes() == b"old"


def test_missing_demucs_stem_fails_without_publishing(tmp_path: Path, ffmpeg: Path) -> None:
    with pytest.raises(SeparationFailedError, match="guitar"):
        _separate(tmp_path, ffmpeg, "incomplete")
    assert _names(tmp_path / "out" / "stems") == []


def test_replaces_only_stem_files_and_clears_stale_staging(tmp_path: Path, ffmpeg: Path) -> None:
    dest = tmp_path / "out" / "stems"
    stale = dest / ".sound-prep-stems-crashed"  # left by a SIGKILLed run
    stale.mkdir(parents=True)
    (stale / "big.wav").write_bytes(b"x")
    (dest / "drums.wav").write_bytes(b"old")
    (dest / "notes.txt").write_text("keep")
    _separate(tmp_path, ffmpeg)
    assert _samples(dest / "drums.wav")[0] == 1000
    assert (dest / "notes.txt").read_text() == "keep"
    assert _names(dest) == sorted([*(s.filename for s in Stem), "notes.txt"])


def test_timeout_kills_demucs_and_its_children_promptly(tmp_path: Path, ffmpeg: Path) -> None:
    started = time.monotonic()
    with pytest.raises(SeparationFailedError, match="timed out"):
        _separate(tmp_path, ffmpeg, "hang", timeout_seconds=3)
    assert time.monotonic() - started < 15
    assert _names(tmp_path / "out" / "stems") == []
    pidfile = tmp_path / "child.pid"
    assert pidfile.exists(), "the fake demucs was killed before it wrote the grandchild pid"
    child = int(pidfile.read_text())
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("the grandchild is still alive")


def test_a_failing_callback_does_not_stop_it_and_a_missing_source_fails(
    tmp_path: Path, ffmpeg: Path
) -> None:
    def broken(_: int) -> None:
        raise RuntimeError("ui gone")

    track = tmp_path / "t.mp3"
    track.write_bytes(b"x")
    separator = DemucsStemSeparator(_fake_demucs(tmp_path), ffmpeg, ("cpu",))
    stems = PurePosixPath(tmp_path / "stems")
    separator.separate(PurePosixPath(track), stems, broken)
    assert (tmp_path / "stems" / "bass.wav").is_file()
    with pytest.raises(SeparationFailedError, match="not found"):
        separator.separate(PurePosixPath(tmp_path / "nope.mp3"), stems, broken)
