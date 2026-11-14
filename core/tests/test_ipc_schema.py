"""The JSON Schema accepts every valid fixture and rejects every invalid one."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
VALID = sorted((CONTRACTS / "fixtures" / "valid").glob("*.json"))
INVALID = sorted((CONTRACTS / "fixtures" / "invalid").glob("*.json"))
# Per invalid fixture: JSON pointer of the failing instance and the failing keyword.
EXPECTATIONS: dict[str, dict[str, str]] = json.loads(
    (CONTRACTS / "fixtures" / "invalid-expectations.json").read_text(encoding="utf-8")
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = _load(CONTRACTS / "ipc.schema.json")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_fixtures_exist() -> None:
    assert VALID
    assert INVALID


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_fixture_passes(validator: Draft202012Validator, path: Path) -> None:
    assert validator.is_valid(_load(path))


def _pointer(error: ValidationError) -> str:
    return "".join(f"/{part}" for part in error.absolute_path)


def test_every_invalid_fixture_has_an_expectation() -> None:
    assert set(EXPECTATIONS) == {p.name for p in INVALID}


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_fixture_fails_for_the_intended_reason(
    validator: Draft202012Validator, path: Path
) -> None:
    expected = EXPECTATIONS[path.name]
    errors = {(_pointer(e), str(e.validator)) for e in validator.iter_errors(_load(path))}
    assert (expected["path"], expected["keyword"]) in errors


def test_every_type_has_exactly_one_discriminated_branch() -> None:
    schema = _load(CONTRACTS / "ipc.schema.json")
    declared = list(schema["properties"]["type"]["enum"])
    branches = [b["if"]["properties"]["type"]["const"] for b in schema["allOf"]]
    assert sorted(declared) == sorted(branches)
    assert len(set(declared)) == len(declared)
    for branch in schema["allOf"]:
        assert branch["then"]["$ref"].removeprefix("#/$defs/") in schema["$defs"]
