"""``SeparateStems`` with in-memory fakes for every port."""

from collections.abc import Callable
from pathlib import PurePosixPath

import pytest

from sound_prep_core.domain.errors import (
    DownloadFailedError,
    InvalidUrlError,
    SeparationFailedError,
)
from sound_prep_core.domain.layout import StemsLayout
from sound_prep_core.domain.ports import ProgressStage
from sound_prep_core.domain.stems import Stem
from sound_prep_core.use_cases.separate_stems import SeparateStems, SeparateStemsRequest

TRACK = PurePosixPath("/out/Song/Song.mp3")
STEMS = PurePosixPath("/out/Song/stems")
URL = "https://www.youtube.com/watch?v=abc"


class World:
    """Downloader, separator, filesystem and reporter in one recording fake."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.files: dict[PurePosixPath, int] = {}
        self.clock = 0
        self.writes_nothing = False
        self.percents: list[int] = []
        self.separate_error: Exception | None = None
        self.skip_stem: Stem | None = None
        self.report_error: Exception | None = None

    def download(self, url: str, destination: PurePosixPath) -> None:
        self.events.append(f"download {url}")
        self.files[destination] = self._tick()

    def _tick(self) -> int:
        self.clock += 1
        return self.clock

    def separate(
        self, source: PurePosixPath, destination: PurePosixPath, on_percent: Callable[[int], None]
    ) -> None:
        self.events.append(f"separate {source} {destination}")
        on_percent(10)
        on_percent(100)
        if self.separate_error:
            raise self.separate_error
        if not self.writes_nothing:
            for s in Stem:
                if s is not self.skip_stem:
                    self.files[destination / s.filename] = self._tick()

    def exists(self, path: PurePosixPath) -> bool:
        return path in self.files

    def stamp(self, path: PurePosixPath) -> int | None:
        return self.files.get(path)

    def make_dir(self, path: PurePosixPath) -> None:
        self.events.append(f"mkdir {path}")

    def report(self, stage: ProgressStage, percent: int | None = None) -> None:
        self.events.append(f"progress {stage.value} {percent}")
        if percent is not None:
            self.percents.append(percent)
        if self.report_error:
            raise self.report_error

    def run(self, url: str = URL) -> StemsLayout:
        return SeparateStems(self, self, self, self).execute(
            SeparateStemsRequest(url, "Song", "/out")
        )


def test_downloads_then_separates_reporting_percent_in_order() -> None:
    world = World()
    layout = world.run()
    assert world.events == [
        "mkdir /out/Song",
        "progress downloading None",
        f"download {URL}",
        "progress separating None",
        f"separate {TRACK} {STEMS}",
        "progress separating 10",
        "progress separating 100",
    ]
    assert layout.stem(Stem.GUITAR) == STEMS / "guitar.wav"


def test_an_existing_track_is_reused_and_stems_are_replaced_on_rerun() -> None:
    world = World()
    world.files[TRACK] = 1
    world.run()
    world.run()
    assert not any(e.startswith(("download", "progress downloading")) for e in world.events)
    assert sum(e.startswith("separate") for e in world.events) == 2


def test_a_missing_stem_file_is_a_separation_failure() -> None:
    world = World()
    world.skip_stem = Stem.OTHER
    with pytest.raises(SeparationFailedError, match="other"):
        world.run()


def test_stems_left_untouched_by_the_separator_are_a_failure() -> None:
    world = World()
    world.run()
    world.writes_nothing = True  # the previous run's stems stay in place
    with pytest.raises(SeparationFailedError, match="drums"):
        world.run()


def test_non_domain_separator_errors_become_separation_failed_keeping_the_cause() -> None:
    world = World()
    world.separate_error = OSError("disk full")
    with pytest.raises(SeparationFailedError, match="disk full") as info:
        world.run()
    assert isinstance(info.value.__cause__, OSError)


def test_a_domain_error_from_the_separator_is_kept_and_a_bad_url_never_reaches_it() -> None:
    world = World()
    world.separate_error = DownloadFailedError("kept")
    with pytest.raises(DownloadFailedError):
        world.run()
    with pytest.raises(InvalidUrlError):
        World().run("not a url")


def test_a_failing_reporter_does_not_abort_the_job() -> None:
    world = World()
    world.report_error = RuntimeError("ui gone")
    world.run()
    assert world.percents == [10, 100]  # percent callbacks kept flowing
    assert Stem.OTHER.filename in {p.name for p in world.files}
