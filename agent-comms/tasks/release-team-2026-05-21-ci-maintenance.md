---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-05-21
slug: ci-maintenance
related:
  - tasks/coverage-team-2026-05-20-coverage-compare-perf.md
  - history/2026-05-21-phase2-3-inspect-and-jest-coverage.md
---

# Task: CI maintenance — GHA action deprecations + a `tests/perf` lane

This task has **two slices**. Slice A is **time-sensitive** and
independent — ship it first. Slice B is gated on another team's merge —
see "Sequencing".

## Why this task exists

The 2026-05-21 cycle history (`history/2026-05-21-phase2-3-inspect-and-jest-coverage.md`,
"Open follow-ups" #3 + the companion-task note in the coverage-perf task)
left two CI items in PM's queue:

1. **GHA action deprecations** — CI run logs surface two non-blocking
   warnings:
   - `astral-sh/setup-uv@v3` — its `python-version` input is deprecated.
   - The **Node 20 GHA action runtime is being retired**; GitHub forces
     actions still on the Node 20 runtime to Node 24 on **2026-06-02**.
     Actions pinned to majors that only ship a Node 20 runtime will start
     emitting hard warnings and eventually break.
2. **No CI lane runs `tests/perf`.** The coverage-perf slice
   (`tasks/coverage-team-2026-05-20-coverage-compare-perf.md`) adds a
   benchmark under a new `tests/perf/` tree that the default
   `uv run pytest -q` does NOT collect. It needs a dedicated opt-in lane.

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-release-team.md`
2. `.github/workflows/ci.yml` — the 9-cell matrix (read in full)
3. `.github/workflows/release-test.yml` — audit it for the SAME
   deprecations
4. `history/2026-05-21-phase2-3-inspect-and-jest-coverage.md` — "Open
   follow-ups" #3
5. `tasks/coverage-team-2026-05-20-coverage-compare-perf.md` — the perf
   test this task wires a lane for (read "Verification commands" + the
   "Companion task" note: the perf test is runnable via
   `uv run pytest tests/perf`)

---

## Slice A — clear the GHA deprecations (do this FIRST, independent)

**Deadline context:** the Node 20 runtime retirement forces migration on
**2026-06-02**. Land Slice A well before then.

**Scope:** audit **both** `.github/workflows/ci.yml` and
`.github/workflows/release-test.yml`. For every `uses:` action:

- Bump each action to a major version whose current release runs on the
  **Node 24** GHA runtime (e.g. `actions/checkout`, `actions/setup-node`,
  `astral-sh/setup-uv`, and any action in `release-test.yml`). Verify the
  target major actually ships a Node 24 runtime — do not bump blindly.
- For `astral-sh/setup-uv`: resolve the deprecated `python-version`
  input. The current `ci.yml` step passes `python-version:
  ${{ matrix.python-version }}` to `setup-uv`. Choose the maintained
  replacement — either the input the newer `setup-uv` major expects, or
  a separate `actions/setup-python` step feeding `uv`. Pick the simplest
  approach that keeps the 3x3 Python matrix intact.

**Pinned constraints:**

- The CI matrix stays **3 OS x 3 Python = 9 cells**. No cell added or
  removed by this slice.
- jest stays a real gate on all 9 cells (the `setup-node` step keeps
  running on every cell, Windows included — do NOT reintroduce a
  `runner.os != 'Windows'` guard).
- `release-test.yml`'s build matrix shape is unchanged (3 build cells +
  `install-script-e2e`); this slice only bumps `uses:` pins there.
- Behaviour-preserving only. No new steps, no matrix change in Slice A.

## Slice B — add a non-blocking `tests/perf` CI lane

**Sequencing:** `tests/perf/` does not exist until the coverage-perf
slice (`tasks/coverage-team-2026-05-20-coverage-compare-perf.md`) merges
to `main`. **Do Slice A now; do Slice B only once `tests/perf/` is
present on `main`.** If `tests/perf/` is not yet on `main` when you pick
this task up, ship Slice A alone, and say so in the handoff — PM
re-dispatches Slice B as a follow-up.

**Scope:** add a CI job that runs the coverage perf benchmark.

- New job in `.github/workflows/ci.yml` (a separate `job`, not a matrix
  cell of `test`). Single cell: `ubuntu-latest`, one Python (`3.13` is
  fine — pick one, do not matrix it).
- The job runs `uv run pytest tests/perf` after `uv sync --dev --frozen`.
- **Non-blocking:** the perf benchmark has a 5s NFR budget on shared
  GitHub runners with +/-30-40% wall-clock variance — it must NOT gate PR
  merges. Make the job non-blocking (`continue-on-error: true`, or place
  it so a failure does not block the `test` matrix's required-check
  status). State in the handoff exactly which mechanism you used and why
  it does not gate merges.
- No Node.js / jest fixture install needed for this job — the perf test
  is pure-Python (it generates `CoverageFactSet`s programmatically).

## Files NOT to touch

- `src/**`, `tests/**` — this is a CI-config-only task.
- `tests/perf/**` — owned by the Coverage team's coverage-perf slice; you
  only *invoke* it from a workflow.
- `pyproject.toml` — `tests/perf/` is deliberately outside `testpaths`;
  no edit needed (your workflow opts in explicitly with the path arg).

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
editing the workflow files (YAML config counts).

## Verification

- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
  and the same for `release-test.yml` — both parse.
- The definitive signal is the **post-merge CI run**: 9/9 `test` cells
  green, **zero deprecation warnings** in any cell's log, and (if Slice B
  shipped) the perf lane present and non-blocking.

## Reporting

Write `agent-comms/handoffs/release-team-2026-05-21-ci-maintenance.md`.
This task touches only `.github/workflows/**` (no `src/`/`tests/`), so
the WORKLOG hook does not fire and **no `WORKLOG.md` entry is required** —
but still run `python3 tools/regen_comms_index.py` and stage the new
`agent-comms/` files + `INDEX.md`.

**DoD bullets believed closed:** none — this is CI hygiene, not a
`delivery-phasing.md` DoD bullet. State that explicitly in the handoff.
In the handoff, name which action majors you landed on and confirm each
runs on the Node 24 runtime; if Slice B was deferred, say so clearly.
