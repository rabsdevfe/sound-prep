from pathlib import PurePosixPath

import pytest

from sound_prep_core.domain.errors import (
    DomainError,
    InvalidTitleError,
    OutputDirUnavailableError,
)
from sound_prep_core.domain.layout import OutputLayout
from sound_prep_core.domain.time_range import TimeRange
from sound_prep_core.domain.title import MAX_NAME_BYTES, Title


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("Song", "Song"),
        ("  Song  name \t", "Song  name"),
        ("AC/DC: Back in Black", "AC-DC- Back in Black"),
        ("a/b/c", "a-b-c"),
        ("a:b", "a-b"),
        ("/", "-"),
        ("Señor ñandú 音楽", "Señor ñandú 音楽"),
        ("a.b.", "a.b."),
        ("x" * MAX_NAME_BYTES, "x" * MAX_NAME_BYTES),
    ],
)
def test_valid_titles_are_neutralized(raw: str, name: str) -> None:
    assert Title.parse(raw).name == name


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "\t\n",
        ".",
        "..",
        ".hidden",
        "  .hidden",
        "../evil",
        "a\x00b",
        "a\nb",
        "a\tb",
        "a\x7fb",
        "a" + chr(0x2028) + "b",
        "a" + chr(0x2029) + "b",
        "a\x1bb",
        "x" * (MAX_NAME_BYTES + 1),
        "é" * (MAX_NAME_BYTES // 2 + 1),
    ],
)
def test_unsafe_titles_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidTitleError):
        Title.parse(raw)


def test_title_error_code() -> None:
    err = InvalidTitleError("x")
    assert isinstance(err, DomainError)
    assert err.code == "invalid_title"


def test_layout_paths() -> None:
    layout = OutputLayout.compute(
        "/Users/me/Music", Title.parse("My Song"), TimeRange.parse("1:30", "2:15")
    )
    assert layout.folder == PurePosixPath("/Users/me/Music/My Song")
    assert layout.full_track == PurePosixPath("/Users/me/Music/My Song/My Song.mp3")
    assert layout.clip == PurePosixPath("/Users/me/Music/My Song/1-30_2-15.mp3")


def test_layout_uses_neutralized_title_and_normalizes_trailing_slash() -> None:
    layout = OutputLayout.compute("/out/", Title.parse("a/b"), TimeRange.parse("5", "10"))
    assert layout.full_track == PurePosixPath("/out/a-b/a-b.mp3")
    assert layout.clip == PurePosixPath("/out/a-b/5_10.mp3")


def test_title_matching_the_clip_name_is_rejected_to_protect_the_full_track() -> None:
    with pytest.raises(InvalidTitleError):
        OutputLayout.compute("/out", Title.parse("5_10"), TimeRange.parse("5", "10"))
    with pytest.raises(InvalidTitleError):
        OutputLayout.compute("/out", Title.parse("1:30_2:15"), TimeRange.parse("1:30", "2:15"))


@pytest.mark.parametrize("output_dir", ["", "relative/dir", "~/Music", "/a/../b", "/.."])
def test_output_dir_must_be_absolute_without_parent_refs(output_dir: str) -> None:
    with pytest.raises(OutputDirUnavailableError) as info:
        OutputLayout.compute(output_dir, Title.parse("t"), TimeRange.parse("1", "2"))
    assert info.value.code == "output_dir_unavailable"
