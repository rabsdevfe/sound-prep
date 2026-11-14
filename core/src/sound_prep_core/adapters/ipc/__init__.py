"""IPC driving adapter: typed messages of the UI <-> core contract (contracts/ipc.schema.json)."""

from sound_prep_core.adapters.ipc.messages import (
    MESSAGE_MODELS,
    ErrorCode,
    ErrorMessage,
    IpcMessage,
    PrepareClipParams,
    PrepareClipRequest,
    ProgressEvent,
    ResultMessage,
    Stage,
    parse_message,
    to_line,
)

__all__ = [
    "MESSAGE_MODELS",
    "ErrorCode",
    "ErrorMessage",
    "IpcMessage",
    "PrepareClipParams",
    "PrepareClipRequest",
    "ProgressEvent",
    "ResultMessage",
    "Stage",
    "parse_message",
    "to_line",
]
