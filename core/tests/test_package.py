import sound_prep_core


def test_exposes_installed_version() -> None:
    assert sound_prep_core.__version__ == "0.1.0"
