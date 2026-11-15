import tomllib
from pathlib import Path

import sound_prep_core

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_exposes_installed_version() -> None:
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    assert sound_prep_core.__version__ == declared
