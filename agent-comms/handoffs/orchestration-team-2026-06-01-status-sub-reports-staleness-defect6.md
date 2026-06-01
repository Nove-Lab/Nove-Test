---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: pending
created: 2026-06-01
slug: status-sub-reports-staleness-defect6
related:
  - agent-comms/tasks/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
worktree: /home/yjshin/dev/novetest-status-defect6
branch: worktree-status-sub-reports-staleness-defect6
---

# Handoff: Orchestration — `status.sub_reports.*` reflects on-disk derived facts (Defect 6)

## TL;DR

Lifted the SAME cache-only retrieval functions `inspect.py` already
uses into `status.py::build_status_view`, so `novetest status`
envelope's `data.sub_reports.{coverage,localization,regression}` now
report `"available"` whenever the corresponding `*_facts.json` /
`*_findings.json` is on disk for the latest run — instead of being
hard-defaulted to `"unavailable"` regardless of cache state. **Cache-
only contract preserved**: the regression flag uses
`get_regression_facts` (not `compare_runs`), so a pair that has never
been compared still surfaces `"unavailable"` — `status` does NOT
derive on miss.

Defect-6 root cause + fix in one sentence: the Phase 1 stub left the
three `*_available: bool` fields at their `False` default; the fix
populates them via the engine `get_*` cache-read helpers and an
`isinstance(result, FactSet)` discriminator check, mirroring
`inspect.py`'s pattern.

## Worktree / files / pytest counts / mypy

- **Worktree**: `/home/yjshin/dev/novetest-status-defect6`
- **Branch**: `worktree-status-sub-reports-staleness-defect6` (based on `origin/main` tip `0ed8fe4`)
- **Commits on branch**: 1 (`feat(orchestration): status sub_reports reflect on-disk facts (Defect 6)`) — single self-contained slice.

### Files touched

| File | Kind | Lines | Notes |
|---|---|---|---|
| `src/novetest/orchestration/workflows/status.py` | modified | +85 / −9 | Imports, docstring rewrite, populated `StatusView`, new helper `_latest_regression_available` |
| `tests/unit/orchestration/workflows/test_status.py` | new | +530 | 12 unit cases |
| `tests/integration/cli/test_status_inspect_consistency_e2e.py` | new | +310 | 2 integration cases |
| `WORKLOG.md` | modified | +6 lines top entry | Standard per-cycle entry |

### Verification

- **Full pytest gate** (`uv run pytest -q tests/unit tests/integration`):
  - **771 passed + 10 skipped in 51.93s** (baseline 757+10 → +14 net = 12 unit + 2 integration).
- **mypy `--strict`**: `Success: no issues found in 72 source files` (unchanged file count — pure logic change in an existing module + tests).
- **Manual smoke** — see "Empirical reproduction" below for the verbatim pre-fix vs post-fix envelopes against an identically-seeded `.novetest/` directory.

## Worklog entry text

Single top entry in `WORKLOG.md` for `2026-06-01 — phase4 /
status-sub-reports-staleness-defect6`. Six sub-bullets (Landed /
Verified / Left open / Gotcha / Next).

## Envelope-schema implications

**None.** The wire shape of the `status` envelope is unchanged — same
top-level keys (`latest_run_reference`, `run_history_size`,
`sub_reports`) and same `sub_reports` keys (`coverage`, `regression`,
`localization`, `replay`). Only the VALUES change semantically:
pre-fix three of the four were stuck at `"unavailable"` regardless of
state; post-fix they reflect cache existence. The
`{"available", "unavailable"}` value set is unchanged.

Envelope schema bump: NOT required.
`decisions/2026-04-?? cli-envelope-v1` (the v1 schema decision) does
NOT pin the semantic meaning of `sub_reports.*` values — only the
key/value-set surface — so this fix is fully within the v1 contract.

## DoD bullets believed closed

(PM verifies; team does NOT tick `delivery-phasing.md`.)

- [ ] `status.sub_reports.*` reflects on-disk derived facts for
      coverage + localization + regression + replay.
  - **Believed closed**: `build_status_view` now calls
    `get_coverage_facts` / `get_localization_findings` /
    `get_regression_facts` and discriminates `isinstance(result,
    FactSet)`. Replay stays `False` (engine module is empty pending
    Phase 5; the one-line switch is staged but does not fire).
- [ ] Cross-check consistency: `status` ↔ `inspect` ↔ direct verb
      agreement for all 4 sub-engines on a cargo aggregate run.
  - **Believed closed**: integration test
    `test_status_inspect_localization_agree_on_availability` pins
    all three sources of truth (status sub_reports, inspect outcomes,
    direct localization verb) agreeing on the same seeded store with
    coverage + localization + regression facts all persisted. Used
    OS-portable pytest-shaped seed; cargo-aggregate equivalence pinned
    at unit level by
    `test_defect6_aggregate_granularity_coverage_facts_marks_coverage_available`.
- [ ] Sub-observation addressed: `inspect.coverage_outcome.percent_covered`
      matches `summary.percent_covered` (or vestigial field removed).
  - **Believed closed; disposition is "explained-as-intended"** — see
    "Sub-observation disposition" below. The integration test
    `test_inspect_coverage_percent_covered_lives_under_summary_only`
    pins both halves: canonical nested path returns the seeded value
    (85.71) AND the top-level key is genuinely absent.
- [ ] Unit + integration tests per §4.
  - **Believed closed**: 12 unit cases in
    `tests/unit/orchestration/workflows/test_status.py` (empty store,
    no-facts, per-test coverage, aggregate coverage [Defect-6 pin],
    localization per-test, localization failure_proximity, regression
    cached, regression not cached, single-run, tombstoned priors,
    replay pinned False, wire-shape pin). 2 integration cases in
    `tests/integration/cli/test_status_inspect_consistency_e2e.py`
    (cross-source-of-truth + sub-observation pin).
- [ ] Full pytest suite green; mypy strict clean.
  - **Believed closed**: 771 passed + 10 skipped (no failures, no new
    skips); mypy strict clean at 72 source files (unchanged count —
    pure logic change in an existing src module).
- [ ] No `delivery-phasing.md` checkbox movement (bug fix).
  - **Believed closed**: zero edits to `design/implementation-plan/delivery-phasing.md`.

## Root cause documented

`src/novetest/orchestration/workflows/status.py::build_status_view`
shipped in Phase 1 as a stub that only populated `latest_entry` +
`run_history_size`, leaving the three `*_available: bool` fields at
their `StatusView` dataclass default of `False`. The dataclass already
had the slots (`coverage_available`, `regression_available`,
`localization_available`, `replay_available`) and the `to_dict` shape
was complete (mapping `True/False` → `"available"/"unavailable"`) —
the populated end-to-end path was just never wired.

When Phase 2 (Coverage), Phase 3 (Regression), and Phase 4
(Localization) engines shipped their `get_*` cache-read helpers, the
`inspect` workflow correctly adopted them in `_resolve_inspect_*`
helpers — but `build_status_view` was not updated symmetrically. The
result was a deceptive `status` envelope that said `"unavailable"` for
every engine despite the on-disk facts being present and `inspect`
correctly reading them.

Manual Test's reproduction (`/tmp/d4-cargo` against the cargo
aggregate run) surfaced the symptom; the hypothesis ("status uses an
over-restrictive precondition probe symmetric to Defect 4") was close
but slightly off — the actual gap was even simpler: NO probe at all
fired; the flags were hardcoded False.

The fix lifts the same cache-only retrieval functions `inspect.py`
uses into `build_status_view`, using `isinstance(result, FactSet)` to
compute the boolean. The cache-only contract is preserved (status does
NOT call `compare_runs`, which would derive on miss — only
`get_regression_facts`, the pure cache-read).

## Empirical reproduction (verbatim, pre-fix vs post-fix)

**Setup** (identical for both branches — seeded once, queried twice):

```python
# Direct-API seed via Memory + Coverage persistence helpers (no cargo
# toolchain needed on the test runner). Mirrors what a real cargo
# aggregate run would persist.
from novetest.memory.project_store import create_project_store
from novetest.memory.store import store_run_evidence
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.models.coverage_fact_set import (
    CoverageFactSet, CoverageSummary, FileCoverage,
)
from novetest.coverage.persistence import write_coverage_facts

store = create_project_store(ws)
ref = RunReference(run_id='01D6SMOKE000000000000000A', created_at=1)
rec = RunRecord(
    run_reference=ref, target_expression='tests/', target_type='dir',
    engine_name='cargo-test', engine_version='1.0', ecosystem='rust',
    status='failed', started_at=1, completed_at=2,
    test_results=(TestResult(node_id='tests::buggy', outcome='failed', duration_ms=10),),
)
store_run_evidence(store, rec)

summary = CoverageSummary(
    num_statements=7, covered_statements=6, missing_statements=1,
    excluded_statements=0, num_branches=0, covered_branches=0,
    missing_branches=0, percent_covered=85.71,
)
fc = FileCoverage(
    file_path='src/buggy.rs',
    executed_lines=(1, 2, 3, 4, 5, 6), missing_lines=(7,),
    excluded_lines=(), executed_branches=(), missing_branches=(),
    summary=summary,
)
fs = CoverageFactSet(
    run_reference=ref, engine_name='cargo-test', ecosystem='rust',
    mapping_granularity='aggregate',  # ← the Defect-6 trigger shape
    summary=summary, files=(fc,), derived_at=3,
)
write_coverage_facts(store, fs)
# coverage_facts.json now exists on disk for run 01D6SMOKE...
```

**PRE-FIX** (main branch `0ed8fe4`):

```
$ cd <seeded_ws> && NOVETEST_OUTPUT=json <main.venv>/bin/python -m novetest status
{
  "ok": true,
  "command": "status",
  "data": {
    "latest_run_reference": {"run_id": "01D6SMOKE000000000000000A", ...},
    "run_history_size": 1,
    "sub_reports": {
      "coverage": "unavailable",      ← ← ← LIES. coverage_facts.json IS on disk.
      "localization": "unavailable",
      "regression": "unavailable",
      "replay": "unavailable"
    }
  }
}
```

**POST-FIX** (worktree branch tip):

```
$ cd <seeded_ws> && NOVETEST_OUTPUT=json <worktree.venv>/bin/python -m novetest status
{
  "ok": true,
  "command": "status",
  "data": {
    "latest_run_reference": {"run_id": "01D6SMOKE000000000000000A", ...},
    "run_history_size": 1,
    "sub_reports": {
      "coverage": "available",        ← ← ← TRUTHFUL. Matches inspect + on-disk file.
      "localization": "unavailable",  ← localization_findings.json NOT seeded
      "regression": "unavailable",    ← single-run store → no pair, correct
      "replay": "unavailable"         ← Phase 5 not shipped, correct
    }
  }
}
```

**Cross-check post-fix** (third source of truth, on-disk + `inspect`):

```
$ cd <seeded_ws> && <worktree.venv>/bin/python -m novetest inspect 01D6SMOKE000000000000000A
... coverage_outcome.kind: "fact-set"                 ← agrees with status
... sub_reports.coverage: "available"                 ← agrees with status
... coverage_outcome.summary.percent_covered: 85.71   ← canonical nested path returns seeded value
... coverage_outcome.percent_covered (top-level):     ← KEY ABSENT (correct; not vestigial)
```

Three sources of truth (`status`, `inspect`, on-disk file) NOW
agree by construction because all three read the same underlying
cache.

## Sub-observation disposition

**`inspect.coverage_outcome.percent_covered: None`** — Manual Test's
suspected "vestigial top-level field" or "wrong-path read".

**Disposition: explained-as-intended; no code change.**

The wire shape per `decisions/2026-05-16-coverage-outcome-envelope-shape.md`
nests `percent_covered` under `summary`:

```
coverage_outcome = {
  "kind": "fact-set",
  "run_reference": {...},
  "mapping_granularity": "...",
  "summary": {
    ...
    "percent_covered": 85.71,   ← canonical position
    ...
  },
}
```

There is NO top-level `percent_covered` field anywhere in the
codebase. `grep -rn percent_covered src/` returns only `CoverageSummary`'s
attribute + `from_dict` parsing + the LCOV/Istanbul parser computations.
The orchestration `_coverage_outcome_section` (in `inspect.py` line
209-237) projects ONLY `{kind, run_reference, mapping_granularity,
summary}` for the `fact-set` branch — no top-level `percent_covered`
is ever emitted.

Manual Test's `dict.get('percent_covered')` against `coverage_outcome`
returned `None` simply because the key doesn't exist at that level;
the canonical path is `coverage_outcome["summary"]["percent_covered"]`.
This is NOT a vestigial field to remove (it doesn't exist) and NOT a
wrong-path code-side read (no Python code reads a non-existent
top-level key — only Manual Test's `.get()` did).

The integration test
`test_inspect_coverage_percent_covered_lives_under_summary_only`
pins both halves as a regression guard:
- `coverage_outcome["summary"]["percent_covered"] == 85.71` (canonical
  path returns the seeded value)
- `"percent_covered" not in coverage_outcome` (top-level key is
  genuinely absent — defends against later patches accidentally
  introducing it as a wrong-path read).

Documenting in this handoff so PM has the disposition recorded in
the next history entry. If PM disagrees with the disposition (e.g.,
wants a top-level `percent_covered` convenience field exposed for AI
agents who consume the envelope without diving into `summary`), that
would be an envelope-shape change requiring a follow-up `decisions/`
entry and a separate orchestration slice.

## Open questions for PM

1. **Replay availability wiring on Phase 5 entry.** The current code
   leaves `replay_available` pinned to `False` in `build_status_view`
   with a comment `# Replay stays False — the engine ships post-MVP
   (Phase 5).` When Replay ships, the symmetric one-line addition is:
   ```python
   replay_available = isinstance(
       get_replay_finding(store, latest_ref), ReplayFinding
   )
   ```
   (assuming the Replay engine follows the same `get_*` + discriminator
   convention as the other three engines). Want this stubbed now with
   a `TODO(phase5)` import marker, or wait until the Replay engine's
   public API actually lands? Current handoff defers to the latter —
   the unit test `test_replay_pinned_unavailable_until_phase5` is a
   regression-pin against accidentally flipping the flag before the
   engine ships.

2. **Sub-observation framing in next history entry.** PM's next
   history file will summarize Defect 6 closure; recommend including
   the sub-observation disposition ("explained-as-intended; canonical
   path is `coverage_outcome.summary.percent_covered`; no top-level
   field exists") so future Manual Test exploration doesn't re-surface
   the same hypothesis. If PM wants this called out more visibly
   (e.g., as a brief in `design/interace-contract/orchestration.md`
   explicitly noting the nested location), that's a small follow-up
   doc PR.

3. **The brief's "10-line src change" estimate.** The actual src
   diff was +85/−9 lines (one populated function + one new ~25-line
   helper + a docstring rewrite from the Phase 1 stub language to
   the post-Defect-6 contract). Brief's "10-line" estimate undershot
   the docstring + helper extraction; the LOGIC change is genuinely
   small (4 isinstance checks + the helper), so the spirit holds.
   No question pending — just calling out the discrepancy so PM's
   future estimates calibrate accordingly.

## Cross-references

- **Origin of Defect 6 + reproduction**:
  `agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md`
  §"Defect 6 surfaced".
- **Task brief**:
  `agent-comms/tasks/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md`.
- **Symmetric prior fix (Defect 4 — same shape, different file)**:
  `agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md`
  §"What shipped".
- **Sibling Defect 5 slice (independent, parallel-dispatchable)**:
  `agent-comms/tasks/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md`.
- **Envelope shape decision** (anchors the sub-observation disposition):
  `agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md`.

## Next step (suggested)

Main Branch team:
1. FF-merge `worktree-status-sub-reports-staleness-defect6` into `main`.
2. Push `main` to `origin/main`.
3. Run the equipped-host gate (`uv run pytest -q tests/unit
   tests/integration`) — expect 771+10 (or higher if Defect 5 has
   landed in parallel; mod up by the Defect-5 test delta).
4. Write the verification request to Manual Test pointing them at
   Scenario H reproduction on `/tmp/d4-cargo` (or a fresh equivalent)
   — pre-fix `sub_reports.coverage == "unavailable"`, post-fix
   `sub_reports.coverage == "available"`, three sources of truth
   agreeing.

Manual Test team (after Main merges + dispatches):
1. Reproduce Defect 6's empirical evidence verbatim against a
   cargo-aggregate workspace and confirm post-fix envelope.
2. Spot-check the sub-observation pin: navigate to
   `coverage_outcome.summary.percent_covered` (not the top level) and
   confirm the value matches the on-disk file.
3. Field-test the `status` ↔ `inspect` ↔ direct-verb agreement on a
   workspace with all four kinds of facts persisted (run with
   `--coverage`, derive localization, run `compare`/`regression
   compare`).
