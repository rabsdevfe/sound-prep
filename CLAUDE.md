# sound-prep — development guide

macOS desktop app that turns a YouTube URL, a title, an output directory and a time range into a full MP3 plus a clip. Planned: compare two clips and report sound differences to guide MainStage patch changes.

## Stack

- `apps/desktop/`: Tauri 2 shell (Rust) with a React + TypeScript UI.
- `core/`: Python core managed with `uv`; it will ship to the app as a sidecar binary.

## Commands

### Desktop (`apps/desktop/`)

Use the Node version in `.nvmrc` (`nvm use`). Supported range is set in `package.json` `engines` and enforced on install (`engine-strict`); keep it aligned with the lockfile's dependency engines.

```bash
npm ci
npm run check:ipc                      # fails when generated IPC files are stale
npm run generate:ipc                   # regenerate them from contracts/ipc.schema.json
npm run lint && npm run typecheck && npm test && npm run build
npm run tauri dev                      # run the app (build the sidecar first, see Core; build.rs lays out its code beside target/debug/core)
(cd src-tauri && cargo fmt --check && cargo clippy --all-targets -- -D warnings)
```

### Core (`core/`)

Python version comes from `core/.python-version`; `uv` installs it when missing.

```bash
uv sync
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
uv run python -m sound_prep_core       # sidecar: JSON Lines on stdin/stdout; takes no argv; ffmpeg: SOUND_PREP_FFMPEG=/abs/path or Homebrew defaults (never PATH)
uv run python packaging/build_sidecar.py   # freeze the sidecar (macOS arm64) into apps/desktop/src-tauri/binaries/ (gitignored)
uv run python packaging/smoke_sidecar.py   # smoke test of the frozen binary in the bundle layout
uv run python packaging/smoke_sidecar.py --dev   # the launcher `tauri dev` runs (after `cargo build` in src-tauri)
```

## Architecture rules

- **Hexagonal core.** Domain and use cases never import adapters or third-party I/O libraries; adapters implement ports.
- **The IPC contract is the source of truth** between UI and core. Change it in its own PR, together with both sides.
  After changing `contracts/ipc.schema.json`: run `npm run generate:ipc` in `apps/desktop/` (rewrites `src/ipc/types.generated.ts` and the precompiled `src/ipc/validate.generated.ts`, commit both), then run the tests of both packages. Never hand-edit generated files and never relax the CSP to compile validators at runtime (no `eval`).
- **UI follows container/presentational.** Presentational components receive data and callbacks only; containers talk to the core client.
- **Thin Rust layer.** Rust only spawns the core sidecar and forwards messages; no business logic.

## Commit workflow (mandatory, in this order)

1. Implement one work unit: one purpose, tests included, the repo still works with only this commit applied.
2. Run the checks of every package the unit touches. All must pass.
3. Stage the unit and get a **blind review**: a fresh reviewer with no prior context receives only the commit objective (what and why) and reads `git diff --cached` itself. The objective must not include implementation hints or a list of changed files.
4. Fix blocking findings, re-run the checks after any fix, and request one fresh re-review (round 2). If round 2 still requests changes:
   - Fix every correct blocking finding in scope (a bug, a broken contract, a failing check). A finding is in scope when it concerns code or docs that the staged diff introduces or changes; any such blocker must be fixed.
   - A finding may stay unfixed only if it is out of scope (it concerns code the diff does not introduce or change, and it belongs to another unit) or you dispute it. A dispute must say why the finding is wrong, citing the code, a test or the contract; "disagree" or "low priority" is not a reason. Log each one in `docs/review-log.md` with Status `declined` or `deferred` and that reason; never dismiss one silently. Unfixed round-2 blockers keep `Severity: blocking` in the log.
   - Re-run the checks after any fix; once they pass, commit without a third review.
   - Inform the repository owner afterwards, in the final report of the PR or task, naming the log rows of any unfixed blockers.
   - Otherwise, stop and ask the owner before committing when a remaining blocker needs a product or security decision that documenting cannot settle, or when you dispute a security or correctness blocker. When in doubt, stop and ask.
5. After the review rounds end, record every finding of every round, with its resolution, in `docs/review-log.md` (format described there) and stage it in the same commit. These rows are written after the review, so they are not part of the reviewed diff.
6. Commit with a Conventional Commit message. No AI attribution or `Co-Authored-By` lines, even if a tool adds them by default.

One PR per phase, at most 400 authored changed lines (lockfiles and generated files excluded); split into chained PRs when larger.

## Git identity

This repository is configured locally to commit and push as the `rabsdevfe` GitHub account. Do not change the local git config or the global one. `git push` already uses the local credential helper; only `gh` commands (PRs, issues, API) need `GH_TOKEN=$(gh auth token -h github.com -u rabsdevfe)` so they target this account regardless of the active `gh` account.
