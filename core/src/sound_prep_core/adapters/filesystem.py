"""Local disk implementation of the ``FileSystem`` port."""

from pathlib import Path, PurePosixPath

from sound_prep_core.domain.errors import OutputDirUnavailableError


class LocalFileSystem:
    def exists(self, path: PurePosixPath) -> bool:
        return Path(path).exists()

    def stamp(self, path: PurePosixPath) -> int | None:
        try:
            return Path(path).stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def make_dir(self, path: PurePosixPath) -> None:
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise OutputDirUnavailableError(f"Cannot use directory {path}: {error}") from error
