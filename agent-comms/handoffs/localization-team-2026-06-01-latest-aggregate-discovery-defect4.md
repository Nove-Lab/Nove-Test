---
from: novetest-localization-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-06-01
slug: latest-aggregate-discovery-defect4
worktree: /home/yjshin/dev/novetest-localization-defect4
branch: novetest-localization-defect4
base_commit: 97285e5
related:
  - agent-comms/tasks/localization-team-2026-06-01-latest-aggregate-discovery-defect4.md
  - agent-comms/history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md
  - src/novetest/localization/retrieval.py
  - src/novetest/localization/derive.py
  - tests/integration/localization/test_latest_verb_non_per_test.py
---

# Handoff: Defect 4 — `localization latest` discoverability gate relaxation

Closes the carry-forward defect from the 2026-06-01 cycle. The
`check_localization_availability` gate now matches the 3-mode dispatch
in `derive_localization_findings`, so `novetest localization latest`
returns a fact-set (not `run_not_analyzable`) for the two modes that
were locked out.

## DoD bullets believed closed

- [x] `retrieval.py:check_localization_availability` returns `True` for
  runs with failed tests regardless of coverage shape (the relaxed gate
  per task brief §1).
- [x] Docstring updated to reflect the new semantics (task brief §2).
- [x] 3 new integration tests covering `latest` verb for all 3
  mode-dispatch paths (task brief §3, ALL in new file
  `tests/integration/localization/test_latest_verb_non_per_test.py`).
- [x] Pre-flight smoke C (per-test pytest) regression-pin via the new
  integration test `test_latest_verb_still_returns_per_test_finding_for_branch_fixture`.
- [x] Pre-flight smoke B (no-coverage pytest) via the new integration
  test `test_latest_verb_returns_failure_proximity_finding_for_no_coverage_fixture`.
- [ ] Pre-flight smoke A (cargo aggregate) **DEFERRED to Main Branch's
  equipped-host gate** — test is implemented + skip-guarded
  (`test_latest_verb_returns_aggregate_finding_for_cargo_fixture`); this
  dev box has no cargo toolchain on PATH so the test SKIPS here. Logic
  is identical to the explicit-`<run_id>` path that Manual Test
  reproduced in 2026-06-01 findings, so the cargo path is expected to
  PASS on equipped host.
- [x] Existing unit tests pass; mypy `--strict` clean; full suite green
  (`757 + 10` vs baseline `755 + 9`; delta = exactly the +3 new tests).

## What changed

### Source (2 files modified, ZERO new src files; count stays 72)

- **`src/novetest/localization/retrieval.py`** — dropped the coverage
  shape gate at the function tail; dropped two now-unused imports
  (`get_coverage_facts`, `CoverageUnavailable`); rewrote docstring to
  enumerate the new contract (non-tombstoned ∧ has-failed-tests) with
  rationale + cross-references.
- **`src/novetest/localization/derive.py`** — docstring of
  `resolve_latest_analyzable_run` updated to reference the relaxed
  gate; ZERO logic change to the function.

### Tests (4 files modified, 1 new file, +3 net tests)

- **`tests/unit/localization/test_retrieval.py`** — 2 cases flipped:
  - `test_availability_no_coverage_returns_false` → `..._returns_true_post_defect4` (assertion flipped, docstring rewritten)
  - `test_availability_coverage_not_per_test_returns_false` → `test_availability_aggregate_coverage_returns_true_post_defect4` (same)
- **`tests/unit/localization/test_latest_resolution.py`** — `_seed_unanalyzable_run` helper changed to seed a passing-only run (under the new contract, "failing + no coverage" is analyzable via failure_proximity, so passing-only is the cleanest "structurally unanalyzable" seed). 2 consuming tests retain their `REASON_RUN_NOT_ANALYZABLE` assertions unchanged.
- **`tests/integration/localization/test_latest_resolution_e2e.py`** — `test_resolve_latest_picks_failing_with_coverage_over_failing_without` renamed `test_resolve_latest_walks_past_passing_only_to_first_with_failed_tests`; assertion flipped from `failing_with_cov_ref` → `failing_no_cov_ref` (the middle candidate is now analyzable). 3-run seed structure preserved.
- **`tests/integration/localization/test_latest_verb_non_per_test.py`** (NEW, ~190 lines): the canonical "latest verb works for all 3 modes" regression-pin — 3 tests, one per dispatch path (aggregate/cargo skip-guarded, failure_proximity/pytest, per-test/pytest regression-pin).

## Pre-flight evidence

### Pre-flight A — cargo aggregate fixture (`localization-aggregate-only`)

**Status: SKIPPED on this dev box (no cargo toolchain). Test
implemented + skip-guarded; equipped-host empirical validation deferred
to Main Branch's FF-merge gate.**

The test `test_latest_verb_returns_aggregate_finding_for_cargo_fixture`
materializes the fixture, spawns the real cargo adapter with
`collect_coverage=True`, calls `derive_latest_localization(store)`, and
asserts `mode == "sbfl_aggregate"` + `confidence == "medium"` + Memory
flag flipped. Identical logic chain to the explicit-`<run_id>` path
that Manual Test reproduced in the 2026-06-01 findings (which confirmed
the explicit path returns `kind: "fact-set", mode: "sbfl_aggregate"`).
The ONLY difference between the two verbs is which entry-point function
is called — `derive_latest_localization` is a pure composition of
`resolve_latest_analyzable_run` (which uses the relaxed gate) +
`derive_localization_findings` (unchanged). Post-fix, the resolver
returns the cargo run instead of skipping it, and the dispatcher routes
it through `_derive_aggregate` exactly as in the explicit-verb case.

### Pre-flight B — no-coverage pytest fixture (`localization-no-coverage`)

**Status: PASSED.** Asserted by
`tests/integration/localization/test_latest_verb_non_per_test.py::test_latest_verb_returns_failure_proximity_finding_for_no_coverage_fixture`:

```
mode = "failure_proximity"
confidence = "low"
run_reference matches the run just stored
canonical findings file exists at <store>/localization/run_<id>/localization_findings.json
Memory has_localization_findings flag flipped to True
```

### Pre-flight C — per-test pytest fixture (`localization-branch`) regression-pin

**Status: PASSED.** Asserted by
`tests/integration/localization/test_latest_verb_non_per_test.py::test_latest_verb_still_returns_per_test_finding_for_branch_fixture`:

```
mode = "sbfl_per_test"           # unchanged from pre-Defect-4 behavior
confidence = "high"              # unchanged
run_reference matches
```

Load-bearing guard: this test proves the gate relaxation did NOT alter
the per-test path's discovery behavior. Without it, a future regression
that accidentally routed per-test through the aggregate path would not
surface in any other test.

### Full local gate

```
$ uv run pytest -q tests/unit tests/integration
757 passed, 10 skipped in 48.15s
```

Baseline at `97285e5` (origin/main tip) on the same Rust-less host:
**755 passed + 9 skipped**. Delta = **+2 passed + 1 skipped = exactly
the 3 new integration tests** (2 pytest paths pass + 1 cargo path
skipped on this box). Zero regressions.

```
$ uv run mypy
Success: no issues found in 72 source files
```

Source-file count unchanged at 72 (pure logic-tightening; no new src
files).

## `delivery-phasing.md` checkbox implications

**None directly.** Phase 4 §4 #2 was already ticked at the prior cycle
close; this slice just closes the discoverability bug exposed by it.
After this merges, all the strategy doc §2 3-mode dispatch works
end-to-end across BOTH verbs (`localization <run_id>` AND `localization
latest`) for all 4 currently-supported languages — that's the END of
Phase 4 §4 modes-related work as the task brief noted.

## Deviations from task brief

**None of consequence.**

- Brief mentioned "implementer's call" on whether to keep the
  `get_coverage_facts` lookup at line 96 as a no-op or remove it; I
  removed it (cleaner — mypy strict would flag a `del coverage` no-op
  against the import otherwise, and the import itself becomes orphaned).
- Brief estimated "0-2 tests" might need flipping for the old per-test
  gate contract; flipped 2 (in line with the upper bound). Also adjusted
  1 helper + 1 integration test that pinned a related "no coverage →
  skip" semantic — those weren't in the brief's scope-estimate but they
  pinned the same load-bearing contract and would have failed otherwise.
- The integration test file is NEW (one of the two options the brief
  offered — the other was extending `test_mode_selection_per_engine.py`).
  Created new because the existing file tests `derive_localization_findings`
  directly while this slice's surface is `derive_latest_localization`;
  splitting keeps each file's surface concept-coherent.

## Open questions for PM

1. **Equipped-host validation of Pre-flight A** is the only piece
   deferred outside this team. Main Branch's FF-merge gate should
   confirm `test_latest_verb_returns_aggregate_finding_for_cargo_fixture`
   PASSES (skipped here, expected to pass on equipped). If it fails,
   the failure mode would surface a Defect-4-adjacent issue that the
   logic analysis couldn't predict — but the logic chain to the
   explicit-`<run_id>` cargo path is identical, and that one is
   verified passing in Manual Test's 2026-06-01 findings.
2. **Documentation cross-reference**: this slice's WORKLOG entry and
   handoff both reference `history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md`
   §"Defect 4". The history doc is the canonical narrative; verify it
   has the §"Defect 4" anchor referenced. If renaming is needed, both
   the source docstring at `retrieval.py:79-83` and the test docstrings
   at `test_retrieval.py:141` would need updating.
3. **The 3-mode dispatcher's contract is now formally pinned by the
   gate** — any future addition of a 4th mode (e.g. a hypothetical
   "delta-debugging" path post-MVP) would need to add its precondition
   to both `derive_localization_findings`'s dispatcher AND the gate
   here. Worth noting in the strategy doc §2 mode table if it lands.

## End-of-work checklist status

1. [x] `WORKLOG.md` entry appended (newest entry at top, under format).
2. [x] Handoff doc (this file) written.
3. [x] `python3 tools/regen_comms_index.py` will be run before commit
   (the staging step bundles `INDEX.md` alongside the new comms file).
4. [x] All of `WORKLOG.md` + this handoff + `INDEX.md` will be staged
   alongside src + test changes for the commit.
