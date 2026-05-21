---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
created: 2026-05-21
slug: coverage-compare-perf
verifies: verifications/2026-05-21-coverage-compare-perf.md
verdict: passed
---

# Findings: NFR-COV-002 50k-location perf benchmark for `coverage diff`

## Verdict: passed

## What was tested (plain language for the CEO)

One of our non-functional requirements (NFR-COV-002) says that comparing the
coverage data of two test runs must stay fast even on a large project — the
target being a project with 50,000 covered code locations on each side of the
comparison. The Coverage team added a performance benchmark that builds two
such large synthetic datasets and times the real comparison function.

The benchmark passes comfortably. On this machine the comparison takes about
**0.024 seconds** — roughly **125x faster** than the 3.0-second internal
budget (and the official NFR ceiling is 5.0 seconds). The result was stable
across four repeat runs. The benchmark is opt-in: it lives outside the normal
test suite, so it never slows down the everyday `pytest` run, and it does not
touch any product code or type-checking surface. I also separately drove the
real `coverage diff` command end-to-end through the CLI to confirm the
comparison path the benchmark stands in for actually works as a shipped
product feature.

## Commands run + observed output

1. **Perf suite (opt-in)** — `uv run pytest tests/perf -q`:
   ```
   [NFR-COV-002] compare_coverage_facts at 50,000 covered locations/side:
     median=0.024s over 5 runs (internal budget 3.0s, NFR ceiling 5.0s)
   3 passed in 0.23s
   ```

2. **Stability re-runs** — ran the perf suite 3 more times; medians observed:
   `0.024s`, `0.024s`, `0.023s`. Consistently ~125x under budget; no
   noisy-machine concern on this box.

3. **Default gate does NOT collect `tests/perf`** —
   `uv run pytest -q tests/unit tests/integration`:
   ```
   337 passed, 3 skipped in 12.82s
   ```
   Baseline unchanged; the 3 perf tests do not appear in the count. (The 3
   skips are the pre-existing Node-dependent jest integration tests.)

4. **Type-check sanity** — `uv run mypy`:
   ```
   Success: no issues found in 52 source files
   ```
   `tests/perf` is correctly outside the type-check surface.

5. **End-to-end CLI sanity (beyond the requested steps)** — copied the
   `pytest-coverage` fixture into the manual-test workspace, ran
   `novetest init`, executed two coverage runs via
   `novetest run --coverage`, then ran the real product command:
   ```
   novetest coverage diff <baseline-run-id> <target-run-id>
   → ok: true, coverage_delta.kind: "delta"
   ```
   The comparison the benchmark exercises directly (`compare_coverage_facts`)
   is correctly wired through the shipped CLI: two identical runs produce a
   well-formed zero delta (empty `file_deltas`/`files_added`/`files_removed`,
   matching `summary_before`/`summary_after`).

## Issues found

**None.** All four requested verification steps matched their expected output
exactly, and the additional end-to-end CLI exercise of the comparison path
passed.

## Recommendations for PM

- **Tick Phase 2 DoD #4** ("Performance NFR-COV-002 met on a fixture with 50k
  covered locations") — verified-passed. The benchmark is genuine (non-trivial
  50-added / 50-removed / 450-per-file-delta scenario, no zero-change fast
  path) and passes with ~125x headroom.
- No `src/` optimization was needed and none was made — `compare.py` and
  `coverage_fact_set.from_dict` are untouched, confirmed by the clean
  337-passed baseline and mypy on 52 source files.
- Re-dispatch the deferred Release "Slice B" task to wire a non-blocking
  `uv run pytest tests/perf` CI lane, now that `tests/perf/` is on `main`.
- Noisy-runner note for the future: a *single* timed run is not the gate (the
  benchmark takes the median of 5 runs after a warm-up); if the CI lane ever
  fails, suspect runner contention before a `compare.py` regression.
