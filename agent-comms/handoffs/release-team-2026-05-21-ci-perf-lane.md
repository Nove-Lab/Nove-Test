---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-21
slug: ci-perf-lane
related:
  - tasks/release-team-2026-05-21-ci-perf-lane.md
  - tasks/release-team-2026-05-21-ci-maintenance.md
  - handoffs/coverage-team-2026-05-21-coverage-compare-perf.md
---

# Handoff: non-blocking `tests/perf` CI lane + install-script encoding hardening

## Summary

Both slices shipped — this is the re-dispatch of the deferred Slice B from
the ci-maintenance task (`tests/perf/` is now on `main` via `5489c7e`),
plus the adjacent install-script encoding hardening fix.

## Worktree

- Branch: `release/ci-perf-lane`
- Worktree: `/home/yjshin/dev/novetest-ci-perf-lane`
- Based on: `c598eb3` (current `main`)

## Files changed

- `.github/workflows/ci.yml` — Slice A: new `perf` job appended
- `tests/release/test_install_script.py` — Slice B: one `encoding="utf-8"` kwarg
- `WORKLOG.md` — entry appended (Slice B touches `tests/release/`, hook fires)
- `agent-comms/handoffs/release-team-2026-05-21-ci-perf-lane.md` — this file

No `src/`, no `pyproject.toml`, no `tests/perf/**` edit.

## Slice A — non-blocking `perf` CI lane

A new top-level `job` named `perf` in `.github/workflows/ci.yml` (NOT a
cell of the existing `test` matrix). It is unchanged-by-design except for
being appended:

- Single cell: `ubuntu-latest`, Python `3.13` (not matrixed).
- Steps: `actions/checkout@v6` → `astral-sh/setup-uv@v7` →
  `uv sync --dev --frozen` → `uv run pytest tests/perf`.
- Action majors match the `test` job exactly (post-`57cdf0d` Node 24 pins)
  — no older majors introduced.
- No `setup-node` step and no jest-fixture `npm install` loop — the perf
  benchmark is pure-Python (`generate_large_fact_set.py` builds
  `CoverageFactSet`s programmatically), so those steps are deliberately
  omitted.
- The existing `test` job (9-cell matrix) and its `pytest (release smoke)`
  step are untouched.
- `pyproject.toml` not edited — `tests/perf/` is outside
  `[tool.pytest.ini_options].testpaths`; the lane opts in explicitly with
  the `tests/perf` path argument. No new dependency needed.

### Non-blocking mechanism (asked for explicitly by the task)

The lane is non-blocking by **two independent guarantees**:

1. **It is a separate, brand-new `job`.** Branch-protection required
   status checks are opt-in by name; a newly added job is never
   auto-added to the required set. So `perf` cannot gate a PR merge
   unless an admin explicitly adds it (and the task says not to).
2. **`continue-on-error: true` on the job.** This is the documented
   job-level knob ("allow a workflow run to pass when this job fails").
   Even if the benchmark exceeds budget, the *workflow run* conclusion
   stays `success` — so the perf job's outcome never drags down the
   overall "CI" check either.

Guarantee (2) is the primary mechanism; (1) is the belt-and-braces
backstop. The 5s NFR budget is measured on shared GitHub runners with
±30-40% wall-clock variance, so a slow run must never block a merge.

## Slice B — install-script test encoding hardening

`tests/release/test_install_script.py::_run_install_script` invoked the
install script via `subprocess.run(..., text=True, timeout=30)` with no
explicit `encoding=`. `text=True` alone decodes the captured pipes with
the parent process's locale codec — the exact latent pattern the
jest-charmap cycle fixed in the two CLI conftests. Added
`encoding="utf-8"` — a one-keyword surgical change; the helper is
otherwise untouched. `tests/release/` runs only on POSIX CI cells today,
so this is pre-emptive hardening, not a live defect.

## Verification done

- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
  → parses; jobs `['test', 'perf']`, `perf.continue-on-error` is `True`.
- `uv run pytest -q tests/release` → **3 passed** — the `encoding=` change
  is behaviour-preserving on a POSIX host.
- `uv run pytest tests/perf` → **3 passed**, observed `median=0.025s` over
  5 runs (internal budget 3.0s) — confirms the exact command the new lane
  runs works.
- `uv run pytest -q` → **337 passed + 3 skipped** — unchanged baseline,
  confirming `tests/perf` is still not collected by the default run.

**Definitive signal** (PM/Main Branch to observe): the post-merge CI run
shows the `perf` lane present, running, and non-blocking.

## DoD bullets believed closed

**None.** Slice A is CI tooling; Slice B is pre-emptive hardening.
Neither is a `delivery-phasing.md` DoD bullet. (Phase 2 DoD #4 itself was
already closed by the coverage-perf slice `5489c7e`.) Stated explicitly
per the task.

## Surprises / notes

- None. No dependency change, no engine impact, no `questions/` round
  needed.
