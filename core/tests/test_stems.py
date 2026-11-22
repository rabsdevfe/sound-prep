from sound_prep_core.domain.errors import SeparationFailedError
from sound_prep_core.domain.ports import ProgressStage
from sound_prep_core.domain.stems import Stem


def test_stems_are_the_five_contract_names_in_order() -> None:
    assert [s.value for s in Stem] == ["drums", "bass", "vocals", "guitar", "other"]
    assert [s.filename for s in Stem] == [f"{s.value}.wav" for s in Stem]


def test_separation_error_and_stage_match_the_ipc_contract() -> None:
    assert SeparationFailedError.code == "separation_failed"
    assert ProgressStage.SEPARATING.value == "separating"
