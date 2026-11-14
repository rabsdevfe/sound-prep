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
npm run lint && npm run typecheck && npm test && npm run build
npm run tauri dev                      # run the app
(cd src-tauri && cargo fmt --check && cargo clippy --all-targets -- -D warnings)
```

### Core (`core/`)

Python version comes from `core/.python-version`; `uv` installs it when missing.

```bash
uv sync
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
```

## Architecture rules

- **Hexagonal core.** Domain and use cases never import adapters or third-party I/O libraries; adapters implement ports.
- **The IPC contract is the source of truth** between UI and core. Change it in its own PR, together with both sides.
- **UI follows container/presentational.** Presentational components receive data and callbacks only; containers talk to the core client.
- **Thin Rust layer.** Rust only spawns the core sidecar and forwards messages; no business logic.

## Commit workflow (mandatory, in this order)

1. Implement one work unit: one purpose, tests included, the repo still works with only this commit applied.
2. Run the checks of every package the unit touches. All must pass.
3. Stage the unit and get a **blind review**: a fresh reviewer with no prior context receives only the commit objective (what and why) and reads `git diff --cached` itself. The objective must not include implementation hints or a list of changed files.
4. Fix blocking findings, re-run checks, and request one fresh re-review. If blockers remain, stop and ask the repository owner.
5. Commit with a Conventional Commit message. No AI attribution or `Co-Authored-By` lines, even if a tool adds them by default.

One PR per phase, at most 400 authored changed lines (lockfiles and generated files excluded); split into chained PRs when larger.

## Git identity

This repository is configured locally to commit and push as the `rabsdevfe` GitHub account. Do not change the local git config or the global one. `git push` already uses the local credential helper; only `gh` commands (PRs, issues, API) need `GH_TOKEN=$(gh auth token -h github.com -u rabsdevfe)` so they target this account regardless of the active `gh` account.
