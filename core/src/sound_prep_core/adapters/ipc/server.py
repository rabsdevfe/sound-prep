"""stdio server for IPC contract v1: JSON Lines in, JSON Lines out.

``serve`` reads one request per line until EOF and writes one contract message per line, flushed
immediately. It never raises because of a bad line: every failure becomes an ``error`` message
(``internal_error`` for unexpected exceptions, without the traceback, which goes to the log).
Blank lines are ignored. Lines longer than ``MAX_LINE_BYTES`` are discarded and answered with
``invalid_request``. The loop only ends at EOF or when the reader of stdout has gone away.
"""

import json
import logging
from collections.abc import Callable
from typing import BinaryIO, Protocol, get_args

from pydantic import ValidationError

from sound_prep_core.adapters.ipc.messages import (
    ErrorCode,
    ErrorMessage,
    IpcMessage,
    PrepareClipRequest,
    ProgressEvent,
    ResultMessage,
    to_line,
)
from sound_prep_core.domain.errors import DomainError
from sound_prep_core.domain.layout import OutputLayout
from sound_prep_core.domain.ports import ProgressReporter, ProgressStage
from sound_prep_core.use_cases.prepare_clip import PrepareClipRequest as DomainRequest

MAX_LINE_BYTES = 1024 * 1024
_MAX_ID_LENGTH = 128
_LOG = logging.getLogger(__name__)

# Contract field (inside ``params``) to the error code and fixed message reported when invalid.
_FIELD_ERRORS = {
    "url": ("invalid_url", "The URL must be an http or https URL without spaces"),
    "title": ("invalid_title", "The title must be between 1 and 120 characters"),
    "start": ("invalid_time_range", "The start time must be SS, MM:SS or HH:MM:SS"),
    "end": ("invalid_time_range", "The end time must be SS, MM:SS or HH:MM:SS"),
    "output_dir": ("output_dir_unavailable", "The output directory must be an absolute path"),
}
_CODES = frozenset(get_args(ErrorCode))


class InternalError(Exception):
    """Raise to answer ``internal_error`` with this (safe, user-facing) message."""


class RequestHandler(Protocol):
    def execute(self, request: DomainRequest) -> OutputLayout: ...


#: Builds the handler of one request around the reporter that emits its progress events.
HandlerFactory = Callable[[ProgressReporter], RequestHandler]


class _Reporter:
    def __init__(self, request_id: str, emit: Callable[[IpcMessage], None]) -> None:
        self._id = request_id
        self._emit = emit

    def report(self, stage: ProgressStage) -> None:
        self._emit(ProgressEvent(v=1, id=self._id, type="progress", stage=stage.value))


def _error(request_id: str | None, code: str, message: str) -> ErrorMessage:
    if code not in _CODES:  # a code outside the contract must never break the answer
        code = "internal_error"
    return ErrorMessage.model_validate(
        {"v": 1, "id": request_id, "type": "error", "code": code, "message": message}
    )


def _encodable(value: object) -> bool:
    """True when the JSON value can be written back as UTF-8 (no lone surrogates anywhere)."""
    try:
        json.dumps(value, ensure_ascii=False).encode("utf-8")
    except (UnicodeEncodeError, RecursionError):
        return False
    return True


def _recover_id(obj: object) -> str | None:
    if isinstance(obj, dict):
        value = obj.get("id")
        if isinstance(value, str) and 1 <= len(value) <= _MAX_ID_LENGTH and _encodable(value):
            return value
    return None


def _invalid_fields_code(exc: ValidationError) -> tuple[str, str]:
    """Pick the error code and a fixed message (never echoing input or patterns)."""
    errors = exc.errors(include_input=False, include_url=False, include_context=False)
    locs = [tuple(str(part) for part in e["loc"]) for e in errors]
    if all(len(loc) == 2 and loc[0] == "params" for loc in locs):
        for error, loc in zip(errors, locs, strict=True):
            if error["type"] not in {"missing", "extra_forbidden"} and loc[1] in _FIELD_ERRORS:
                return _FIELD_ERRORS[loc[1]]
    where = ".".join(locs[0]) if locs else "request"
    return "invalid_request", f"Invalid or missing field: {where}"


def _parse(raw: bytes) -> PrepareClipRequest | ErrorMessage:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _error(None, "invalid_request", "Request is not valid UTF-8")
    try:
        obj = json.loads(text)
    except (ValueError, RecursionError):
        return _error(None, "invalid_request", "Request is not valid JSON")
    request_id = _recover_id(obj)
    if not isinstance(obj, dict):
        return _error(None, "invalid_request", "Request must be a JSON object")
    if not _encodable(obj):
        return _error(request_id, "invalid_request", "Request contains unpaired surrogates")
    version = obj.get("v")
    if isinstance(version, int) and not isinstance(version, bool) and version != 1:
        return _error(request_id, "unsupported_version", f"Unsupported version: {version}")
    try:
        return PrepareClipRequest.model_validate_json(text)
    except ValidationError as exc:
        code, message = _invalid_fields_code(exc)
        return _error(request_id, code, message)


def _read_line(stdin: BinaryIO) -> tuple[bytes, bool] | None:
    """Return ``(line, too_long)``; ``None`` at EOF. An oversized line is drained, not kept."""
    chunk = stdin.readline(MAX_LINE_BYTES + 1)
    if not chunk:
        return None
    if len(chunk) <= MAX_LINE_BYTES or chunk.endswith(b"\n"):
        return chunk, False
    while chunk and not chunk.endswith(b"\n"):
        chunk = stdin.readline(MAX_LINE_BYTES)
    return b"", True


def serve(stdin: BinaryIO, stdout: BinaryIO, make_handler: HandlerFactory) -> int:
    """Run the request loop until EOF. Returns the process exit code (0 on EOF)."""

    def emit(message: IpcMessage) -> None:
        data = (to_line(message) + "\n").encode("utf-8")
        stdout.write(data)
        stdout.flush()

    known_id: str | None = None

    def handle(raw: bytes, too_long: bool) -> None:
        nonlocal known_id
        known_id = None
        if too_long:
            emit(_error(None, "invalid_request", f"Request exceeds {MAX_LINE_BYTES} bytes"))
            return
        if not raw.strip():
            return
        parsed = _parse(raw)
        if isinstance(parsed, ErrorMessage):
            emit(parsed)
            return
        request_id = known_id = parsed.id
        try:
            p = parsed.params
            layout = make_handler(_Reporter(request_id, emit)).execute(
                DomainRequest(p.url, p.title, p.output_dir, p.start, p.end)
            )
            result: IpcMessage = ResultMessage(
                v=1,
                id=request_id,
                type="result",
                folder=str(layout.folder),
                full_track=str(layout.full_track),
                clip=str(layout.clip),
            )
        except DomainError as exc:
            result = _error(request_id, exc.code, str(exc) or exc.code)
        except InternalError as exc:
            result = _error(request_id, "internal_error", str(exc) or "Internal error")
        except Exception:
            _LOG.exception("Unexpected error while handling request %s", request_id)
            result = _error(request_id, "internal_error", "Internal error")
        emit(result)

    try:
        while (item := _read_line(stdin)) is not None:
            try:
                handle(*item)
            except (BrokenPipeError, ConnectionResetError):
                raise
            except Exception:
                # Last resort (e.g. an unencodable message): answer once, keep serving.
                _LOG.exception("Unexpected error in the request loop")
                emit(_error(known_id, "internal_error", "Internal error"))
    except (BrokenPipeError, ConnectionResetError):
        _LOG.error("stdout closed; stopping")
        return 1
    return 0
