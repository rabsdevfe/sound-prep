from dataclasses import replace
from pathlib import PurePosixPath

import pytest

from sound_prep_core.domain.errors import (
    DomainError,
    InvalidTitleError,
    OutputDirUnavailableError,
)
from sound_prep_core.domain.layout import OutputLayout, StemsLayout
from sound_prep_core.domain.stems import Stem
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
        "a\ud800b",  # lone surrogate
        "a\u200bb",  # zero-width space
        "a\u202eb",  # right-to-left override
        "a\u2066b",  # bidi isolate
        "a\ufeffb",  # BOM / zero-width no-break space
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


def test_title_is_nfc_normalized() -> None:
    decomposed = "Sen" + "n" + "\u0303" + "or"  # n + combining tilde
    assert Title.parse(decomposed).name == "Sen\u00f1or"
    assert Title("e\u0301").name == "\u00e9"


def test_title_cannot_be_constructed_unsafe() -> None:
    with pytest.raises(InvalidTitleError):
        Title(".hidden")
    with pytest.raises(InvalidTitleError):
        Title("")
    assert Title("a/b").name == "a-b"


@pytest.mark.parametrize(
    "bad",
    [
        "/out\nx",
        "/out\x00",
        "/out\x1b[0m",
        "/out\u2028x",
        "/out\u2029x",
        "/out\ud800x",
        "/out\u200bx",
    ],
)
def test_output_dir_rejects_control_characters(bad: str) -> None:
    with pytest.raises(OutputDirUnavailableError, match="control"):
        OutputLayout.compute(bad, Title.parse("t"), TimeRange.parse("1", "2"))


def test_output_dir_error_messages_are_specific() -> None:
    with pytest.raises(OutputDirUnavailableError, match="absolute"):
        OutputLayout.compute("rel", Title.parse("t"), TimeRange.parse("1", "2"))
    with pytest.raises(OutputDirUnavailableError, match=r"'\.\.'") as info:
        OutputLayout.compute("/a/../b", Title.parse("t"), TimeRange.parse("1", "2"))
    assert "absolute" not in str(info.value)


def test_replace_revalidates_title_and_is_idempotent() -> None:
    with pytest.raises(InvalidTitleError):
        replace(Title("ok"), name=".hidden")
    assert replace(Title("ok"), name="a/b").name == "a-b"
    title = Title("  AC/DC: x  ")
    assert Title(title.name) == title


def test_layout_cannot_be_constructed_invalid() -> None:
    p = PurePosixPath
    rng = TimeRange.parse("1", "2")
    assert OutputLayout(p("/o/t"), rng).clip == p("/o/t/1_2.mp3")
    for bad in ("o/t", "/o/../t", "/", "/o/.hidden", "/o/a\x00b", "/o/a\u200bb", "/o/\ud800"):
        with pytest.raises(OutputDirUnavailableError):
            OutputLayout(p(bad), rng)
    with pytest.raises(InvalidTitleError):
        OutputLayout(p("/o/1_2"), rng)


def test_layout_derives_file_paths_from_folder() -> None:
    layout = OutputLayout(PurePosixPath("/o/t"), TimeRange.parse("1", "2"))
    assert layout.full_track == PurePosixPath("/o/t/t.mp3")
    assert layout.clip.parent == layout.full_track.parent == layout.folder


def test_layout_nfc_normalizes_output_dir() -> None:
    rng = TimeRange.parse("1", "2")
    expected = PurePosixPath("/m/caf\u00e9/t")
    assert OutputLayout.compute("/m/cafe\u0301", Title("t"), rng).folder == expected
    assert OutputLayout(PurePosixPath("/m/cafe\u0301/t"), rng).folder == expected


def test_stems_layout_puts_the_stems_under_the_title_folder() -> None:
    layout = StemsLayout.compute("/out", Title("Song"))
    assert layout.full_track == PurePosixPath("/out/Song/Song.mp3")
    assert layout.stem(Stem.DRUMS) == PurePosixPath("/out/Song/stems/drums.wav")
    with pytest.raises(OutputDirUnavailableError):
        StemsLayout.compute("relative", Title("Song"))
