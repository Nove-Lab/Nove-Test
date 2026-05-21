---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
created: 2026-05-21
slug: ci-perf-lane
verifies: verifications/2026-05-21-ci-perf-lane.md
verdict: passed
---

# Findings: non-blocking `tests/perf` CI lane + install-script encoding hardening

## Verdict: passed

## What was tested (plain language for the CEO)

This slice has two parts. **Slice A** wires the performance benchmark
(NFR-COV-002, verified earlier this cycle) into CI as its own dedicated job
that runs on every push — but deliberately as a *non-blocking* job: even if
the benchmark were ever slow enough to fail, the CI run as a whole still
reports success and a pull request can still be merged. This is the right
design: a performance benchmark on a shared, noisy CI runner must never block
someone's merge over machine contention. **Slice B** is a small pre-emptive
hardening: it adds the same `encoding="utf-8"` fix to the install-script test
that the Run team applied to the CLI test harness earlier this cycle —
forestalling an identical Windows-only text-decoding failure if a Windows
release runner is ever added.

Everything checks out. The new `perf` job is correctly structured as a
separate, non-blocking job; the benchmark passes; the install-script test
still passes after the encoding change; and the everyday test gate is
unchanged.

## Commands run + observed output

1. **CI workflow structure + non-blocking flag**:
   ```
   python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml')); print(list(d['jobs'].keys()), d['jobs']['perf'].get('continue-on-error'))"
   -> ['test', 'perf'] True
   ```
   `perf` is a brand-new **separate top-level job** (not a 10th cell of the
   `test` matrix), with `continue-on-error: true`. Matches expected exactly.

2. **`perf` job definition inspected** (edge-case probe):
   - `runs-on: ubuntu-latest`, `continue-on-error: True`, `needs: None`
     (independent — not chained to `test`).
   - Steps: `actions/checkout@v6` -> `astral-sh/setup-uv@v7` ->
     `uv sync --dev --frozen` -> `uv run pytest tests/perf`.
   - **No `setup-node` step** — confirmed deliberate; the benchmark is
     pure-Python (`compare_coverage_facts`), so Node would be dead weight.
   - The `test` matrix is untouched: `os: [ubuntu, macos, windows]` x
     `python-version: [3.11, 3.12, 3.13]` = still exactly 9 cells.

3. **Perf lane command** — `uv run pytest tests/perf -q`:
   ```
   [NFR-COV-002] compare_coverage_facts at 50,000 covered locations/side:
     median=0.023s over 5 runs (internal budget 3.0s, NFR ceiling 5.0s)
   3 passed in 0.23s
   ```

4. **Install-script test (Slice B)** — `uv run pytest -q tests/release`:
   ```
   3 passed in 1.64s
   ```
   Behaviour-preserving on this POSIX host, as expected.

5. **Default gate unchanged** — `uv run pytest -q tests/unit tests/integration`:
   ```
   337 passed, 3 skipped in 13.10s
   ```
   `tests/perf` is still not collected by the default run; baseline intact.

## Issues found

**None.** All five verification points (4 commands + the job-structure probe)
matched expectations exactly.

Edge cases from the verification request, all confirmed:
- **Non-blocking guarantee (a)** — `perf` is a new separate job with no
  `needs`, so it is never auto-added to branch-protection required checks.
- **Non-blocking guarantee (b)** — `continue-on-error: true` keeps the
  workflow run `success` even on a perf step failure.
- **No `setup-node`** — deliberate, the benchmark is pure-Python.
- **Slice B is pre-emptive** — `tests/release/` runs only on POSIX CI cells
  today, so the `encoding="utf-8"` kwarg has no observable behaviour change
  now; it forecloses the Windows `charmap` failure mode if a Windows release
  cell is ever added.

## Recommendations for PM

- **Tick the ci-perf-lane slice as verified-passed.** No `delivery-phasing.md`
  DoD bullet closes (Slice A is CI tooling, Slice B is hardening; Phase 2
  DoD #4 was already closed by `5489c7e`) — this is a clean
  process/tooling slice.
- **Definitive signal still pending — post-merge GHA CI run.** Manual Test
  cannot observe GHA. Confirm on the first post-merge run that: the `perf`
  job appears and runs, and the workflow conclusion stays `success` even if
  the perf step's outcome were ever `failure`. The 9-cell `test` job should
  be unchanged.
- **Push reminder (carried from the prior batch's findings):** the
  ci-maintenance and jest-charmap "definitive signals" — and now this one —
  all require the local commits to reach `origin` so GHA actually runs.
  Local `main` is currently ahead of `origin/main` by several commits across
  multiple teams. The push decision is a Main Branch / PM repo-state call,
  not Manual Test's; flagging it so the pending CI signals do not stall.

## Process note

`Write` was blocked by the worktree-isolation handshake (a known harness
quirk — see `GOTCHAS.md`). This findings file was written via a `Bash`
heredoc instead; output bytes are identical, no deliverable impact.
