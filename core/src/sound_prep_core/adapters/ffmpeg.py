"""Locating a usable ffmpeg binary (ADR 0001, option B).

A GUI-launched process has a minimal PATH, and trusting PATH would run whatever is first on it,
so PATH is never consulted. An explicitly configured absolute path wins; otherwise fixed absolute
candidates are tried. The chosen binary must actually run (``-version``).
"""

import subprocess
from collections.abc import Sequence
from pathlib import Path

DEFAULT_CANDIDATES: tuple[Path, ...] = (
    Path("/opt/homebrew/bin/ffmpeg"),
    Path("/usr/local/bin/ffmpeg"),
)
_VERSION_TIMEOUT_SECONDS = 10


class FfmpegUnavailableError(Exception):
    """No usable ffmpeg binary was found, or the configured one does not work."""


def _check_runs(path: Path) -> str | None:
    """Return ``None`` when ``path`` is a working ffmpeg, else the reason it is not."""
    if not path.is_absolute():
        return f"{path} is not an absolute path"
    try:
        result = subprocess.run(
            [str(path), "-version"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=_VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return f"{path} cannot be run: {error}"
    if result.returncode != 0 or not result.stdout.startswith("ffmpeg version"):
        return f"{path} is not a working ffmpeg (exit code {result.returncode})"
    return None


def locate_ffmpeg(
    configured: Path | None = None,
    candidates: Sequence[Path] = DEFAULT_CANDIDATES,
) -> Path:
    """Return the absolute path of a working ffmpeg. Raises ``FfmpegUnavailableError``.

    A configured path that does not work is an error, not a reason to fall back silently: the
    user asked for that binary.
    """
    if configured is not None:
        problem = _check_runs(configured)
        if problem is not None:
            raise FfmpegUnavailableError(f"Configured ffmpeg is unusable: {problem}")
        return configured
    for candidate in candidates:
        if _check_runs(candidate) is None:
            return candidate
    tried = ", ".join(str(c) for c in candidates)
    raise FfmpegUnavailableError(
        f"ffmpeg not found (tried {tried}); install it or configure a path"
    )
