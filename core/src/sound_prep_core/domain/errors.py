"""Typed domain errors. ``code`` matches an ``ErrorCode`` of the IPC contract."""

from typing import ClassVar


class DomainError(Exception):
    """Base class of every error the domain raises on purpose."""

    code: ClassVar[str]


class InvalidTimeRangeError(DomainError):
    code: ClassVar[str] = "invalid_time_range"


class InvalidTitleError(DomainError):
    code: ClassVar[str] = "invalid_title"


class OutputDirUnavailableError(DomainError):
    code: ClassVar[str] = "output_dir_unavailable"


class InvalidUrlError(DomainError):
    code: ClassVar[str] = "invalid_url"


class DownloadFailedError(DomainError):
    code: ClassVar[str] = "download_failed"


class CutFailedError(DomainError):
    code: ClassVar[str] = "cut_failed"
