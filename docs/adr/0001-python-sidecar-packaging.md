# ADR 0001: Packaging the Python core as a Tauri sidecar

- Status: proposed (decision is provisional, see "Decision")
- Date: 2026-11-14
- Scope: packaging, process model and external tools (ffmpeg) for `core/`

## Context

The core (Python, `uv`) will ship inside the Tauri 2 app as a sidecar and talk to the Rust shell over stdin/stdout JSON Lines (`contracts/ipc.schema.json`). It will later use yt-dlp (as a library) and ffmpeg. This spike measured packaging, the spawn path and macOS runtime behavior before building on them. The end goal includes distributing a signed app, so signing behavior is part of the evaluation, not an afterthought.

Environment: macOS 26.7.1, arm64 (`aarch64-apple-darwin`), Python 3.13.6, PyInstaller 6.22.3, Tauri 2.12.5 (`tauri-plugin-shell` crate 2.3.6), Rust 1.100, yt-dlp 2026.10.26, Homebrew ffmpeg 9.0.2. Timings are wall clock for `echo '{"id":"1"}' | <binary>` (process start to exit). One machine, small samples (n shown); treat them as orders of magnitude.

## Findings (evidence)

### 1. PyInstaller output and `externalBin`

`bundle.externalBin: ["binaries/core"]` requires the file `binaries/core-aarch64-apple-darwin`; Tauri copies it to `Contents/MacOS/core` (suffix stripped). The build fails when the file is missing, so `tauri dev` needs it too.

| Variant | Entry point | Size (dist) | App size | Run times, ms (n) |
|---|---|---|---|---|
| onefile | minimal (json, subprocess) | 6.9 MB | 12.1 MiB | 3792-6004, median about 4300 (8) |
| onedir | minimal | 17 MB | 22.6 MiB | first 4493, then 78-83 (8) |
| onefile | + yt-dlp | 14 MB | - | 10966-12200 (6) |
| onedir | + yt-dlp | 27 MB | - | first 12045, then 173-196 (6) |

Reference: `python -c "import yt_dlp"` takes 124 ms, so a warm frozen onedir adds little.

- onefile pays on EVERY launch (fresh `/tmp/_MEI*` extraction). onedir pays once per new copy of the files.
- Cause of the roughly 12 s first run (investigated, with yt-dlp onedir, 58 files / 54 Mach-O). A fresh `cp -R` of the onedir always took 11.9-12.6 s on first run and about 170 ms afterwards. It did NOT go away when: all files were pre-read (disk cache ruled out), `xattr -cr` was applied, the launcher was re-signed before the first run (12.6 s), or all 54 `.so`/`.dylib` were re-signed before the first run (12.1 s). A `sample` of the process at 5 s showed the main thread inside `dyld::dlopen` (loading the extension modules), not in extraction or Python code. This is consistent with time spent in the first `dlopen` of each newly written Mach-O (a macOS-side cost on first load of new files; the exact subsystem, for example syspolicyd or XProtect, was not identified because `log show` returned nothing without elevated access). What would confirm it: a trace with `sudo fs_usage -w` or `sudo log stream` on `syspolicyd`/`amfid` during the first run. Practical consequence: a first launch after each build or install is slow for onedir; onefile is slow on every launch.
- onedir does not fit `externalBin` alone. PyInstaller detects `.app/Contents/MacOS` and looks for its libraries in `Contents/Frameworks` (a plain `_internal` next to the binary fails with "Failed to load Python shared library ... Contents/Frameworks/Python"). It works when the onedir contents are mapped there with `bundle.macOS.files`. Symlinks are preserved by Tauri's copy.

### 2. Spawn, stdin/stdout, CSP and capability

The shell plugin works in the release build under the unchanged production CSP. The UI spawned the sidecar, wrote a request line, received `progress` and `result` lines, then wrote an `ack` line after the second stdout line; the sidecar logged both inputs. Verified for onefile and onedir, launched with `env -i /usr/bin/open -n sound-prep.app`.

- Production CSP, in `apps/desktop/src-tauri/tauri.conf.json` at `app.security.csp`, unchanged by the spike (no relaxation was needed because the plugin uses Tauri IPC): `default-src 'self'; connect-src ipc: http://ipc.localhost`
- Capability, `apps/desktop/src-tauri/capabilities/default.json` (the permissions list is the only change from the repository version):

```json
{ "identifier": "default", "windows": ["main"],
  "permissions": ["core:default",
    { "identifier": "shell:allow-spawn",
      "allow": [{ "name": "binaries/core", "sidecar": true, "args": false }] },
    { "identifier": "shell:allow-stdin-write",
      "allow": [{ "name": "binaries/core", "sidecar": true }] }] }
```

Negative tests (release build, same capability; each call attempted from the UI):

| Attempt | Result |
|---|---|
| `Command.create("/bin/ls").spawn()` | denied: program not allowed on the configured shell scope |
| `Command.create("ls").spawn()` | denied: same |
| `Command.sidecar("binaries/other").spawn()` | denied: not in `externalBin` |
| `Command.sidecar("binaries/core").execute()` | denied by ACL (no `allow-execute`) |
| `child.kill()` | denied by ACL (no `allow-kill`) |
| `Command.sidecar("binaries/core", ["--x"]).spawn()` | ALLOWED, even with `"args": false` in the scope entry |

So arbitrary programs cannot be spawned, but arguments to the allowed sidecar are NOT restricted: `"args": false` is not enforced (tested once, with `tauri` 2.12.5, crate `tauri-plugin-shell` 2.3.6 and npm `@tauri-apps/plugin-shell` 2.3.6). This is an open risk, not an accepted one. Blocking gate for the sidecar-phase PR (must pass before merge): the core rejects any argv (exits non-zero with an error on stderr when `len(sys.argv) > 1`) and a test proves it (spawn the entrypoint with an extra argument and assert the failure). All data comes from stdin. Omitting `allow-kill` is intentional: the child ends through stdin EOF (below); if explicit cancel is needed, send a `cancel` message through the contract rather than granting kill.

Process lifetime: after `kill -9` of the app the sidecar exited within 3 s because its stdin reached EOF. The core must keep a `for line in sys.stdin` loop and exit on EOF.

Version surprise: `cargo add tauri-plugin-shell` resolved crate 2.3.6 (the crate declares `rust-version = 1.85`), while `npm i @tauri-apps/plugin-shell` took 2.6.0 and `tauri build` refused the mismatch. The npm package had to be pinned to `~2.3.0`.

### 3. Launching from Finder: PATH and ffmpeg

A GUI-launched process gets `PATH=/usr/bin:/bin:/usr/sbin:/sbin`. Measured: the release `.app` started with `env -i /usr/bin/open -n` reported exactly that PATH and `shutil.which("ffmpeg") = None`, although `/opt/homebrew/bin/ffmpeg` exists. Plain `open -n` from a shell inherits the shell's PATH and hides the problem; test with `env -i`. With `PATH=/usr/bin:/bin:/opt/homebrew/bin` the same sidecar found ffmpeg 9.0.2.

| Option | Pros | Cons |
|---|---|---|
| A. Append `/opt/homebrew/bin`, `/usr/local/bin` to PATH in the core | trivial | trust assumption: those directories are writable by the admin user (Homebrew) and any binary there named `ffmpeg` (or other tools we exec) will run with the app's privileges; assumes Homebrew layout |
| B. User-configured absolute ffmpeg path, validated at startup (`ffmpeg -version`) | explicit trust, any install | needs a setting and validation UI |
| C. Bundle ffmpeg as a sidecar/resource | works offline, no prerequisite | license obligations, size, signing, updates |

Prefer B with a default discovered by checking fixed absolute candidates (`/opt/homebrew/bin/ffmpeg`, `/usr/local/bin/ffmpeg`) rather than prepending directories to PATH; if PATH is augmented at all, append (never prepend) so system tools keep precedence, and exec the resolved absolute path.

Licensing facts (not legal advice; review before any distribution): Homebrew's ffmpeg is configured with `--enable-gpl --enable-version3 --enable-libx264 --enable-libx265` (shared, 36 dylib references, not relocatable). Obligations of the GPL attach to whoever redistributes that ffmpeg binary: providing corresponding source and license notices. They would therefore apply to this project if it ships such a binary; they are not triggered by using a user-installed ffmpeg. A build without `--enable-gpl` and `--enable-nonfree` (LGPL configuration, for example with libmp3lame) has different license terms (LGPL) that also need review. Whether the app that ships it is affected depends on how it is combined with it; that determination needs legal review and was not made in this spike. No ffmpeg was bundled or built here.

### 4. Gatekeeper and signing

- Default Tauri build: the main binary is only linker-signed ad hoc; `codesign --verify --deep --strict` says "code has no resources but signature indicates they must be present" and `spctl -a` rejects the app (also with a `com.apple.quarantine` xattr). A locally built app, with no quarantine, launches normally from `open`. A downloaded copy would be blocked until the user overrides it in Settings.
- `bundle.macOS.signingIdentity: "-"` makes Tauri ad-hoc sign the bundle and the sidecar with the hardened runtime. `codesign --verify --deep --strict` then passes (`spctl` still rejects: expected for ad hoc).
- With the hardened runtime, BOTH onefile and onedir fail to start the Python runtime ("mapping process and mapped file have different Team IDs"; reproduced for onedir without the entitlement). Fix verified for both: `com.apple.security.cs.disable-library-validation` via `bundle.macOS.entitlements`. Security cost: library validation normally stops the process from loading dylibs not signed by the same team or Apple; disabling it lets the executables that carry it load any dylib, so a dylib planted or replaced inside the app bundle would run with their privileges. Which binaries carry it here is an open question (below). Tampering with a signed bundle invalidates its seal, and `allow-dyld-environment-variables` must not be added. Notarized distribution is still required for other machines (Developer ID certificate, every nested Mach-O signed with the hardened runtime).
- onedir signing, solved in this spike (it initially failed): `codesign` rejects loose non-code files in `Contents/Frameworks` (`base_library.zip`, the `python3.13/lib-dynload` directory). It works with this layout: only code stays in `Frameworks` (`libcrypto.3.dylib`, `Python` symlink, `Python.framework`), the data (`base_library.zip`, `python3.13/`) goes to `Resources/pyi/`, and relative symlinks in `Frameworks` point to `../Resources/pyi/...` (the layout PyInstaller's own `BUNDLE` produces); each `.so` and `Python.framework` are ad-hoc signed before bundling. Result: `codesign --verify --deep --strict` valid, and the app round-trips with the entitlement. Not tested: Developer ID signing, notarization, `x86_64`.

## Options considered

1. PyInstaller onefile sidecar, one long-lived process.
2. PyInstaller onedir sidecar mapped into the bundle (layout above), one long-lived process.
3. Untested alternatives: python-build-standalone plus `uv`-installed wheels as resources behind a thin launcher; Nuitka (compiled onefile/standalone). Neither was tried, so no claim is made about their startup, size or signing.

## Decision (Provisional)

Provisional recommendation: PyInstaller **onedir** with the signable layout above and **one long-lived sidecar** per app session (JSON Lines over stdin, exit on stdin EOF). It is provisional because it rests on one machine, ad-hoc signing only, and an unidentified first-load mechanism. Gate to confirm it: build with a Developer ID identity, notarize, install to `/Applications` from a downloaded (quarantined) copy, and check first-run time and Gatekeeper behavior. If that fails or the first-run cost is unacceptable, fall back to onefile (simpler layout, signs with the same entitlement, but 4 s minimal to 11-12 s with yt-dlp on every start, paid once per session when long-lived) or evaluate the untested alternatives.

Why onedir over onefile: after the first run it starts in about 0.2 s (with yt-dlp) versus 11-12 s on every launch for onefile, and the signing blocker found initially is solved. Cost: a layout script and symlinks that must be maintained, a larger app (22.6 vs 12.1 MiB minimal), and a slow first launch after install.

ffmpeg: option B (configured absolute path with fixed-candidate discovery); do not bundle now. Keep the CSP untouched; keep the capability limited to the two permissions shown.

## Consequences

- A build script must produce `binaries/core-<triple>`, the signed `fw/` and `res/` trees and the symlinks before `tauri build`/`tauri dev`, for `aarch64-apple-darwin` (PyInstaller does not cross-compile; add `x86_64` only if wanted).
- Signed builds need the entitlements file and carry the library-validation trade-off above.
- First launch after a build or install can take about 12 s with yt-dlp; the UI needs a "starting" state and a slow-spawn tolerance, and could warm up the sidecar at first run.
- The core exits on stdin EOF, flushes every line, and treats argv as untrusted.
- Homebrew ffmpeg stays a documented prerequisite; the core reports a clear error when it is not found.
- Pin `@tauri-apps/plugin-shell` to the same minor as the crate.

## Open questions

- Confirm the first-load mechanism (privileged trace) and whether fewer modules (`--exclude-module`, only the needed yt-dlp extractors) shrink the cost.
- Developer ID signing and notarization of the onedir layout; quarantined install behavior.
- Why `"args": false` is not enforced for sidecars (plugin bug, wrong syntax or version issue); until known, rely on the argv-rejection gate.
- Which signed binaries carry `disable-library-validation`: ANSWERED (wiring PR, verified on a release build with `codesign -d --entitlements -`). The single `bundle.macOS.entitlements` file puts it on BOTH the main `sound-prep` binary (which hosts the webview) and the `core` sidecar. This is accepted for local ad-hoc builds only. Before Developer ID signing and notarization it must be resolved so the main app does not carry it, for example by signing the main binary without the entitlement (the sidecar needs it, the main app does not appear to). Release signing is also not configured by `tauri.conf.json`: `bundle.macOS.signingIdentity: "-"` (ad hoc) is overridden by the `APPLE_SIGNING_IDENTITY` environment variable, which is how a Developer ID identity is supplied (JSON cannot hold a comment, so this is recorded here).
- Behavior of `cmd.on("close")` when the core crashes; Intel and universal builds.
- Static LGPL ffmpeg build, if bundling is ever required, after legal review.

## Reproduce

Minimal entrypoint (`core/src/sound_prep_core/spike_main.py`):

```python
import json, os, shutil, sys

for line in sys.stdin:
    req = json.loads(line)
    print(json.dumps({"type": "progress", "id": req.get("id"), "pct": 50}), flush=True)
    print(json.dumps({"type": "result", "id": req.get("id"), "path": os.environ.get("PATH"),
                      "ffmpeg": shutil.which("ffmpeg")}), flush=True)
```

yt-dlp variant entrypoint (`spike_ytdlp.py`, after `uv add yt-dlp`):

```python
import json, sys
import yt_dlp
from yt_dlp import YoutubeDL

for line in sys.stdin:
    req = json.loads(line)
    with YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
        ie = ydl.get_info_extractor("Youtube")
    print(json.dumps({"type": "result", "id": req.get("id"),
                      "ytdlp": yt_dlp.version.__version__, "ie": type(ie).__name__}), flush=True)
```

Build and time (n=8 loops; replace `ONE`/`DIR`):

```bash
cd core && uv add --dev pyinstaller   # and `uv add yt-dlp` for the yt-dlp variant
uv run pyinstaller --onefile --name core --distpath dist1 src/sound_prep_core/spike_main.py
uv run pyinstaller --onedir  --name core --distpath dist2 src/sound_prep_core/spike_main.py
bench() { for i in 1 2 3 4 5 6 7 8; do s=$(python3 -c 'import time;print(time.time())')
  echo '{"id":"1"}' | "$1" >/dev/null
  python3 -c "import time;print(round((time.time()-$s)*1000))"; done | tr '\n' ' '; echo; }
bench dist1/core; bench dist2/core/core        # onedir: first run is slow, later runs fast
# first-run test: fresh copy each time
cp -R dist2/core /tmp/fresh && bench /tmp/fresh/core
```

Tauri side (`apps/desktop`):

```bash
npm i @tauri-apps/plugin-shell@~2.3.0 && (cd src-tauri && cargo add tauri-plugin-shell@2)
```

`src-tauri/src/lib.rs`: `tauri::Builder::default().plugin(tauri_plugin_shell::init())`.

`src-tauri/tauri.conf.json` (onefile needs only `externalBin`; the rest is for signed onedir):

```json
"bundle": { "externalBin": ["binaries/core"],
  "macOS": { "signingIdentity": "-", "entitlements": "Entitlements.plist",
             "files": { "Frameworks": "binaries/fw", "Resources/pyi": "binaries/res" } } }
```

`src-tauri/Entitlements.plist`:

```xml
<plist version="1.0"><dict>
  <key>com.apple.security.cs.disable-library-validation</key><true/>
</dict></plist>
```

Capability: the JSON in section 2. UI spawn code (`src/App.tsx`):

```ts
import { Command } from "@tauri-apps/plugin-shell";
const cmd = Command.sidecar("binaries/core");
cmd.stdout.on("data", (line) => { /* one JSON message per line */ });
cmd.on("close", (d) => { /* sidecar ended */ });
const child = await cmd.spawn();
await child.write(JSON.stringify({ type: "prepare_clip", id: "1" }) + "\n");
```

onedir tree preparation (from the dist2 output):

```bash
B=apps/desktop/src-tauri/binaries; mkdir -p $B/fw $B/res
cp core/dist2/core/core $B/core-aarch64-apple-darwin
cp -R core/dist2/core/_internal/. $B/fw/
mv $B/fw/base_library.zip $B/res/
PYDIR=$(cd $B/fw && ls -d python3.*)   # e.g. the Python minor-version directory
mv "$B/fw/$PYDIR" $B/res/
(cd $B/fw && ln -s ../Resources/pyi/base_library.zip base_library.zip \
          && ln -s "../Resources/pyi/$PYDIR" "$PYDIR")
for f in $(find $B/res -name '*.so'); do codesign --force -s - "$f"; done
codesign --force -s - $B/fw/Python.framework
```

For onefile: `cp core/dist1/core $B/core-aarch64-apple-darwin` and drop `files`. Build and verify:

```bash
npm run tauri build -- --bundles app
APP=src-tauri/target/release/bundle/macos/sound-prep.app
codesign --verify --deep --strict -vv $APP
env -i /usr/bin/open -n $APP         # Finder-like launch (no shell PATH)
```

Negative-test spawn code (run after `spawn()` in the spike UI; each attempt reports `ALLOWED` or the error):

```ts
const attempt = async (k: string, f: () => Promise<unknown>) => {
  try { await f(); neg[k] = "ALLOWED"; } catch (e) { neg[k] = "denied: " + String(e); }
};
await attempt("create /bin/ls", () => Command.create("/bin/ls").spawn());
await attempt("sidecar other", () => Command.sidecar("binaries/other").spawn());
await attempt("sidecar core with args", () => Command.sidecar("binaries/core", ["--x"]).spawn());
await attempt("execute core", () => Command.sidecar("binaries/core").execute());
await attempt("kill", () => child.kill());
```

Gotchas: `spctl -a` rejects ad-hoc apps (expected); the spike logged the sidecar stdin to a file to prove the round trip, since the window content is not machine-readable.
