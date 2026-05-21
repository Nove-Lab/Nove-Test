---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-21
slug: ci-maintenance
related:
  - tasks/release-team-2026-05-21-ci-maintenance.md
  - history/2026-05-21-phase2-3-inspect-and-jest-coverage.md
---

# Handoff: CI maintenance — GHA action deprecations (Slice A)

## Summary

**Slice A shipped. Slice B deferred** — `tests/perf/` is not yet on `main`
(the coverage-perf slice `tasks/coverage-team-2026-05-20-coverage-compare-perf.md`
has not merged), so the perf CI lane cannot be wired without referencing a
path that does not exist. Per the task's "Sequencing" clause, Slice A is
shipped alone; PM should re-dispatch Slice B as a follow-up once
`tests/perf/` lands on `main`.

## Worktree

- Branch: `release/ci-maintenance`
- Worktree: `/home/yjshin/dev/novetest-ci-maintenance`
- Commit: `c81fc47` — `ci: bump GHA actions to Node 24 runtime majors`
- Based on: `69c6c74` (current `main`)

## Files changed

- `.github/workflows/ci.yml` — 3 `uses:` pins bumped + a clarifying comment
- `.github/workflows/release-test.yml` — 5 `uses:` pins bumped + a clarifying comment

No `src/`, no `tests/`, no `pyproject.toml`. CI-config-only — the WORKLOG
hook does not fire and no `WORKLOG.md` entry is required (per task).

## Action majors landed — each verified on the Node 24 runtime

Verification method: fetched each action's `action.yml` at the target
ref via `gh api` and inspected `runs.using`. `node24` = Node 24 runtime.

| Action | Was | Now | `runs.using` at new ref |
|---|---|---|---|
| `actions/checkout` | `@v4` | `@v6` | `node24` ✓ |
| `actions/setup-node` | `@v4` | `@v6` | `node24` ✓ |
| `actions/upload-artifact` | `@v4` | `@v7` | `node24` ✓ |
| `actions/download-artifact` | `@v4` | `@v8` | `node24` ✓ |
| `astral-sh/setup-uv` | `@v3` | `@v7` | `node24` ✓ |
| `softprops/action-gh-release` | `@v2` | `@v3` | `node24` ✓ |
| `dtolnay/rust-toolchain` | `@stable` | `@stable` (unchanged) | `composite` — see below |

- All bumps land on the **highest current floating-major tag** of each
  action — except `actions/checkout`/`actions/setup-node` where v5 was the
  first node24 major and v6 is current, and `astral-sh/setup-uv` where v7
  is the highest floating-major tag (no `v8` floating tag exists yet
  despite a `v8.1.0` point release; `@v7` resolves to `v7.6.0`, node24).
- `dtolnay/rust-toolchain@stable` is a **composite action** (`runs.using:
  composite`) — it has no JavaScript runtime at all, so the Node 20
  retirement does not affect it. Left unchanged deliberately.

## The `setup-uv` `python-version` deprecation — resolved

Root cause confirmed by inspecting `action.yml` inputs across majors:
`astral-sh/setup-uv@v3` has **no `python-version` input** — it was added
in `setup-uv@v4`. Both workflows pass `python-version:` to `setup-uv`, so
`@v3` emitted an `Unexpected input(s) 'python-version'` warning on every
cell. `@v7` recognizes the input (it sets `UV_PYTHON`), so:

- the warning is cleared, and
- the 3×3 Python matrix is kept intact with **no separate
  `actions/setup-python` step** — the simplest conforming approach.

## Constraints honoured

- CI matrix unchanged: still 3 OS × 3 Python = **9 cells**. No cell
  added/removed.
- jest stays a real gate on all 9 cells — the `setup-node` step is
  untouched except its version pin; no `runner.os != 'Windows'` guard
  reintroduced.
- `release-test.yml` build matrix shape unchanged (3 build cells +
  `install-script-e2e`); only `uses:` pins bumped there.
- Behaviour-preserving: only `uses:` pins changed (+ two explanatory
  comments). No new steps, no matrix change.

## Verification done

- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` → OK
- same for `release-test.yml` → OK
- `grep` confirms no `@v4`/`@v3`/`@v2` action pin remains; final pin set:
  `checkout@v6 ×3`, `setup-node@v6 ×1`, `setup-uv@v7 ×2`,
  `upload-artifact@v7 ×1`, `download-artifact@v8 ×2`,
  `action-gh-release@v3 ×1`, `rust-toolchain@stable ×1`.

**Definitive signal** (PM/Main Branch to observe): the post-merge CI run —
expect **9/9 `test` cells green** and **zero deprecation warnings** in any
cell's log. `release-test.yml` only runs on tag push / `workflow_dispatch`;
its pins are statically verified here and exercised at the next release
trigger.

## DoD bullets believed closed

**None.** This is CI hygiene (clearing GHA deprecation warnings ahead of
the 2026-06-02 Node 20 runtime retirement), not a `delivery-phasing.md`
DoD bullet. Stated explicitly per the task.

## Slice B — deferred (PM action needed)

Slice B (a non-blocking `tests/perf` CI lane) is **not started**:
`tests/perf/` does not exist on `main` yet. PM should re-dispatch Slice B
once the coverage-perf slice merges. The intended shape (from the task):
a separate `ubuntu-latest` / single-Python job running
`uv run pytest tests/perf` after `uv sync --dev --frozen`, made
non-blocking via `continue-on-error: true` so the 5s NFR budget on noisy
shared runners cannot gate PR merges.

## Surprises / notes

- `astral-sh/setup-uv` does not maintain a `v8` floating-major tag even
  though `v8.1.0` is the latest release. `@v7` is the highest floating
  major and is on Node 24 — pinning to a floating major keeps consistency
  with every other action in the workflow (all floating majors). If a
  future audit wants v8, it must pin an exact `v8.x.x` tag.
- No `questions/` round was needed — no dependency change, no engine
  impact; purely workflow `uses:` pins.
