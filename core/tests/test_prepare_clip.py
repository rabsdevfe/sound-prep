from pathlib import PurePosixPath

import pytest

from sound_prep_core.domain.errors import (
    CutFailedError,
    DownloadFailedError,
    InvalidTimeRangeError,
    InvalidTitleError,
    InvalidUrlError,
    OutputDirUnavailableError,
)
from sound_prep_core.domain.ports import ProgressStage
from sound_prep_core.domain.time_range import TimeRange
from sound_prep_core.use_cases.prepare_clip import PrepareClip, PrepareClipRequest

P = PurePosixPath
FULL = P("/out/Song/Song.mp3")
CLIP = P("/out/Song/1-30_2-15.mp3")


class World:
    """Fake downloader, cutter, filesystem and reporter sharing one event log.

    Files map to a modification stamp. ``writes`` logs every publication, so tests can assert what
    was written where. Downloads and cuts go through a temporary ``.part`` name and are published
    by rename, like real adapters must.
    """

    def __init__(self, existing: set[PurePosixPath] | None = None) -> None:
        self.clock = 0
        self.files: dict[PurePosixPath, int] = {}
        for path in existing or ():
            self._touch(path)
        self.events: list[str] = []
        self.writes: list[PurePosixPath] = []
        self.download_error: BaseException | None = None
        self.cut_error: BaseException | None = None
        self.mkdir_error: BaseException | None = None
        self.exists_error: BaseException | None = None
        self.stamp_error: BaseException | None = None
        self.report_error: BaseException | None = None
        self.interrupt_download = False
        self.download_creates = True
        self.cut_creates = True

    def _touch(self, path: PurePosixPath) -> None:
        self.clock += 1
        self.files[path] = self.clock

    @staticmethod
    def _temp(path: PurePosixPath) -> PurePosixPath:
        return path.with_name(path.name + ".part")

    def download(self, url: str, destination: PurePosixPath) -> None:
        self.events.append(f"download {url} {destination}")
        if self.download_error:
            raise self.download_error
        self._touch(self._temp(destination))
        if self.interrupt_download:
            raise OSError("connection lost")  # leaves the partial temp file behind
        if self.download_creates:
            del self.files[self._temp(destination)]
            self._touch(destination)
            self.writes.append(destination)

    def cut(self, source: PurePosixPath, destination: PurePosixPath, time_range: TimeRange) -> None:
        self.events.append(f"cut {source} {destination} {time_range.file_stem}")
        if self.cut_error:
            raise self.cut_error
        if self.cut_creates:
            self._touch(destination)
            self.writes.append(destination)

    def exists(self, path: PurePosixPath) -> bool:
        if self.exists_error:
            raise self.exists_error
        return path in self.files

    def stamp(self, path: PurePosixPath) -> int | None:
        if self.stamp_error:
            raise self.stamp_error
        return self.files.get(path)

    def make_dir(self, path: PurePosixPath) -> None:
        self.events.append(f"mkdir {path}")
        if self.mkdir_error:
            raise self.mkdir_error

    def report(self, stage: ProgressStage, percent: int | None = None) -> None:
        self.events.append(f"progress {stage.value}")
        if self.report_error:
            raise self.report_error

    def use_case(self) -> PrepareClip:
        return PrepareClip(self, self, self, self)


def request(**overrides: str) -> PrepareClipRequest:
    fields = {
        "url": "https://www.youtube.com/watch?v=abc",
        "title": "Song",
        "output_dir": "/out",
        "start": "1:30",
        "end": "2:15",
    }
    return PrepareClipRequest(**{**fields, **overrides})


def test_happy_path_downloads_then_cuts_and_returns_paths() -> None:
    world = World()
    layout = world.use_case().execute(request())
    assert (layout.folder, layout.full_track, layout.clip) == (P("/out/Song"), FULL, CLIP)
    assert world.events == [
        "mkdir /out/Song",
        "progress downloading",
        "download https://www.youtube.com/watch?v=abc /out/Song/Song.mp3",
        "progress cutting",
        "cut /out/Song/Song.mp3 /out/Song/1-30_2-15.mp3 1-30_2-15",
    ]
    assert set(world.files) == {FULL, CLIP}
    assert world.writes == [FULL, CLIP]


def test_existing_full_track_is_reused_without_download() -> None:
    world = World({FULL})
    world.use_case().execute(request())
    assert not any(e.startswith(("download", "progress downloading")) for e in world.events)
    assert [e for e in world.events if e.startswith("progress")] == ["progress cutting"]
    assert CLIP in world.files


def test_existing_clip_is_recut_and_full_track_untouched() -> None:
    world = World({FULL, CLIP})
    full_stamp, clip_stamp = world.files[FULL], world.files[CLIP]
    world.use_case().execute(request())
    assert world.writes == [CLIP]  # the cutter really wrote the clip, nothing else
    assert world.files[CLIP] > clip_stamp
    assert world.files[FULL] == full_stamp


def test_cutter_that_silently_leaves_a_stale_clip_is_a_cut_failure() -> None:
    world = World({FULL, CLIP})
    world.cut_creates = False
    with pytest.raises(CutFailedError):
        world.use_case().execute(request())


def test_full_track_is_never_a_cut_destination_or_overwritten() -> None:
    for existing in (set(), {FULL}, {FULL, CLIP}):
        world = World(existing)
        had_track = FULL in existing
        world.use_case().execute(request())
        assert world.writes.count(FULL) == (0 if had_track else 1)
        assert not any(e.startswith("cut") and e.split()[2] == str(FULL) for e in world.events)


def test_interrupted_download_leaves_no_track_and_next_run_downloads_again() -> None:
    world = World()
    world.interrupt_download = True
    with pytest.raises(DownloadFailedError) as info:
        world.use_case().execute(request())
    assert isinstance(info.value.__cause__, OSError)
    assert FULL not in world.files  # only the temporary name remains
    assert P("/out/Song/Song.mp3.part") in world.files
    assert not any(e.startswith("cut") for e in world.events)

    world.interrupt_download = False
    world.events.clear()
    world.use_case().execute(request())
    assert any(e.startswith("download") for e in world.events)
    assert FULL in world.files


def test_temporary_file_is_never_taken_for_the_track() -> None:
    world = World({P("/out/Song/Song.mp3.part")})
    world.use_case().execute(request())
    assert any(e.startswith("download") for e in world.events)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"start": "x"}, InvalidTimeRangeError),
        ({"start": "2:00", "end": "1:00"}, InvalidTimeRangeError),
        ({"title": ".hidden"}, InvalidTitleError),
        ({"title": "5_10", "start": "5", "end": "10"}, InvalidTitleError),
        ({"url": "ftp://x/y"}, InvalidUrlError),
        ({"url": "not a url"}, InvalidUrlError),
        ({"url": "https://"}, InvalidUrlError),
        ({"url": "http://[::1"}, InvalidUrlError),
        ({"url": "https://[abc/x"}, InvalidUrlError),
        ({"url": "https://a\uff0f@b.com"}, InvalidUrlError),
        ({"url": "https://exa\u2100mple.com/x"}, InvalidUrlError),
        ({"url": "https://a.com:0/x"}, InvalidUrlError),
        ({"url": "https://a.com:65536/x"}, InvalidUrlError),
        ({"url": "https://a.com:abc/x"}, InvalidUrlError),
        ({"url": "https://a.com/\nb"}, InvalidUrlError),
        ({"output_dir": "relative"}, OutputDirUnavailableError),
    ],
)
def test_invalid_input_raises_before_any_side_effect(
    overrides: dict[str, str], error: type[Exception]
) -> None:
    world = World()
    with pytest.raises(error):
        world.use_case().execute(request(**overrides))
    assert world.events == []


def test_output_dir_error_propagates_and_nothing_else_runs() -> None:
    world = World()
    world.mkdir_error = OutputDirUnavailableError("read-only")
    with pytest.raises(OutputDirUnavailableError):
        world.use_case().execute(request())
    assert world.events == ["mkdir /out/Song"]


@pytest.mark.parametrize(
    ("attribute", "error"),
    [
        ("download_error", DownloadFailedError),
        ("cut_error", CutFailedError),
        ("mkdir_error", OutputDirUnavailableError),
        ("exists_error", OutputDirUnavailableError),
        ("stamp_error", OutputDirUnavailableError),
    ],
)
def test_non_domain_port_exceptions_are_mapped_per_step_with_cause(
    attribute: str, error: type[Exception]
) -> None:
    world = World()
    cause = OSError("disk on fire")
    setattr(world, attribute, cause)
    with pytest.raises(error) as info:
        world.use_case().execute(request())
    assert info.value.__cause__ is cause


def test_domain_errors_from_ports_pass_through_unchanged() -> None:
    world = World()
    original = OutputDirUnavailableError("read-only")
    world.download_error = original
    with pytest.raises(OutputDirUnavailableError) as info:
        world.use_case().execute(request())
    assert info.value is original


def test_keyboard_interrupt_is_not_swallowed() -> None:
    world = World()
    world.download_error = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        world.use_case().execute(request())


def test_failing_progress_reporter_does_not_abort_the_job() -> None:
    world = World()
    world.report_error = RuntimeError("ui gone")
    layout = world.use_case().execute(request())
    assert layout.clip in world.files
    assert [e for e in world.events if e.startswith("progress")] == [
        "progress downloading",
        "progress cutting",
    ]


def test_download_error_propagates_without_cutting() -> None:
    world = World()
    world.download_error = DownloadFailedError("boom")
    with pytest.raises(DownloadFailedError):
        world.use_case().execute(request())
    assert not any(e.startswith(("cut", "progress cutting")) for e in world.events)


def test_download_that_produces_no_file_is_a_download_failure() -> None:
    world = World()
    world.download_creates = False
    with pytest.raises(DownloadFailedError):
        world.use_case().execute(request())
    assert not any(e.startswith("cut") for e in world.events)


def test_cut_error_propagates_and_keeps_the_full_track() -> None:
    world = World()
    world.cut_error = CutFailedError("boom")
    with pytest.raises(CutFailedError):
        world.use_case().execute(request())
    assert FULL in world.files


def test_download_target_is_always_the_full_track_never_the_clip() -> None:
    world = World()
    world.use_case().execute(request())
    downloads = [e for e in world.events if e.startswith("download")]
    assert [d.split()[-1] for d in downloads] == [str(FULL)]
