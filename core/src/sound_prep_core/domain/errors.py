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
