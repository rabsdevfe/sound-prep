# Blind review log

Every finding raised by the blind pre-commit reviewer (see the commit workflow in `CLAUDE.md`), with what was done about it. The goal is to analyze, at the end of the project, what kind of issues the reviews catch and how they were handled.

## How to record

- After the review rounds of a work unit end, append one row per finding of every round, then stage this file in the same commit as the reviewed change. The rows are written after the review, so they are never part of a reviewed diff.
- Identify the unit by **Branch** and **Unit** (the commit subject); both are known before the commit exists. Find the commit later with `git log --grep`.
- **Round:** 1 is the first review of a unit; 2 is the single allowed re-review.
- **Verdict:** the verdict of that round, repeated on each of its rows. Count rounds as distinct (Unit, Round) pairs, not rows.
- **Severity:** `blocking` or `suggestion`.
- **Category:** `correctness`, `security`, `cross-engine`, `test-quality`, `docs`, `config`, `dependencies`, `ci`, `extensibility`, `scope`, `cleanup`, or `other` (extend this list here when a new category recurs).
- **Status:** `fixed`, `deferred`, `declined`, or `no-change` (acknowledged, nothing to do).
- **Notes:** free text: how it was fixed, where it was deferred to, or why it was declined.

## Findings

| # | Date | Branch | Unit | Round | Verdict | Severity | Category | Status | Finding | Notes |
|---|------|--------|------|-------|---------|----------|----------|--------|---------|-------|
| 1 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 1 | APPROVE | suggestion | docs | fixed | `GH_TOKEN` note did not say `git push` already uses the local credential helper |  |
| 2 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 1 | APPROVE | suggestion | docs | fixed | "What and why, never how" was ambiguous for the review prompt | objective must exclude implementation hints and file lists |
| 3 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 1 | APPROVE | suggestion | docs | fixed | "Maintainer" undefined in the escalation step | "repository owner" |
| 4 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 1 | APPROVE | suggestion | docs | declined | "One PR per phase" refers to phases defined nowhere in the repo | roadmap not in the repo yet |
| 5 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 1 | APPROVE | suggestion | docs | fixed | State that the no-attribution rule overrides tool defaults |  |
| 6 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 1 | APPROVE | suggestion | scope | declined | Roadmap sentence belongs in the README | one line of context |
| 7 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 2 | APPROVE | suggestion | docs | declined | "IPC contract in its own PR" conflicts with "one PR per phase" |  |
| 8 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 2 | APPROVE | suggestion | docs | fixed | Stack (Tauri, sidecar) not named, so rules lack context | in `32f6a53` |
| 9 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 2 | APPROVE | suggestion | docs | declined | Blind review mechanism not named |  |
| 10 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 2 | APPROVE | suggestion | docs | fixed | "Run the checks" has no commands | in `32f6a53` and `7942d12` |
| 11 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 2 | APPROVE | suggestion | docs | declined | Only Claude Code reads `CLAUDE.md`; add `AGENTS.md` |  |
| 12 | 2026-11-14 | `chore/phase-0-scaffold` | `docs: add development workflow` | 2 | APPROVE | suggestion | docs | no-change | Make sure tooling does not re-add `Co-Authored-By` | already covered |
| 13 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 1 | APPROVE | suggestion | security | fixed | Strict CSP would block Vite HMR in `tauri dev` | separate `devCsp` |
| 14 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 1 | APPROVE | suggestion | dependencies | fixed | `@types/node` 26 mismatches the Node 22 pin; no `engines` |  |
| 15 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 1 | APPROVE | suggestion | config | fixed | `tsc --noEmit` never type-checks `vite.config.ts` |  |
| 16 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 1 | APPROVE | suggestion | cleanup | fixed | Edition 2024 without `rust-version`; unused `serde` deps |  |
| 17 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 1 | APPROVE | suggestion | cleanup | deferred | Default Tauri template icons | packaging phase |
| 18 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 1 | APPROVE | suggestion | scope | declined | Unrequested tagline in `App.tsx` |  |
| 19 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 1 | APPROVE | suggestion | cleanup | declined | `apps/desktop/.gitignore` duplicates the root one |  |
| 20 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 2 | APPROVE | suggestion | dependencies | fixed | `engines >=22` too loose: jsdom needs Node 22.12+ | in PR #2 |
| 21 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 2 | APPROVE | suggestion | cleanup | declined | Duplicate ignore and editor rules |  |
| 22 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 2 | APPROVE | suggestion | cleanup | deferred | Windows/mobile template leftovers, `bundle.targets: all` | packaging phase |
| 23 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 2 | APPROVE | suggestion | cleanup | declined | `src-tauri/.gitignore` duplicates root patterns |  |
| 24 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 2 | APPROVE | suggestion | config | declined | `composite` in `tsconfig.node.json` is unnecessary |  |
| 25 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(desktop): scaffold tauri react app` | 2 | APPROVE | suggestion | docs | declined | Document the Rust 1.85 minimum | `rust-version` in `Cargo.toml` |
| 26 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(core): scaffold python core package` | 1 | APPROVE | suggestion | dependencies | no-change | `uv_build` upper bound needs bumping with uv upgrades |  |
| 27 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(core): scaffold python core package` | 1 | APPROVE | suggestion | config | declined | Ruff could also select `S` and `PT` |  |
| 28 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(core): scaffold python core package` | 1 | APPROVE | suggestion | test-quality | declined | Smoke test hard-codes the version |  |
| 29 | 2026-11-14 | `chore/phase-0-scaffold` | `chore(core): scaffold python core package` | 1 | APPROVE | suggestion | config | no-change | `license` field set while `LICENSE` lives at the root | until publishing |
| 30 | 2026-11-14 | `chore/phase-0-scaffold` | `ci: add lint and test workflow` | 1 | APPROVE | suggestion | security | declined | Actions pinned to tags, not SHAs; no Dependabot | read-only permissions |
| 31 | 2026-11-14 | `chore/phase-0-scaffold` | `ci: add lint and test workflow` | 1 | APPROVE | suggestion | ci | declined | Rust toolchain unpinned; new clippy lints can break CI |  |
| 32 | 2026-11-14 | `chore/phase-0-scaffold` | `ci: add lint and test workflow` | 1 | APPROVE | suggestion | ci | declined | No `timeout-minutes` on jobs |  |
| 33 | 2026-11-14 | `chore/phase-0-scaffold` | `ci: add lint and test workflow` | 1 | APPROVE | suggestion | ci | declined | `cancel-in-progress` also cancels runs on `main` |  |
| 34 | 2026-11-14 | `chore/phase-0-scaffold` | `ci: add lint and test workflow` | 1 | APPROVE | suggestion | ci | deferred | Core job runs on Linux only | add macOS when OS-specific code lands |
| 35 | 2026-11-14 | `chore/phase-0-scaffold` | `ci: add lint and test workflow` | 1 | APPROVE | suggestion | ci | fixed | CI cannot block merges without branch protection | protection enabled on `main` |
| 36 | 2026-11-14 | `fix/desktop-node-engines` | `fix(desktop): enforce supported node versions on install` | 1 | CHANGES | blocking | dependencies | fixed | `>=22.12` claims versions the locked deps reject | `^22.22.2`, `^24.15.0` or `>=26.0.0` |
| 37 | 2026-11-14 | `fix/desktop-node-engines` | `fix(desktop): enforce supported node versions on install` | 1 | CHANGES | blocking | config | fixed | `engine-strict` would fail on a dependency, not the package | aligned range fails on the package first |
| 38 | 2026-11-14 | `fix/desktop-node-engines` | `fix(desktop): enforce supported node versions on install` | 1 | CHANGES | suggestion | config | declined | Pin `.nvmrc` to the minimum version |  |
| 39 | 2026-11-14 | `fix/desktop-node-engines` | `fix(desktop): enforce supported node versions on install` | 1 | CHANGES | suggestion | config | no-change | `.npmrc` applies only inside `apps/desktop` | intended |
| 40 | 2026-11-14 | `fix/desktop-node-engines` | `fix(desktop): enforce supported node versions on install` | 1 | CHANGES | suggestion | docs | fixed | Document the Node requirement |  |
| 41 | 2026-11-14 | `fix/desktop-node-engines` | `fix(desktop): enforce supported node versions on install` | 2 | APPROVE | suggestion | config | declined | Pin `.nvmrc` to `22.22.2` |  |
| 42 | 2026-11-14 | `fix/desktop-node-engines` | `fix(desktop): enforce supported node versions on install` | 2 | APPROVE | suggestion | docs | fixed | Mention unsupported Node versions in the commit body |  |
| 43 | 2026-11-14 | `fix/desktop-node-engines` | `fix(desktop): enforce supported node versions on install` | 2 | APPROVE | suggestion | config | no-change | `engine-strict` is npm-specific | repo uses npm |
| 44 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 1 | CHANGES | blocking | cross-engine | fixed | Python `$` matches before a trailing newline; JS does not | `(?![\s\S])` end guard |
| 45 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 1 | CHANGES | blocking | correctness | fixed | `output_dir` accepted relative paths |  |
| 46 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 1 | CHANGES | blocking | correctness | fixed | `format: uri` never enforced; `https://` passed | stricter pattern |
| 47 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 1 | CHANGES | blocking | test-quality | fixed | Invalid fixtures could fail for unrelated reasons | expected-failure manifest |
| 48 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 1 | CHANGES | suggestion | extensibility | fixed | Top-level `oneOf` gives poor errors and scales badly | `type`-discriminated branches |
| 49 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 1 | CHANGES | suggestion | test-quality | fixed | No valid fixtures for most error codes |  |
| 50 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 1 | CHANGES | suggestion | docs | fixed | Message direction and stream rule undocumented | schema description |
| 51 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 1 | CHANGES | suggestion | docs | fixed | Paths are POSIX-only but not stated |  |
| 52 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 1 | CHANGES | suggestion | correctness | fixed | `id` has no `maxLength` | 128 |
| 53 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 1 | CHANGES | suggestion | correctness | no-change | `v` accepts `1.0` | equal in JSON Schema |
| 54 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 2 | CHANGES | blocking | cross-engine | fixed | `\s` matches different characters in Python and JS | explicit excluded character classes |
| 55 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 2 | CHANGES | blocking | test-quality | deferred | No JS validator proves cross-engine parity | a later desktop commit runs ajv on the same fixtures (owner decision) |
| 56 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 2 | CHANGES | suggestion | correctness | fixed | Errors cannot be sent when the request id is unreadable | nullable `id` on errors only |
| 57 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 2 | CHANGES | suggestion | extensibility | fixed | A `type` enum value without a branch would pass unvalidated | enum/branch parity test |
| 58 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 2 | CHANGES | suggestion | test-quality | declined | Test checks membership, not the exact error set |  |
| 59 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 2 | CHANGES | suggestion | correctness | no-change | Leading time field is unbounded (`99999`) | documented |
| 60 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 2 | CHANGES | suggestion | test-quality | deferred | "Exactly one result or error" rule is untestable in a schema | sidecar protocol tests |
| 61 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 2 | CHANGES | suggestion | cleanup | declined | Boilerplate valid error fixtures |  |
| 62 | 2026-11-14 | `feat/phase-1-ipc-contract` | `feat(contract): define ipc v1 schema with fixtures` | 2 | CHANGES | suggestion | docs | declined | `$id` URL does not resolve |  |
| 63 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 1 | CHANGES | blocking | docs | fixed | Rule required a commit hash that does not exist until the commit is made | rows keyed by branch and commit subject |
| 64 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 1 | CHANGES | blocking | docs | fixed | Log claimed exemption from review, contradicting the workflow in `CLAUDE.md` | `CLAUDE.md` states rows are written after the review |
| 65 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 1 | CHANGES | suggestion | docs | fixed | Resolution column mixed a status with free text | split into Status and Notes |
| 66 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 1 | CHANGES | suggestion | docs | fixed | Commit/PR column mixed hashes and PR labels | replaced by Branch and Unit |
| 67 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 1 | CHANGES | suggestion | docs | fixed | Closed category list had no fallback | `other` plus an extension rule |
| 68 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 1 | CHANGES | suggestion | docs | fixed | Verdict repeated on every row inflates round counts | counting rule documented |
| 69 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 2 | APPROVE | suggestion | docs | deferred | Allowed Verdict values not enumerated | follow-up commit refining the log rules |
| 70 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 2 | APPROVE | suggestion | docs | fixed | Escaped pipes in a cell break naive column splitting | cell rephrased without pipes |
| 71 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 2 | APPROVE | suggestion | docs | deferred | Date format, numbering and rounds with zero findings unspecified | follow-up commit refining the log rules |
| 72 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 2 | APPROVE | suggestion | docs | deferred | Backfilled rows land in a later commit, against the same-commit rule | follow-up commit documents the backfill exception |
| 73 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 2 | APPROVE | suggestion | docs | deferred | "Never part of a reviewed diff" is false for the commit that introduces the log | follow-up commit refines the wording |
| 74 | 2026-11-14 | `feat/phase-1-ipc-contract` | `docs: add blind review findings log` | 2 | APPROVE | suggestion | docs | fixed | A row referred to a phase unit the repo does not define | cell rephrased |
