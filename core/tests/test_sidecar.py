"""stdio server: contract compliance (schema as oracle), error mapping and loop resilience."""

import io
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from sound_prep_core.adapters.ipc.server import (
    MAX_LINE_BYTES,
    InternalError,
    RequestHandler,
    serve,
)
from sound_prep_core.domain.errors import (
    CutFailedError,
    DownloadFailedError,
    InvalidTimeRangeError,
    InvalidTitleError,
    InvalidUrlError,
    OutputDirUnavailableError,
)
from sound_prep_core.domain.layout import OutputLayout
from sound_prep_core.domain.ports import ProgressReporter, ProgressStage
from sound_prep_core.domain.time_range import TimeRange
from sound_prep_core.domain.title import Title
from sound_prep_core.use_cases.prepare_clip import PrepareClipRequest

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts" / "ipc.schema.json").read_text("utf-8")
)
VALIDATOR = Draft202012Validator(SCHEMA)
PARAMS = {
    "url": "https://youtu.be/x",
    "title": "Song",
    "output_dir": "/out",
    "start": "0:10",
    "end": "0:20",
}


def req(request_id: object = "r1", **overrides: Any) -> bytes:
    body: dict[str, Any] = {
        "v": 1,
        "id": request_id,
        "type": "prepare_clip",
        "params": {**PARAMS, **overrides},
    }
    return json.dumps(body).encode() + b"\n"


class Handler:
    def __init__(self, progress: ProgressReporter, behavior: Callable[[], None]) -> None:
        self.progress = progress
        self.behavior = behavior

    def execute(self, request: PrepareClipRequest) -> OutputLayout:
        self.progress.report(ProgressStage.DOWNLOADING)
        self.behavior()
        self.progress.report(ProgressStage.CUTTING)
        layout = OutputLayout.compute(
            request.output_dir, Title(request.title), TimeRange.parse(request.start, request.end)
        )
        return layout


def run(
    data: bytes, behavior: Callable[[], None] = lambda: None
) -> tuple[int, list[dict[str, Any]]]:
    out = io.BytesIO()

    def factory(progress: ProgressReporter) -> RequestHandler:
        return Handler(progress, behavior)

    code = serve(io.BytesIO(data), out, factory)
    raw = out.getvalue()
    assert raw == b"" or raw.endswith(b"\n")
    messages = [json.loads(line) for line in raw.splitlines()]
    for message in messages:
        assert VALIDATOR.is_valid(message), message
        assert message["type"] in {"progress", "result", "error"}
    return code, messages


def raiser(exc: BaseException) -> Callable[[], None]:
    def _raise() -> None:
        raise exc

    return _raise


def test_success_emits_progress_in_order_then_one_result_with_the_request_id() -> None:
    code, messages = run(req("abc"))
    assert code == 0
    assert [m["type"] for m in messages] == ["progress", "progress", "result"]
    assert [m.get("stage") for m in messages[:2]] == ["downloading", "cutting"]
    assert {m["id"] for m in messages} == {"abc"}
    assert messages[2]["clip"] == "/out/Song/0-10_0-20.mp3"
    assert messages[2]["full_track"] == "/out/Song/Song.mp3"
    assert messages[2]["folder"] == "/out/Song"


def test_eof_without_trailing_newline_still_handles_the_last_request() -> None:
    _, messages = run(req().rstrip(b"\n"))
    assert messages[-1]["type"] == "result"


def test_empty_input_exits_zero_with_no_output() -> None:
    assert run(b"") == (0, [])


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (InvalidUrlError("u"), "invalid_url"),
        (InvalidTimeRangeError("t"), "invalid_time_range"),
        (InvalidTitleError("n"), "invalid_title"),
        (OutputDirUnavailableError("o"), "output_dir_unavailable"),
        (DownloadFailedError("d"), "download_failed"),
        (CutFailedError("c"), "cut_failed"),
        (InternalError("not wired"), "internal_error"),
        (RuntimeError("boom secret"), "internal_error"),
    ],
)
def test_use_case_errors_map_to_their_code_after_progress(error: Exception, code: str) -> None:
    _, messages = run(req("e1"), raiser(error))
    assert [m["type"] for m in messages] == ["progress", "error"]
    assert messages[1]["id"] == "e1"
    assert messages[1]["code"] == code


def test_unexpected_exception_does_not_leak_details() -> None:
    _, messages = run(req(), raiser(RuntimeError("secret /etc/passwd")))
    assert "secret" not in json.dumps(messages)


def test_empty_domain_error_message_falls_back_to_the_code() -> None:
    _, messages = run(req(), raiser(CutFailedError()))
    assert messages[-1]["message"] == "cut_failed"


@pytest.mark.parametrize(
    "line",
    [b"not json\n", b"[1,2]\n", b"42\n", b'"x"\n', b"null\n", b"{\n", b"\xff\xfe\x00\n"],
)
def test_unparseable_input_gets_invalid_request_with_null_id(line: bytes) -> None:
    _, messages = run(line)
    assert len(messages) == 1
    assert messages[0]["code"] == "invalid_request"
    assert messages[0]["id"] is None


def test_deeply_nested_json_is_answered_not_fatal() -> None:
    _, messages = run(b"[" * 100000 + b"\n" + req("after"))
    assert messages[0]["code"] == "invalid_request"
    assert messages[-1]["id"] == "after"
    assert messages[-1]["type"] == "result"


@pytest.mark.parametrize("version", [2, 0, 99])
def test_unsupported_version_keeps_the_id(version: int) -> None:
    body = json.dumps({"v": version, "id": "v1", "type": "prepare_clip", "params": {}})
    _, messages = run(body.encode() + b"\n")
    assert messages == [
        {
            "v": 1,
            "id": "v1",
            "type": "error",
            "code": "unsupported_version",
            "message": f"Unsupported version: {version}",
        }
    ]


def test_unsupported_version_without_a_valid_id_has_null_id() -> None:
    _, messages = run(b'{"v": 2, "id": 7}\n')
    assert messages[0]["code"] == "unsupported_version"
    assert messages[0]["id"] is None


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("url", "ftp://x/y", "invalid_url"),
        ("url", "has space", "invalid_url"),
        ("title", "", "invalid_title"),
        ("title", "x" * 121, "invalid_title"),
        ("output_dir", "relative/dir", "output_dir_unavailable"),
        ("start", "1:99", "invalid_time_range"),
        ("end", "abc", "invalid_time_range"),
    ],
)
def test_invalid_field_maps_to_its_code_and_keeps_the_id(field: str, value: str, code: str) -> None:
    _, messages = run(req("f1", **{field: value}))
    assert len(messages) == 1
    assert (messages[0]["id"], messages[0]["code"]) == ("f1", code)
    assert value not in messages[0]["message"] or value == ""


@pytest.mark.parametrize(
    "body",
    [
        {"v": 1, "id": "m1", "type": "prepare_clip"},
        {"v": 1, "id": "m1", "type": "prepare_clip", "params": {**PARAMS, "extra": 1}},
        {"v": 1, "id": "m1", "type": "prepare_clip", "params": {"url": PARAMS["url"]}},
        {"v": 1, "id": "m1", "type": "nope", "params": PARAMS},
        {"v": 1, "id": "m1", "type": "result"},
        {"id": "m1", "type": "prepare_clip", "params": PARAMS},
        {"v": True, "id": "m1", "type": "prepare_clip", "params": PARAMS},
        {"v": "1", "id": "m1", "type": "prepare_clip", "params": PARAMS},
    ],
)
def test_structurally_invalid_requests_are_invalid_request_with_recovered_id(
    body: dict[str, Any],
) -> None:
    _, messages = run(json.dumps(body).encode() + b"\n")
    assert [(m["id"], m["code"]) for m in messages] == [("m1", "invalid_request")]


@pytest.mark.parametrize("bad_id", [None, 5, "", "x" * 129, ["a"]])
def test_unrecoverable_id_yields_null_id(bad_id: object) -> None:
    _, messages = run(req(bad_id))
    assert [(m["id"], m["code"]) for m in messages] == [(None, "invalid_request")]


def test_blank_lines_are_ignored() -> None:
    _, messages = run(b"\n   \n\t\r\n" + req("b1") + b"\n")
    assert [m["type"] for m in messages] == ["progress", "progress", "result"]


def test_oversized_line_is_rejected_and_the_loop_continues() -> None:
    huge = b'{"id":"big","pad":"' + b"a" * (MAX_LINE_BYTES * 2 + 5) + b'"}\n'
    _, messages = run(huge + req("next"))
    assert (messages[0]["id"], messages[0]["code"]) == (None, "invalid_request")
    assert messages[-1] == {
        "v": 1,
        "id": "next",
        "type": "result",
        "folder": "/out/Song",
        "full_track": "/out/Song/Song.mp3",
        "clip": "/out/Song/0-10_0-20.mp3",
    }


def test_line_of_exactly_the_limit_is_not_rejected_as_too_long() -> None:
    line = b"x" * (MAX_LINE_BYTES - 1) + b"\n"
    _, messages = run(line)
    assert messages[0]["message"] == "Request is not valid JSON"


def test_loop_survives_a_mix_of_good_and_bad_lines_in_order() -> None:
    data = b"junk\n" + req("a") + b"\xff\n" + req("b", url="nope") + req("c")
    _, messages = run(data)
    summary = [(m["id"], m["type"]) for m in messages]
    assert summary == [
        (None, "error"),
        ("a", "progress"),
        ("a", "progress"),
        ("a", "result"),
        (None, "error"),
        ("b", "error"),
        ("c", "progress"),
        ("c", "progress"),
        ("c", "result"),
    ]


def test_each_request_gets_exactly_one_terminal_message() -> None:
    data = b"".join(req(f"r{i}") for i in range(5))
    _, messages = run(data, raiser(CutFailedError("x")))
    terminals = [m for m in messages if m["type"] in {"result", "error"}]
    assert [m["id"] for m in terminals] == [f"r{i}" for i in range(5)]


def test_non_ascii_content_is_utf8_and_valid() -> None:
    _, messages = run(req("é-1", title="Canción ñ"))
    assert messages[-1]["folder"] == "/out/Canción ñ"


def test_unserializable_result_does_not_kill_the_loop() -> None:
    # A lone surrogate survives json.loads but cannot be encoded as UTF-8 output.
    data = (
        b'{"v":1,"id":"s1","type":"prepare_clip","params":'
        + json.dumps({**PARAMS, "title": "a\ud800"}).encode()
        + b"}\n"
    )
    _, messages = run(data + req("s2"))
    assert [(m["id"], m["code"]) for m in messages[:1]] == [("s1", "invalid_request")]
    assert messages[-1]["id"] == "s2"
    assert messages[-1]["type"] == "result"


def test_closed_stdout_stops_the_loop_with_a_failure_code() -> None:
    class Closed(io.BytesIO):
        def write(self, data: Any) -> int:
            raise BrokenPipeError

    code = serve(io.BytesIO(req()), Closed(), lambda p: Handler(p, lambda: None))
    assert code == 1


# --- real entrypoint, in a subprocess ---------------------------------------------------------

CORE = Path(__file__).resolve().parents[1]


def spawn(*args: str, stdin: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "sound_prep_core", *args],
        input=stdin,
        capture_output=True,
        timeout=60,
        cwd=CORE,
        check=False,
    )


@pytest.mark.parametrize("args", [("--x",), ("a", "b"), ("",)])
def test_entrypoint_rejects_any_argv_with_nothing_on_stdout(args: tuple[str, ...]) -> None:
    result = spawn(*args, stdin=req())
    assert result.returncode != 0
    assert result.stdout == b""
    assert result.stderr.strip()


def test_entrypoint_exits_zero_on_stdin_eof() -> None:
    result = spawn()
    assert (result.returncode, result.stdout) == (0, b"")


def test_entrypoint_keeps_stray_prints_off_stdout() -> None:
    code = (
        "import sys, os\n"
        "from sound_prep_core import main as m\n"
        "from sound_prep_core.adapters.ipc.server import InternalError\n"
        "class H:\n"
        "    def execute(self, r):\n"
        "        print('stray'); os.write(1, b'raw fd write\\n'); raise InternalError('x')\n"
        "m.build_handler_factory = lambda env: lambda p: H()\n"
        "sys.exit(m.main([]))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=req("p1"),
        capture_output=True,
        timeout=60,
        cwd=CORE,
        check=False,
    )
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["code"] == "internal_error"
    assert b"stray" in result.stderr


def test_id_with_a_lone_surrogate_is_rejected_up_front_without_side_effects() -> None:
    calls: list[int] = []
    body = b'{"v":1,"id":"\\ud800","type":"prepare_clip","params":' + json.dumps(PARAMS).encode()
    _, messages = run(body + b"}\n", lambda: calls.append(1))
    assert [(m["id"], m["code"]) for m in messages] == [(None, "invalid_request")]
    assert calls == []


def test_result_that_cannot_be_encoded_answers_internal_error_with_the_known_id() -> None:
    class Bad:
        def execute(self, request: PrepareClipRequest) -> OutputLayout:
            raise CutFailedError("bad \ud800")

    out = io.BytesIO()
    serve(io.BytesIO(req("k1") + req("k2")), out, lambda p: Bad())
    messages = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [(m["id"], m["code"]) for m in messages] == [
        ("k1", "internal_error"),
        ("k2", "internal_error"),
    ]
    assert all(VALIDATOR.is_valid(m) for m in messages)


def test_domain_error_with_a_code_outside_the_contract_still_answers_with_the_id() -> None:
    class Odd(CutFailedError):
        code = "not_in_contract"

    _, messages = run(req("o1"), raiser(Odd("x")))
    assert (messages[-1]["id"], messages[-1]["code"]) == ("o1", "internal_error")


def test_field_messages_are_fixed_and_do_not_leak_patterns() -> None:
    for field, value in [("url", "ftp://x"), ("start", "1:99"), ("output_dir", "rel")]:
        _, messages = run(req("m", **{field: value}))
        assert "^" not in messages[0]["message"]
        assert "pattern" not in messages[0]["message"].lower()
