"""Build the frozen sidecar in the signable onedir layout of ADR 0001.

Run from ``core/``: ``uv run python packaging/build_sidecar.py [--out DIR]``. macOS arm64 only
(PyInstaller does not cross-compile). Output, by default ``apps/desktop/src-tauri/binaries``
(gitignored; the path Tauri's ``externalBin: ["binaries/core"]`` resolves):

- ``core-aarch64-apple-darwin``: the launcher; Tauri copies it to ``Contents/MacOS/core``.
- ``fw/``: code only (dylibs, ``Python.framework``, symlinks); maps to ``Contents/Frameworks``.
- ``res/``: data (``base_library.zip``, ``python3.X/``); maps to ``Contents/Resources/pyi``.

Modules are not hard-coded: every runtime dependency declared in ``pyproject.toml`` and the whole
``sound_prep_core`` package are collected with ``--collect-submodules``, ``--collect-data`` and
``--copy-metadata`` (dev-group tools are excluded), so a dependency added later (for example
yt-dlp, which imports its extractors dynamically) is picked up automatically.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
TRIPLE = "aarch64-apple-darwin"
DEFAULT_OUT = CORE.parent / "apps" / "desktop" / "src-tauri" / "binaries"
MARKER = ".sound-prep-sidecar"
#: Build tooling and dev-only submodules that must never ship. The build excludes them and fails if
#: one still shows up in the output (the smoke test repeats the file-tree check).
BUILD_ONLY = (
    "setuptools",
    "pkg_resources",
    "_distutils_hack",
    "pydantic.mypy",
    "pydantic.experimental",
    "mypy",
    "PyInstaller",
    "altgraph",
    "macholib",
    "pyinstaller_hooks_contrib",
)


def forbidden_in_tree(root: Path) -> list[str]:
    """Paths under ``root`` that are build-only modules (or dist-info of build-only packages)."""
    found = []
    for path in root.rglob("*"):
        parts = list(path.relative_to(root).parts)
        if parts[0].endswith(".dist-info"):
            parts[0] = parts[0].removesuffix(".dist-info").rsplit("-", 1)[0].replace("-", "_")
        parts[-1] = parts[-1].split(".")[0]  # drop .py / .cpython-313-darwin.so
        if any(parts[: len(bad.split("."))] == bad.split(".") for bad in BUILD_ONLY):
            found.append(str(path.relative_to(root)))
    return found


def _modules_of(requirements: list[str]) -> set[str]:
    owners: dict[str, set[str]] = {}
    for module, dists in packages_distributions().items():
        for dist in dists:
            owners.setdefault(_normalize(dist), set()).add(module)
    modules: set[str] = set()
    for requirement in requirements:
        match = re.match(r"[A-Za-z0-9_.-]+", requirement.strip())
        name = _normalize(match.group(0)) if match else ""
        if not owners.get(name):
            raise SystemExit(f"cannot find the import name of dependency {name!r}; run `uv sync`")
        modules |= owners[name]
    return modules


def module_sets() -> tuple[list[str], list[str]]:
    """Modules to collect (runtime dependencies plus the core) and dev-only ones to exclude.

    Dev tools must stay out: some hooks (pydantic's) would otherwise drag mypy into the bundle.
    """
    data = tomllib.loads((CORE / "pyproject.toml").read_text("utf-8"))
    runtime = _modules_of(data["project"].get("dependencies", [])) | {"sound_prep_core"}
    dev = _modules_of(
        [r for r in data.get("dependency-groups", {}).get("dev", []) if isinstance(r, str)]
    )
    return sorted(runtime), sorted((dev - runtime) | set(BUILD_ONLY))


def runtime_distributions() -> list[str]:
    """Distribution names of the runtime dependencies and of the core itself."""
    project = tomllib.loads((CORE / "pyproject.toml").read_text("utf-8"))["project"]
    names = [project["name"]]
    for requirement in project.get("dependencies", []):
        match = re.match(r"[A-Za-z0-9_.-]+", requirement.strip())
        if match:
            names.append(match.group(0))
    return names


def missing_data(roots: list[Path]) -> list[str]:
    """Data files PyInstaller's own collector lists for the runtime modules but not in ``roots``.

    Covers package data such as certifi's ``cacert.pem``; ``roots`` are the directories that end up
    side by side in the bundle (``fw`` and ``res``), so a file counts if any of them has it.
    """
    from PyInstaller.utils.hooks import collect_data_files  # type: ignore[import-untyped]

    missing = []
    for module in module_sets()[0]:
        for src, dest in collect_data_files(module):
            relative = Path(dest) / Path(src).name
            if not any((root / relative).exists() for root in roots):
                missing.append(str(relative))
    return sorted(set(missing))


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _run(*cmd: str | Path) -> None:
    subprocess.run([str(c) for c in cmd], check=True)


def freeze(work: Path) -> Path:
    shutil.rmtree(work, ignore_errors=True)
    cmd: list[str | Path] = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--name", "core",
        "--distpath", work / "dist", "--workpath", work / "work", "--specpath", work,
    ]  # fmt: skip
    collect, exclude = module_sets()
    for module in collect:
        cmd += ["--collect-submodules", module]
    for module in collect:
        cmd += ["--collect-data", module]
    for dist in runtime_distributions():
        cmd += ["--copy-metadata", dist]
    for module in exclude:
        cmd += ["--exclude-module", module]
    cmd.append(CORE / "packaging" / "sidecar_entry.py")
    _run(*cmd)
    leaked = _leaked_modules(work / "work" / "core" / "PYZ-00.toc")
    if leaked:
        raise SystemExit(f"build-only modules ended up in the frozen archive: {leaked}")
    return work / "dist" / "core"


def _leaked_modules(toc: Path) -> list[str]:
    """Modules of the PYZ archive (listed in PyInstaller's toc) that are build-only."""
    names = set(re.findall(r"\('([\w.]+)',", toc.read_text("utf-8")))
    return sorted(
        n for n in names if any(n == bad or n.startswith(bad + ".") for bad in BUILD_ONLY)
    )


def _is_data(entry: Path) -> bool:
    """True for a top-level item of ``fw`` that holds no Mach-O code (it must not stay there)."""
    files = [entry] if entry.is_file() else [p for p in entry.rglob("*") if p.is_file()]
    code = [p for p in files if p.suffix in {".so", ".dylib"} or p.name == "Python"]
    if code and len(code) != len(files):
        raise SystemExit(f"{entry.name} mixes code and data; codesign would reject it")
    return not code


def _check_out_is_ours(out: Path) -> None:
    """Refuse to delete anything in a directory this script did not produce."""
    if not out.exists() or (out / MARKER).exists() or not any(out.iterdir()):
        return
    raise SystemExit(
        f"refusing to clean {out}: it is not empty and lacks the {MARKER} marker of a previous "
        "sidecar build. Choose an empty directory or delete it yourself."
    )


def assemble(onedir: Path, out: Path) -> None:
    """Split the onedir into launcher, ``fw`` (code) and ``res`` (data) as ADR 0001 describes."""
    launcher, fw, res = out / f"core-{TRIPLE}", out / "fw", out / "res"
    _check_out_is_ours(out)
    for path in (launcher, fw, res):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(onedir / "core", launcher)
    shutil.copytree(onedir / "_internal", fw, symlinks=True)
    res.mkdir()
    for entry in sorted(fw.iterdir()):
        # The stdlib directory holds only extension modules, but ADR 0001 keeps it in res.
        stdlib = re.fullmatch(r"python3\.\d+", entry.name) is not None
        if entry.is_symlink() or entry.name == "Python.framework":
            continue
        if not stdlib and not _is_data(entry):
            continue
        shutil.move(entry, res / entry.name)
        entry.symlink_to(f"../Resources/pyi/{entry.name}")
    # Like the other symlinks into ../Resources/pyi, these only resolve inside the bundle mapping
    # (fw -> Contents/Frameworks, res -> Contents/Resources/pyi); they dangle in this output dir.
    # Extension modules in res/python3.X/lib-dynload find their dylibs through @rpath, which
    # resolves (through the symlink) to Resources/pyi/: link the Frameworks dylibs there.
    for dylib in sorted(fw.glob("*.dylib")):
        if not dylib.is_symlink():
            (res / dylib.name).symlink_to(f"../../Frameworks/{dylib.name}")
    # codesign rejects loose data next to code, and each Mach-O must be signed before bundling.
    for binary in [*res.rglob("*.so"), *fw.rglob("*.dylib"), *fw.rglob("*.so")]:
        if not binary.is_symlink():
            _run("codesign", "--force", "-s", "-", binary)
    if (fw / "Python.framework").is_dir():
        _run("codesign", "--force", "-s", "-", fw / "Python.framework")
    leaked = forbidden_in_tree(fw) + forbidden_in_tree(res)
    if leaked:
        raise SystemExit(f"build-only files ended up in the output: {leaked}")
    absent = missing_data([fw, res])
    if absent:
        raise SystemExit(f"package data missing from the output: {absent}")
    (out / MARKER).write_text("generated by core/packaging/build_sidecar.py\n", "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if (
        sys.platform != "darwin"
        or subprocess.check_output(["uname", "-m"], text=True).strip() != "arm64"
    ):
        raise SystemExit(f"only {TRIPLE} is supported (PyInstaller does not cross-compile)")
    assemble(freeze(CORE / "build" / "sidecar"), args.out.resolve())
    print(f"sidecar written to {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
