"""``locate_demucs`` tests: it only verifies the executable bit, so plain scripts stand in."""

from pathlib import Path

import pytest

from sound_prep_core.adapters.demucs import (
    DemucsUnavailableError,
    default_candidates,
    locate_demucs,
)


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def _bin(version_dir: Path) -> Path:
    (version_dir / "bin").mkdir(parents=True)
    return version_dir / "bin" / "demucs"


def test_prefers_the_configured_path(tmp_path: Path) -> None:
    demucs = _executable(tmp_path / "demucs")
    assert locate_demucs(configured=demucs, candidates=[]) == demucs


@pytest.mark.parametrize("kind", ["plain", "missing", "relative", "directory", "dangling_link"])
def test_rejects_a_bad_configured_path_without_falling_back(tmp_path: Path, kind: str) -> None:
    good = _executable(tmp_path / "demucs")
    bad = tmp_path / "bad"
    if kind == "plain":
        bad.write_text("x")
        bad.chmod(0o644)
    elif kind == "relative":
        bad = Path("~/bin/demucs")
    elif kind == "directory":
        bad.mkdir()
    elif kind == "dangling_link":
        bad.symlink_to(tmp_path / "nowhere")
    with pytest.raises(DemucsUnavailableError, match="Configured demucs"):
        locate_demucs(configured=bad, candidates=[good])


def test_a_relative_path_error_says_an_absolute_path_is_required() -> None:
    with pytest.raises(DemucsUnavailableError, match="absolute path is required"):
        locate_demucs(configured=Path("~/bin/demucs"), candidates=[])


def test_accepts_a_symlink_to_an_executable(tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(_executable(tmp_path / "real"))
    assert locate_demucs(configured=link) == link


def test_takes_the_first_executable_candidate(tmp_path: Path) -> None:
    good = _executable(tmp_path / "good")
    not_exec = tmp_path / "not-exec"
    not_exec.write_text("x")
    not_exec.chmod(0o644)
    assert locate_demucs(candidates=[tmp_path / "missing", not_exec, good]) == good


def test_fails_listing_what_it_tried(tmp_path: Path) -> None:
    with pytest.raises(DemucsUnavailableError, match="missing"):
        locate_demucs(candidates=[tmp_path / "missing"])


def test_no_candidates_raises() -> None:
    with pytest.raises(DemucsUnavailableError, match="not found"):
        locate_demucs(candidates=[])


def test_default_candidates_list_framework_versions_newest_first(tmp_path: Path) -> None:
    for version in ("3.9", "3.13", "3.10"):
        _executable(_bin(tmp_path / "Versions" / version))
    home = tmp_path / "home"
    found = default_candidates(tmp_path / "Versions", home)
    assert [c.parent.parent.name for c in found[:3]] == ["3.13", "3.10", "3.9"]
    assert found[3:] == [
        Path("/opt/homebrew/bin/demucs"),
        Path("/usr/local/bin/demucs"),
        home / ".local" / "bin" / "demucs",
    ]


def test_default_candidates_are_built_per_call_from_the_given_home(tmp_path: Path) -> None:
    missing = tmp_path / "none"
    assert (
        default_candidates(missing, tmp_path / "a")[-1]
        != default_candidates(missing, tmp_path / "b")[-1]
    )
    assert all(c.is_absolute() for c in default_candidates(missing))


def test_locate_demucs_uses_the_default_candidates_when_none_are_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = _executable(tmp_path / "demucs")
    monkeypatch.setattr(
        "sound_prep_core.adapters.demucs.default_candidates", lambda: [tmp_path / "x", good]
    )
    assert locate_demucs() == good
