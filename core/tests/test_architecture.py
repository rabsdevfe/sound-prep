import ast
from pathlib import Path

import sound_prep_core

ROOT = Path(sound_prep_core.__file__).parent
FORBIDDEN = (
    "sound_prep_core.adapters",
    "pydantic",
    "yt_dlp",
    "ffmpeg",
    "subprocess",
    "requests",
    "os",
    "shutil",
)


def _imported_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # Also catch `from sound_prep_core import adapters`.
            names += [module, *(f"{module}.{a.name}" for a in node.names)]
    return names


def _is_forbidden(name: str) -> bool:
    return any(name == f or name.startswith(f + ".") for f in FORBIDDEN)


def test_domain_and_use_cases_import_no_adapters_or_io_libraries() -> None:
    files = [*(ROOT / "domain").rglob("*.py"), *(ROOT / "use_cases").rglob("*.py")]
    assert files
    for file in files:
        for name in _imported_names(ast.parse(file.read_text())):
            assert not _is_forbidden(name), f"{file.name} imports {name}"


def test_import_scanner_catches_the_known_escape_routes() -> None:
    for source in (
        "from sound_prep_core import adapters",
        "from sound_prep_core.adapters.ipc import messages",
        "import os",
        "from os import path",
        "import shutil",
        "from subprocess import run",
        "import pydantic.v1",
    ):
        assert any(_is_forbidden(n) for n in _imported_names(ast.parse(source))), source
    assert not any(_is_forbidden(n) for n in _imported_names(ast.parse("from pathlib import Path")))
