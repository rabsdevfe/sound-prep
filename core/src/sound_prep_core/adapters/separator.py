"""``StemSeparator`` backed by the external demucs CLI (six-stem model, piano merged into other)."""

import codecs
import contextlib
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath

from sound_prep_core.domain.errors import SeparationFailedError
from sound_prep_core.domain.stems import Stem

_MODEL = "htdemucs_6s"
_TIMEOUT_SECONDS = 30 * 60
_MERGE_TIMEOUT_SECONDS = 300
_PERCENT = re.compile(r"(\d{1,3})%\|")
_STDERR_TAIL = 500
# Demucs names its outputs after the six-stem model; piano is folded into `other`.
_MODEL_STEMS = (*(s.value for s in Stem), "piano")
_FFMPEG_FLAGS = ("-nostdin", "-hide_banner", "-loglevel", "error", "-y")
_MIX = "amix=inputs=2:normalize=0,alimiter=limit=0.98"


def default_devices() -> tuple[str, ...]:
    """MPS first on Apple silicon, falling back to the CPU when demucs fails with it."""
    if sys.platform == "darwin" and platform.machine() == "arm64":
        return ("mps", "cpu")
    return ("cpu",)


def _kill_group(process: "subprocess.Popen[bytes]") -> None:
    """Kill demucs and its children (the ffmpeg it spawns shares its stderr pipe)."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)


class DemucsStemSeparator:
    """Retries on the next device after ANY demucs failure: its exit codes do not say why."""

    def __init__(
        self,
        demucs: Path,
        ffmpeg: Path,
        devices: Sequence[str] | None = None,
        timeout_seconds: float = _TIMEOUT_SECONDS,
    ) -> None:
        self._demucs = str(demucs)
        self._ffmpeg = ffmpeg
        self._devices = tuple(devices) if devices is not None else default_devices()
        self._timeout = timeout_seconds

    def _env(self) -> dict[str, str]:
        # Demucs decodes mp3 by spawning `ffmpeg` through PATH, which is minimal under a GUI app.
        env = dict(os.environ)
        env["PATH"] = os.pathsep.join([str(self._ffmpeg.parent), *filter(None, [env.get("PATH")])])
        return env

    def _run_demucs(
        self, source: Path, out_dir: Path, device: str, on_percent: Callable[[int], None]
    ) -> str | None:
        """Run demucs once. Returns ``None`` on success, else the reason it failed."""
        process = subprocess.Popen(
            [self._demucs, "-n", _MODEL, "-d", device, "-o", str(out_dir), str(source)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=self._env(),
            start_new_session=True,  # own process group, so a timeout can kill the whole tree
        )
        timed_out = threading.Event()

        def expire() -> None:
            if process.poll() is None:  # a clean exit just before the timer fired is not a timeout
                timed_out.set()
                _kill_group(process)

        timer = threading.Timer(self._timeout, expire)
        timer.start()
        tail = ""
        try:
            assert process.stderr is not None
            pending = ""
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while chunk := os.read(process.stderr.fileno(), 4096):
                # tqdm redraws its bar with `\r`; split on both separators.
                *lines, pending = re.split(r"[\r\n]", pending + decoder.decode(chunk))
                pending = pending[-4096:]
                for line in lines:
                    tail = (tail + "\n" + line)[-_STDERR_TAIL:]
                    match = _PERCENT.search(line)
                    if match:
                        on_percent(min(int(match.group(1)), 99))  # 100 is reported once published
            tail = (tail + "\n" + pending)[-_STDERR_TAIL:]
            code = process.wait()
        finally:
            timer.cancel()
            _kill_group(process)  # also on early exit (e.g. a callback error): no orphans
            process.wait()
            if process.stderr is not None:
                process.stderr.close()
        if timed_out.is_set():
            raise SeparationFailedError(f"demucs timed out after {self._timeout:.0f}s")
        if code != 0:
            return f"demucs ({device}) exited with code {code}: {tail.strip()}"
        return None

    def _merge_other(self, staged: Path) -> None:
        merged = staged / "merged.wav"
        result = subprocess.run(
            [
                str(self._ffmpeg),
                *_FFMPEG_FLAGS,
                "-i",
                str(staged / "piano.wav"),
                "-i",
                str(staged / "other.wav"),
                *["-filter_complex", _MIX, "-c:a", "pcm_s16le", str(merged)],
            ],
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=_MERGE_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            raise SeparationFailedError(
                f"ffmpeg failed merging piano: {result.stderr.strip()[-300:]}"
            )
        merged.replace(staged / Stem.OTHER.filename)

    def separate(
        self,
        source: PurePosixPath,
        destination: PurePosixPath,
        on_percent: Callable[[int], None],
    ) -> None:
        src, dest = Path(source), Path(destination)
        last = -1

        def report(percent: int) -> None:
            # Port contract: never decreasing (a retry restarts demucs at 0), once per value.
            nonlocal last
            if percent > last:
                last = percent
                with contextlib.suppress(Exception):  # best effort, as the port says
                    on_percent(percent)

        staging: Path | None = None
        try:
            if not src.is_file():
                raise SeparationFailedError(f"Source track not found: {src}")
            dest.mkdir(parents=True, exist_ok=True)
            # A crashed run (SIGKILL) leaves gigabytes of staging behind; the sidecar runs one job
            # at a time, so any staging folder found here is stale.
            for stale in dest.glob(".sound-prep-stems-*"):
                shutil.rmtree(stale, ignore_errors=True)
            # Staged inside the destination so the final renames never cross a filesystem.
            staging = Path(tempfile.mkdtemp(prefix=".sound-prep-stems-", dir=dest))
            failures: list[str] = []
            for device in self._devices:
                failure = self._run_demucs(src, staging, device, report)
                if failure is None:
                    break
                failures.append(failure)
            else:
                raise SeparationFailedError("; ".join(failures) or "No device to run demucs on")
            produced = staging / _MODEL / src.stem
            missing = [n for n in _MODEL_STEMS if not (produced / f"{n}.wav").is_file()]
            if missing:
                raise SeparationFailedError(f"demucs did not produce: {', '.join(missing)}")
            self._merge_other(produced)
            # All five are produced and merged before the first rename. The renames themselves
            # are sequential same-filesystem replaces: staging is guaranteed, not the atomicity
            # of the whole set.
            for stem in Stem:
                (produced / stem.filename).replace(dest / stem.filename)
            report(100)  # a success always ends with 100
        except (subprocess.TimeoutExpired, OSError) as error:
            raise SeparationFailedError(f"Cannot separate the track: {error}") from error
        finally:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
