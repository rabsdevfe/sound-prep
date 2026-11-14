from dataclasses import replace

import pytest

from sound_prep_core.domain.errors import DomainError, InvalidTimeRangeError
from sound_prep_core.domain.time_range import MAX_SECONDS, ClipTime, TimeRange


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("0", 0),
        ("05", 5),
        ("90", 90),
        ("1:30", 90),
        ("01:30", 90),
        ("90:00", 5400),
        ("0:59", 59),
        ("1:02:03", 3723),
        ("23:59:59", 86399),
    ],
)
def test_parses_every_format(text: str, seconds: int) -> None:
    parsed = ClipTime.parse(text)
    assert parsed.seconds == seconds
    assert parsed.text == text


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        " 5",
        "5 ",
        "5\n",
        "1:30\n",
        "-5",
        "+5",
        "1.5",
        "1:5",
        "1:60",
        "1:2:3",
        "1:00:60",
        "1:60:00",
        ":30",
        "1:",
        "1::30",
        "1:00:00:00",
        "a",
        "1:3a",
        "١٢",  # Arabic-Indic digits
    ],
)
def test_rejects_invalid_neighbors(text: str) -> None:
    with pytest.raises(InvalidTimeRangeError):
        ClipTime.parse(text)


@pytest.mark.parametrize("seconds", [0, 1, 59, 60, 61, 3599, 3600, 3661, 86399, MAX_SECONDS])
def test_time_round_trips_through_seconds(seconds: int) -> None:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    assert ClipTime.parse(f"{h}:{m:02d}:{s:02d}").seconds == seconds


def test_limit_boundary() -> None:
    assert ClipTime.parse("24:00:00").seconds == MAX_SECONDS
    assert ClipTime.parse("86400").seconds == MAX_SECONDS
    for text in ("24:00:01", "86401", "1440:01"):
        with pytest.raises(InvalidTimeRangeError):
            ClipTime.parse(text)


@pytest.mark.parametrize("text", ["9" * 5000, "9" * 33, "0" * 5000, "1:" + "9" * 5000 + ":00"])
def test_huge_values_raise_domain_error(text: str) -> None:
    with pytest.raises(InvalidTimeRangeError):
        ClipTime.parse(text)


def test_range_exposes_duration_and_stem() -> None:
    rng = TimeRange.parse("1:30", "2:15")
    assert rng.duration_seconds == 45
    assert rng.file_stem == "1-30_2-15"


@pytest.mark.parametrize(
    ("start", "end", "stem"),
    [
        ("5", "10", "5_10"),
        ("0:05", "1:00:00", "0-05_1-00-00"),
        ("01:30", "02:15", "01-30_02-15"),
    ],
)
def test_file_stem_replaces_colons_and_keeps_typed_text(start: str, end: str, stem: str) -> None:
    assert TimeRange.parse(start, end).file_stem == stem


@pytest.mark.parametrize(("start", "end"), [("10", "10"), ("1:00", "59"), ("2:00", "1:00")])
def test_end_must_be_after_start(start: str, end: str) -> None:
    with pytest.raises(InvalidTimeRangeError):
        TimeRange.parse(start, end)


def test_equal_instants_in_different_formats_are_rejected() -> None:
    with pytest.raises(InvalidTimeRangeError):
        TimeRange.parse("60", "1:00")


def test_invalid_end_is_reported_as_time_error() -> None:
    with pytest.raises(InvalidTimeRangeError):
        TimeRange.parse("0", "x")


def test_error_is_a_domain_error_with_contract_code() -> None:
    err = InvalidTimeRangeError("boom")
    assert isinstance(err, DomainError)
    assert err.code == "invalid_time_range"


@pytest.mark.parametrize("text", ["", "x", "1:60", "86401", "9" * 5000])
def test_clip_time_cannot_be_constructed_invalid(text: str) -> None:
    with pytest.raises(InvalidTimeRangeError):
        ClipTime(text)


def test_clip_time_seconds_is_derived_not_settable() -> None:
    with pytest.raises(TypeError):
        ClipTime("1:00", 5)  # type: ignore[call-arg]
    assert ClipTime("1:00").seconds == 60


def test_range_cannot_be_constructed_unordered() -> None:
    with pytest.raises(InvalidTimeRangeError):
        TimeRange(ClipTime("2"), ClipTime("1"))


def test_replace_revalidates_clip_time() -> None:
    with pytest.raises(InvalidTimeRangeError):
        replace(ClipTime("1:00"), text="x")
    assert replace(ClipTime("1:00"), text="2:00").seconds == 120
