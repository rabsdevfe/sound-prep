"""``ClipCutter`` backed by ffmpeg."""

import os
import re
import secrets
import subprocess
from pathlib import Path, PurePosixPath

from sound_prep_core.domain.errors import CutFailedError
from sound_prep_core.domain.time_range import TimeRange

_PROBE_TIMEOUT_SECONDS = 60
_CUT_TIMEOUT_SECONDS = 600
_DURATION = re.compile(r"Duration: (\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_ENCODED_TIME = re.compile(r"time=(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


def _seconds(hours: str, minutes: str, seconds: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


class FfmpegClipCutter:
    def __init__(self, ffmpeg: Path) -> None:
        self._ffmpeg = str(ffmpeg)

    def _run(self, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self._ffmpeg, "-nostdin", "-hide_banner", *args],
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )

    def _duration(self, path: Path) -> float | None:
        """Container duration reported by ffmpeg, or ``None`` when it does not report one."""
        # Without an output ffmpeg exits non-zero after printing the input info: expected here.
        match = _DURATION.search(self._run(["-i", str(path)], _PROBE_TIMEOUT_SECONDS).stderr)
        return _seconds(*match.groups()) if match else None

    def _decoded_seconds(self, path: Path) -> float:
        """Seconds of audio that actually decode from ``path`` (0 for an empty file)."""
        result = self._run(["-i", str(path), "-f", "null", "-"], _PROBE_TIMEOUT_SECONDS)
        if result.returncode != 0:
            return 0.0
        times = _ENCODED_TIME.findall(result.stderr.replace("\r", "\n"))
        return _seconds(*times[-1]) if times else 0.0

    def cut(self, source: PurePosixPath, destination: PurePosixPath, time_range: TimeRange) -> None:
        src, dest = Path(source), Path(destination)
        if src.resolve() == dest.resolve():
            raise CutFailedError("The clip destination is the source track")
        temp: Path | None = None
        try:
            if not src.is_file():
                raise CutFailedError(f"Source track not found: {src}")
            total = self._duration(src)
            if total is not None and time_range.start.seconds >= total:
                raise CutFailedError(
                    f"Clip starts at {time_range.start.text} but the track lasts {total:.0f}s"
                )
            # O_CREAT with 0o666 lets the umask decide the permissions, like the reference script
            # (mkstemp would force 0600, which the rename would then publish).
            temp = dest.parent / f".{dest.stem}.{secrets.token_hex(8)}.tmp"
            os.close(os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666))
            result = self._run(
                [
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    str(time_range.start.seconds),
                    "-t",
                    str(time_range.duration_seconds),
                    "-i",
                    str(src),
                    "-vn",
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    "0",
                    "-f",
                    "mp3",
                    str(temp),
                ],
                _CUT_TIMEOUT_SECONDS,
            )
            if result.returncode != 0:
                raise CutFailedError(f"ffmpeg failed: {result.stderr.strip()[-500:]}")
            if self._decoded_seconds(temp) <= 0:
                raise CutFailedError("ffmpeg produced an empty clip")
            os.replace(temp, dest)
            temp = None
        except subprocess.TimeoutExpired as error:
            raise CutFailedError("ffmpeg timed out") from error
        except OSError as error:
            raise CutFailedError(f"Cannot cut the clip: {error}") from error
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
