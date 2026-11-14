"""Smoke test of the frozen sidecar, run in the layout Tauri produces inside the app bundle.

``uv run python packaging/smoke_sidecar.py [--binaries DIR]`` (build first). It mirrors the
mapping lane F configures (``core`` -> ``Contents/MacOS/core``, ``fw`` -> ``Contents/Frameworks``,
``res`` -> ``Contents/Resources/pyi``) in a temporary ``.app``. Checks: no build-only files,
package data present, the build's own signatures valid, the bundle signed like the app (hardened
runtime plus the ADR's entitlement) and verified, then, launched like Finder (empty environment,
cwd ``/``): argv is rejected, EOF exits 0, and an invalid request is answered per contract.
"""

import argparse
import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build_sidecar import forbidden_in_tree, missing_data
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
TRIPLE = "aarch64-apple-darwin"
BINARIES = ROOT / "apps" / "desktop" / "src-tauri" / "binaries"
SCHEMA = json.loads((ROOT / "contracts" / "ipc.schema.json").read_text("utf-8"))
TIMEOUT = 180  # the first run of a freshly copied onedir can take about 12 s (ADR 0001)


def run(
    launcher: Path, *args: str, stdin: bytes = b"", env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(launcher), *args],
        input=stdin,
        capture_output=True,
        timeout=TIMEOUT,
        env=env or {},
        cwd="/",  # Finder launches with cwd "/", not the repository
        check=False,
    )


def codesign_verify(*flags: str, path: Path) -> subprocess.CompletedProcess[bytes]:
    cmd = ["codesign", "--verify", *flags, str(path)]
    return subprocess.run(cmd, capture_output=True, check=False)


def check(condition: bool, what: str) -> None:
    if not condition:
        raise SystemExit(f"smoke test FAILED: {what}")
    print(f"ok: {what}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--binaries", type=Path, default=BINARIES)
    src = parser.parse_args().binaries
    with tempfile.TemporaryDirectory() as tmp:
        contents = Path(tmp) / "smoke.app" / "Contents"
        (contents / "MacOS").mkdir(parents=True)
        (contents / "Resources").mkdir()
        shutil.copy2(src / f"core-{TRIPLE}", contents / "MacOS" / "core")
        shutil.copytree(src / "fw", contents / "Frameworks", symlinks=True)
        shutil.copytree(src / "res", contents / "Resources" / "pyi", symlinks=True)
        launcher = contents / "MacOS" / "core"
        (contents / "Info.plist").write_bytes(
            plistlib.dumps(
                {
                    "CFBundleExecutable": "core",
                    "CFBundleIdentifier": "dev.rabsdevfe.soundprep.smoke",
                    "CFBundleName": "smoke",
                    "CFBundlePackageType": "APPL",
                }
            )
        )
        app = contents.parent
        check(
            not forbidden_in_tree(contents / "Frameworks")
            + forbidden_in_tree(contents / "Resources" / "pyi"),
            "no build-only files in the bundle",
        )
        frameworks, pyi = contents / "Frameworks", contents / "Resources" / "pyi"
        absent = missing_data([frameworks, pyi])
        check(not absent, f"package data of runtime dependencies present (missing: {absent})")
        # 1. The layout exactly as the build produced it: every Mach-O keeps its build signature.
        machos = [
            p
            for root in (frameworks, pyi)
            for p in root.rglob("*")
            if p.is_file() and not p.is_symlink() and p.suffix in {".so", ".dylib"}
        ]
        for path in [src / f"core-{TRIPLE}", *machos, frameworks / "Python.framework"]:
            verified = codesign_verify("--strict", path=path)
            check(verified.returncode == 0, f"build signature valid: {path.name}")
        # 2. Sign the way the app is (ADR 0001 section 4): hardened runtime plus the
        # disable-library-validation entitlement, nested code untouched (no --force --deep).
        entitlements = Path(tmp) / "Entitlements.plist"
        entitlements.write_bytes(
            plistlib.dumps({"com.apple.security.cs.disable-library-validation": True})
        )
        sign = ["codesign", "--force", "--options", "runtime", "--entitlements", str(entitlements)]
        subprocess.run([*sign, "-s", "-", str(launcher)], check=True)
        subprocess.run([*sign, "-s", "-", str(app)], check=True)
        verify = codesign_verify("--deep", "--strict", path=app)
        check(verify.returncode == 0, f"signed bundle verifies: {verify.stderr.decode().strip()}")

        result = run(launcher, "--x", stdin=b"{}\n")
        check(
            result.returncode != 0 and result.stdout == b"" and bool(result.stderr), "argv rejected"
        )

        result = run(launcher)
        check(result.returncode == 0 and result.stdout == b"", "exit 0 on stdin EOF")

        params = {"url": "ftp://nope", "title": "t", "output_dir": "/tmp", "start": "0", "end": "5"}
        bad = {"v": 1, "id": "smoke-1", "type": "prepare_clip", "params": params}
        result = run(launcher, stdin=b"not json\n" + json.dumps(bad).encode() + b"\n")
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        validator = Draft202012Validator(SCHEMA)
        check(
            result.returncode == 0 and all(validator.is_valid(m) for m in messages),
            "output validates",
        )
        check(
            [(m["id"], m["code"]) for m in messages]
            == [(None, "invalid_request"), ("smoke-1", "invalid_url")],
            "invalid requests answered per contract",
        )

        # A valid request with an unusable ffmpeg: a contract error naming ffmpeg, loop alive.
        # No network: ffmpeg is only needed (and fails) at the first download step.
        out_dir = Path(tmp) / "out"
        out_dir.mkdir()
        good_params = {**params, "url": "https://youtu.be/x", "output_dir": str(out_dir)}
        valid = {**bad, "id": "smoke-2", "params": good_params}
        lines = [json.dumps(valid), json.dumps(bad)]
        result = run(
            launcher,
            stdin="\n".join(lines).encode() + b"\n",
            env={"SOUND_PREP_FFMPEG": "/nonexistent/ffmpeg"},
        )
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        check(
            result.returncode == 0 and all(validator.is_valid(m) for m in messages),
            "valid request with missing ffmpeg: output validates",
        )
        errors = [m for m in messages if m["type"] == "error"]
        check(
            [(m["id"], m["code"]) for m in errors]
            == [("smoke-2", "download_failed"), ("smoke-1", "invalid_url")]
            and "ffmpeg" in errors[0]["message"].lower(),
            "missing ffmpeg is a contract error naming ffmpeg and the loop keeps serving",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
