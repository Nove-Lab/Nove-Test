---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-05-21
slug: ci-perf-lane
related:
  - tasks/release-team-2026-05-21-ci-maintenance.md
  - handoffs/coverage-team-2026-05-21-coverage-compare-perf.md
  - findings/manual-test-team-2026-05-21-jest-charmap-encoding.md
---

# Task: non-blocking `tests/perf` CI lane + install-script encoding hardening

This is the **re-dispatch of the deferred Slice B** from
`tasks/release-team-2026-05-21-ci-maintenance.md`, plus one small adjacent
hardening fix that Manual Test surfaced in the same cycle. Two slices,
both small.

## Why this task exists

- **Slice B was deferred** in the ci-maintenance task: a non-blocking CI
  lane for `tests/perf` could not be wired while `tests/perf/` did not
  exist on `main`. The coverage-perf slice has since merged
  (`5489c7e` — `test(coverage): NFR-COV-002 50k-location perf
  benchmark`), so `tests/perf/` is now on `main` and the lane can land.
- **Adjacent hardening:** the jest-charmap cycle root-caused a Windows
  `UnicodeDecodeError: 'charmap'` warning to `subprocess.run(...,
  text=True)` calls with no explicit `encoding=`. The Run team fixed the
  two test-harness conftest sites; both the Run handoff and Manual Test's
  findings flagged that `tests/release/test_install_script.py` carries
  the **same latent pattern** and recommended a pre-emptive Release-side
  fix (it is Release territory, and `tests/release/` is yours).

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-release-team.md`
2. `.github/workflows/ci.yml` — the workflow you extend (read in full;
   it was just bumped to Node 24 action majors by `57cdf0d`)
3. `handoffs/coverage-team-2026-05-21-coverage-compare-perf.md` — the
   "For the companion Release task (PM note)" section: the perf test runs
   via `uv run pytest tests/perf`, needs only existing dev-deps
4. `tests/perf/coverage/test_perf_compare.py` — what the lane runs
5. `tests/release/test_install_script.py` (the `subprocess.run` at the
   bottom of the install-script invocation helper, ~line 175)
6. `findings/manual-test-team-2026-05-21-jest-charmap-encoding.md` — the
   "Pre-existing follow-up worth tracking" recommendation

---

## Slice A — non-blocking `tests/perf` CI lane

**Scope:** add a CI job that runs the coverage perf benchmark.

- New job in `.github/workflows/ci.yml` — a **separate `job`**, not a
  matrix cell of the existing `test` job.
- Single cell: `ubuntu-latest`, **one** Python version (`3.13` — do not
  matrix it).
- The job: `actions/checkout` → `astral-sh/setup-uv` →
  `uv sync --dev --frozen` → `uv run pytest tests/perf`.
- **No Node.js / jest-fixture install needed** — the perf test is
  pure-Python (`generate_large_fact_set.py` builds `CoverageFactSet`s
  programmatically; no native engine). Do NOT add the `setup-node` step
  or the fixture `npm install` loop to this job.
- **Non-blocking — this is mandatory.** The benchmark has a 5s NFR budget
  measured on shared GitHub runners with ±30-40% wall-clock variance; it
  must NOT gate PR merges. Use `continue-on-error: true` on the job (or
  an equivalent mechanism that keeps it off the required-check set).
  State in the handoff which mechanism you used and confirm it cannot
  block a merge.
- Reuse the **same action major pins** the `test` job now uses
  (`actions/checkout@v6`, `astral-sh/setup-uv@v7`) — keep the workflow
  internally consistent; do not introduce older majors.

**Constraints:**

- The existing `test` job (9-cell matrix) and the `pytest (release
  smoke)` step are untouched.
- `pyproject.toml` is NOT edited — `tests/perf/` is deliberately outside
  `[tool.pytest.ini_options].testpaths`; the lane opts in explicitly with
  the `tests/perf` path argument. (`pyproject.toml` dev-deps are your
  territory, but no new dependency is needed — `pytest` + `pytest-asyncio`
  already cover it, per the coverage-perf handoff.)

## Slice B — install-script test encoding hardening

**Scope:** in `tests/release/test_install_script.py`, the helper that
invokes the install script via `subprocess.run([...], capture_output=True,
text=True, timeout=30)` (~line 175) decodes the captured pipes with the
**parent's locale codec** because `text=True` is set with no explicit
`encoding=`. On a non-UTF-8-locale host this can mis-decode output (the
exact class of bug the jest-charmap cycle fixed in the CLI conftests).

- Add `encoding="utf-8"` to that `subprocess.run(...)` call.
- This is a one-keyword surgical change. Do NOT refactor the helper.
- `tests/release/` runs only on POSIX CI cells today, so this is
  pre-emptive hardening, not a live defect — keep it minimal.

## Files in scope

- `.github/workflows/ci.yml` — Slice A.
- `tests/release/test_install_script.py` — Slice B (one kwarg).

## Files NOT to touch

- `src/**` — no production code in this task.
- `tests/perf/**` — Coverage team's; you only invoke it from the workflow.
- `pyproject.toml` — no edit needed (see Slice A constraints).
- `tests/unit/**`, `tests/integration/**` — out of scope.

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
editing the workflow YAML and the test file.

## Verification (must pass before handoff)

- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
  → parses.
- `uv run pytest -q tests/release` → green (POSIX host) — confirms the
  `encoding=` change is behaviour-preserving.
- `uv run pytest tests/perf` → green — confirms the command the new lane
  runs works.
- `uv run pytest -q` → unchanged baseline (337 passed + 3 skipped) —
  confirms `tests/perf` is still not collected by the default run.
- Definitive signal: the post-merge CI run shows the new perf lane
  present, running, and **non-blocking**.

## Reporting

Write `agent-comms/handoffs/release-team-2026-05-21-ci-perf-lane.md`.

This task touches `tests/release/` (Slice B), so the WORKLOG hook **does**
fire: append a `WORKLOG.md` entry per its format, run
`python3 tools/regen_comms_index.py`, and stage `WORKLOG.md` + the new
`agent-comms/` files + `INDEX.md` alongside source.

**DoD bullets believed closed:** none — Slice A is CI tooling, Slice B is
pre-emptive hardening. Neither is a `delivery-phasing.md` DoD bullet.
State that explicitly. Report which non-blocking mechanism you chose for
the perf lane.
