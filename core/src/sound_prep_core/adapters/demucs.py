"""Locating the external ``demucs`` executable (ADR 0001 applied to demucs).

Demucs is not bundled nor a Python dependency: the user installs it. PATH is never consulted. An
explicitly configured absolute path wins; otherwise fixed absolute candidates are tried. Running
``demucs`` just to probe it would import torch (seconds), so only executability is verified.
"""

import os
from collections.abc import Sequence
from pathlib import Path

FRAMEWORK_VERSIONS = Path("/Library/Frameworks/Python.framework/Versions")


class DemucsUnavailableError(Exception):
    """No usable demucs executable was found, or the configured one does not work."""


def _version_key(path: Path) -> tuple[int, ...]:
    """Sort key of ``Versions/<major.minor>/bin/demucs``: ``3.13`` is newer than ``3.9``."""
    name = path.parent.parent.name
    return tuple(int(part) for part in name.split(".")) if name.replace(".", "").isdigit() else ()


def default_candidates(
    framework_versions: Path = FRAMEWORK_VERSIONS, home: Path | None = None
) -> list[Path]:
    """Fixed absolute locations, built per call (``Path.home()`` is not read at import time).

    Python.framework installs come first, newest version first, then Homebrew and ``~/.local``.
    """
    framework = sorted(framework_versions.glob("*/bin/demucs"), key=_version_key, reverse=True)
    return [
        *framework,
        Path("/opt/homebrew/bin/demucs"),
        Path("/usr/local/bin/demucs"),
        (home or Path.home()) / ".local" / "bin" / "demucs",
    ]


def _problem(path: Path) -> str | None:
    """Return ``None`` when ``path`` is an executable file, else the reason it is not."""
    if not path.is_absolute():
        return f"{path} is not an absolute path (an absolute path is required; ~ is not expanded)"
    if not path.is_file():
        return f"{path} is not a file"
    if not os.access(path, os.X_OK):
        return f"{path} is not executable"
    return None


def locate_demucs(
    configured: Path | None = None,
    candidates: Sequence[Path] | None = None,
) -> Path:
    """Return the absolute path of demucs. Raises ``DemucsUnavailableError``.

    A configured path that does not work is an error, not a reason to fall back silently.
    """
    if configured is not None:
        problem = _problem(configured)
        if problem is not None:
            raise DemucsUnavailableError(f"Configured demucs is unusable: {problem}")
        return configured
    if candidates is None:
        candidates = default_candidates()
    for candidate in candidates:
        if _problem(candidate) is None:
            return candidate
    tried = ", ".join(str(c) for c in candidates)
    raise DemucsUnavailableError(
        f"demucs not found (tried {tried}); install it or configure a path"
    )
