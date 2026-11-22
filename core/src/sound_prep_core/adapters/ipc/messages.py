"""Pydantic models of IPC contract v1.

The JSON Schema in ``contracts/ipc.schema.json`` is the source of truth. These models mirror it;
``tests/test_ipc_models.py`` proves they agree on every fixture and share the schema's patterns.
To add a command, add a model, add it to ``IpcMessage`` and update the schema in the same change.
"""

from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

# Patterns are copied verbatim from the schema. They must run on Python's `re` (not pydantic's
# default Rust engine, which has no lookahead) and use explicit classes so they match the same
# characters as ECMAScript.
CLIP_TIME_PATTERN = r"^(?:[0-9]+|[0-9]+:[0-5][0-9]|[0-9]+:[0-5][0-9]:[0-5][0-9])(?![\s\S])"
ABSOLUTE_PATH_PATTERN = r"^/[^\x00-\x1f\x7f-\x9f\u2028\u2029]*(?![\s\S])"
URL_PATTERN = (
    r"^https?://"
    r"[^\x00-\x20\x7f-\x9f\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff/?#]+"
    r"[^\x00-\x20\x7f-\x9f\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]*"
    r"(?![\s\S])"
)


def _reject_bool(value: Any) -> Any:
    # JSON Schema keeps booleans and numbers apart; Python treats True as 1.
    if isinstance(value, bool):
        raise ValueError("a boolean is not a number")
    return value


Version = Annotated[Literal[1], BeforeValidator(_reject_bool)]
MessageId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
AbsolutePath = Annotated[str, StringConstraints(pattern=ABSOLUTE_PATH_PATTERN)]
ClipTime = Annotated[str, StringConstraints(pattern=CLIP_TIME_PATTERN)]
HttpUrl = Annotated[str, StringConstraints(pattern=URL_PATTERN)]

Stage = Literal["downloading", "cutting", "separating"]
ErrorCode = Literal[
    "invalid_request",
    "unsupported_version",
    "invalid_url",
    "invalid_time_range",
    "invalid_title",
    "output_dir_unavailable",
    "download_failed",
    "cut_failed",
    "separation_failed",
    "internal_error",
]

_STRICT = ConfigDict(extra="forbid", strict=True, regex_engine="python-re", frozen=True)


class _Model(BaseModel):
    model_config = _STRICT


class PrepareClipParams(_Model):
    url: HttpUrl
    title: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    output_dir: AbsolutePath
    start: ClipTime | None = None
    end: ClipTime | None = None
    separate_stems: bool = False

    @field_validator("start", "end", "separate_stems", mode="before")
    @classmethod
    def _absent_or_value(cls, value: Any) -> Any:
        # Optional fields may be omitted, but an explicit null is never valid.
        if value is None:
            raise ValueError("must be omitted, not null")
        return value

    @model_validator(mode="after")
    def _time_range_matches_mode(self) -> Self:
        has_range = "start" in self.model_fields_set or "end" in self.model_fields_set
        if self.separate_stems:
            if has_range:
                raise ValueError("start and end must be absent when separate_stems is true")
        elif "start" not in self.model_fields_set or "end" not in self.model_fields_set:
            raise ValueError("start and end are required unless separate_stems is true")
        return self


class PrepareClipRequest(_Model):
    """UI -> core."""

    v: Version
    id: MessageId
    type: Literal["prepare_clip"]
    params: PrepareClipParams


class ProgressEvent(_Model):
    """Core -> UI, zero or more per request."""

    v: Version
    id: MessageId
    type: Literal["progress"]
    stage: Stage
    percent: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)] | None = None

    @field_validator("percent", mode="before")
    @classmethod
    def _absent_or_number(cls, value: Any) -> Any:
        # The field may be omitted, but an explicit null is not a number (validators do not
        # run for the omitted default).
        if value is None:
            raise ValueError("percent must be a number or omitted, not null")
        if isinstance(value, bool):
            raise ValueError("a boolean is not a number")
        return value


class Stems(_Model):
    drums: AbsolutePath
    bass: AbsolutePath
    vocals: AbsolutePath
    guitar: AbsolutePath
    other: AbsolutePath


class ResultMessage(_Model):
    """Core -> UI, terminal success. Exactly one of ``clip`` or ``stems`` is present."""

    v: Version
    id: MessageId
    type: Literal["result"]
    folder: AbsolutePath
    full_track: AbsolutePath
    clip: AbsolutePath | None = None
    stems: Stems | None = None

    @field_validator("clip", "stems", mode="before")
    @classmethod
    def _absent_or_value(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("must be omitted, not null")
        return value

    @model_validator(mode="after")
    def _exactly_one_output(self) -> Self:
        if ("clip" in self.model_fields_set) == ("stems" in self.model_fields_set):
            raise ValueError("exactly one of clip or stems must be present")
        return self


class ErrorMessage(_Model):
    """Core -> UI, terminal failure. ``id`` is None only when the request id was unreadable."""

    v: Version
    id: MessageId | None
    type: Literal["error"]
    code: ErrorCode
    message: NonEmptyString


IpcMessage = Annotated[
    PrepareClipRequest | ProgressEvent | ResultMessage | ErrorMessage,
    Field(discriminator="type"),
]

#: Message ``type`` to its model; one entry per branch of the schema's ``type`` enum.
MESSAGE_MODELS: Mapping[str, type[BaseModel]] = {
    "prepare_clip": PrepareClipRequest,
    "progress": ProgressEvent,
    "result": ResultMessage,
    "error": ErrorMessage,
}

_ADAPTER: TypeAdapter[IpcMessage] = TypeAdapter(IpcMessage)


def parse_message(line: str | bytes) -> IpcMessage:
    """Parse one JSON line into a message; raises ``pydantic.ValidationError`` if invalid.

    Duplicate keys in the object are not rejected: the last one wins, as in ``JSON.parse``.
    """
    return _ADAPTER.validate_json(line)


def to_line(message: IpcMessage) -> str:
    """Serialize a message to one JSON line (no trailing newline).

    Fields that were never set (an omitted ``percent``) are left out; every other field is
    written, including an explicit ``id: null`` on errors.
    """
    return message.model_dump_json(exclude_unset=True)
