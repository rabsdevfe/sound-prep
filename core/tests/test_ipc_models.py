"""The pydantic models agree with the JSON Schema (used as the oracle) and share its limits."""

import copy
import json
import typing
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from sound_prep_core.adapters.ipc import (
    MESSAGE_MODELS,
    ErrorCode,
    ErrorMessage,
    IpcMessage,
    ProgressEvent,
    Stage,
    messages,
    parse_message,
    to_line,
)

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
VALID = sorted((CONTRACTS / "fixtures" / "valid").glob("*.json"))
INVALID = sorted((CONTRACTS / "fixtures" / "invalid").glob("*.json"))
SCHEMA: dict[str, Any] = json.loads((CONTRACTS / "ipc.schema.json").read_text(encoding="utf-8"))
EXPECTATIONS: dict[str, dict[str, str]] = json.loads(
    (CONTRACTS / "fixtures" / "invalid-expectations.json").read_text(encoding="utf-8")
)
ORACLE = Draft202012Validator(SCHEMA)
DEFS = SCHEMA["$defs"]
PARAMS = DEFS["PrepareClipRequest"]["properties"]["params"]["properties"]


def _accepts(document: Any) -> bool:
    try:
        parse_message(json.dumps(document))
    except ValidationError:
        return False
    return True


def _model_paths(error: ValidationError) -> set[str]:
    """JSON pointers of the failing instances, aligned with how the schema reports them."""
    paths: set[str] = set()
    for item in error.errors():
        loc = list(item["loc"])
        kind = item["type"]
        if kind == "union_tag_invalid":
            loc = ["type"]
        elif kind in {"union_tag_not_found", "dict_type"}:
            loc = []
        else:
            loc = loc[1:]  # drop the discriminator tag
            if kind in {"missing", "extra_forbidden"}:
                loc = loc[:-1]  # the schema reports these on the object itself
        paths.add("".join(f"/{part}" for part in loc))
    return paths


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_fixture_is_accepted(path: Path) -> None:
    parse_message(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_to_line_round_trips_and_satisfies_the_schema(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    emitted = json.loads(to_line(parse_message(text)))
    assert emitted == json.loads(text)
    assert ORACLE.is_valid(emitted)


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_fixture_is_rejected_at_the_expected_path(path: Path) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_message(path.read_text(encoding="utf-8"))
    assert EXPECTATIONS[path.name]["path"] in _model_paths(caught.value)


def _mutations(document: Any) -> list[Any]:
    """Deterministic mutants of a valid message: remove, replace or extend each node."""
    replacements: list[Any] = [
        None, 0, 1, 1.0, -1, 1.5, 100, 101, True, False, "", "x", "10", "00:30", "1:60",
        "/abs", "https://x", "x" * 120, "x" * 121, "x" * 128, "x" * 129, [], {}, ["a"], {"a": 1},
    ]  # fmt: skip
    mutants: list[Any] = []

    def walk(node: Any, trail: list[str | int]) -> None:
        def at(new: Any) -> Any:
            root = copy.deepcopy(document)
            if not trail:
                return new
            target = root
            for key in trail[:-1]:
                target = target[key]
            target[trail[-1]] = new
            return root

        for replacement in replacements:
            mutants.append(at(replacement))
        if isinstance(node, dict):
            extended = copy.deepcopy(node)
            extended["extra"] = 1
            mutants.append(at(extended))
            for key, value in node.items():
                reduced = {k: v for k, v in node.items() if k != key}
                mutants.append(at(reduced))
                walk(value, [*trail, key])

    walk(document, [])
    return mutants


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_models_accept_exactly_what_the_schema_accepts(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    for mutant in _mutations(document):
        assert _accepts(mutant) == ORACLE.is_valid(mutant), json.dumps(mutant)


def test_progress_percent_is_absent_or_a_number() -> None:
    with pytest.raises(ValidationError):
        ProgressEvent(v=1, id="a", type="progress", stage="cutting", percent=None)
    assert "percent" not in json.loads(
        to_line(ProgressEvent(v=1, id="a", type="progress", stage="cutting"))
    )


def test_error_null_id_serializes_as_null() -> None:
    line = to_line(ErrorMessage(v=1, id=None, type="error", code="invalid_request", message="x"))
    assert json.loads(line)["id"] is None


def test_enums_match_the_schema() -> None:
    assert set(typing.get_args(ErrorCode)) == set(DEFS["ErrorCode"]["enum"])
    stage = DEFS["ProgressEvent"]["properties"]["stage"]["enum"]
    assert set(typing.get_args(Stage)) == set(stage)


def _progress(percent: float) -> dict[str, Any]:
    return {"v": 1, "id": "a", "type": "progress", "stage": "cutting", "percent": percent}


def test_numeric_and_length_bounds_match_the_schema() -> None:
    percent = DEFS["ProgressEvent"]["properties"]["percent"]
    lo, hi = percent["minimum"], percent["maximum"]
    for value, expected in [(lo, True), (hi, True), (lo - 0.01, False), (hi + 0.01, False)]:
        assert _accepts(_progress(value)) is expected

    id_max = DEFS["MessageId"]["maxLength"]
    title_max = PARAMS["title"]["maxLength"]
    request = json.loads((CONTRACTS / "fixtures/valid/prepare_clip_request.json").read_text())
    for length, expected in [(id_max, True), (id_max + 1, False)]:
        assert _accepts({**request, "id": "x" * length}) is expected
    for length, expected in [(title_max, True), (title_max + 1, False)]:
        params = {**request["params"], "title": "x" * length}
        assert _accepts({**request, "params": params}) is expected


def test_patterns_match_the_schema() -> None:
    assert DEFS["ClipTime"]["pattern"] == messages.CLIP_TIME_PATTERN
    assert DEFS["AbsolutePath"]["pattern"] == messages.ABSOLUTE_PATH_PATTERN
    assert PARAMS["url"]["pattern"] == messages.URL_PATTERN


def test_each_message_type_maps_to_its_model() -> None:
    assert set(MESSAGE_MODELS) == set(SCHEMA["properties"]["type"]["enum"])
    for name, model in MESSAGE_MODELS.items():
        assert typing.get_args(model.model_fields["type"].annotation) == (name,)
    union = typing.get_args(typing.get_args(IpcMessage)[0])
    assert set(union) == set(MESSAGE_MODELS.values())
