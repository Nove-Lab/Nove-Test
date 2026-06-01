---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-06-01
slug: status-sub-reports-staleness-defect6
merged_commit: 0895e59
source_handoffs:
  - agent-comms/handoffs/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md
source_tasks:
  - agent-comms/tasks/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md
related:
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
  - agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md
  - src/novetest/orchestration/workflows/status.py
  - src/novetest/orchestration/workflows/inspect.py
---

# Verification: Defect 6 closed — `status.sub_reports.*` reflects on-disk derived facts

## Merged commit + summary

**Merged at**: `0895e59` (rebased from `9ba8e34`; WORKLOG conflict
resolved surgically with incoming-on-top convention).

Pre-fix, `novetest status` envelope's `data.sub_reports.*` was hard-
defaulted to `"unavailable"` for coverage / localization / regression
regardless of on-disk state. The Phase 1 stub `build_status_view` left
the three `*_available: bool` fields at their `False` default; the
populated end-to-end path was never wired even after Phase 2 / 3 / 4
engines shipped their `get_*` cache-read helpers.

Post-fix, `build_status_view` lifts the SAME cache-only retrieval
functions `inspect.py` already uses (`get_coverage_facts` /
`get_localization_findings` / `get_regression_facts`) and uses
`isinstance(result, FactSet)` to compute each boolean flag. The
cache-only contract is preserved: `status` does NOT derive on miss
(it does NOT call `compare_runs` for regression; only the pure cache-
read). `replay_available` stays pinned `False` with a regression-pin
test guarding against accidental flip before the engine ships in
Phase 5.

**Net surface**: 1 src file modified (+85 / −9 in `status.py` — 
~50 logic + ~35 docstring; ZERO new src files; count stays at 72),
2 new test files (12 unit cases + 2 integration cases; +14 net tests).

**Test counts** (equipped host, cargo on PATH):
- Pre-merge gate on worktree: **776 + 5** (= 762 baseline + 14 new)
- Post-merge gate on main: **776 + 5** (no further delta; D5 sibling
  in same cycle had +0 test count delta)
- mypy `--strict`: **Success: no issues found in 72 source files**

## Source handoffs consumed

1. `agent-comms/handoffs/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md` — single handoff for the single-commit slice.

## What to verify (7 scenarios for Manual Test)

> **Note for Manual Test**: All envelope literals were verified by
> Main Branch dry-running each scenario against the merged tip
> (`0895e59`).

### Scenario A — `status.sub_reports.coverage` flips post `run --coverage`

The canonical Defect 6 closure proof (and Manual Test's original
Defect 6 reproduction surface).

**Setup**:
```sh
. "$HOME/.cargo/env"
cp -r tests/fixtures/projects/localization-aggregate-only /tmp/d6-cargo
cd /tmp/d6-cargo
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run --coverage >/dev/null 2>&1
```

**Probe**:
```sh
novetest status
```

**Expected envelope** (verbatim from merged tip):
```json
{
  "command": "status",
  "data": {
    "latest_run_reference": {
      "created_at": <timestamp>,
      "run_id": "<RUN_ID>",
      "schema_version": 1
    },
    "run_history_size": 1,
    "sub_reports": {
      "coverage": "available",
      "localization": "unavailable",
      "regression": "unavailable",
      "replay": "unavailable"
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

**Pre-fix would have returned** (Manual Test's original reproduction):
```json
"sub_reports": {
  "coverage": "unavailable",        // ← LIES (coverage facts exist on disk)
  "localization": "unavailable",
  "regression": "unavailable",
  "replay": "unavailable"
}
```

**What to assert**:
- `sub_reports.coverage == "available"` (FIX WORKING — pre-fix this was `"unavailable"`)
- `sub_reports.localization == "unavailable"` (no derive yet — Scenario B flips this)
- `sub_reports.regression == "unavailable"` (single-run store, no pair to compare)
- `sub_reports.replay == "unavailable"` (Phase 5 not shipped)
- `latest_run_reference.run_id` matches the run just executed
- `run_history_size == 1`

### Scenario B — `sub_reports.localization` flips post `localization latest`

**Setup**: re-use Scenario A's `/tmp/d6-cargo`.

**Probe**:
```sh
novetest localization latest >/dev/null
novetest status
```

**Expected**:
```json
"sub_reports": {
  "coverage": "available",
  "localization": "available",   // ← FLIPPED post-derive
  "regression": "unavailable",
  "replay": "unavailable"
}
```

**What to assert**:
- `sub_reports.localization == "available"` (FIX WORKING — pre-fix
  this stayed `"unavailable"` even after derive)
- `sub_reports.coverage` stays `"available"` (no regression from
  Scenario A)
- `sub_reports.regression` stays `"unavailable"` (no pair to compare
  in single-run store)
- `sub_reports.replay` stays `"unavailable"` (Phase 5 guard)

### Scenario C — Cross-source-of-truth: status ↔ inspect ↔ on-disk all agree

This is the load-bearing "no more lying" pin. Three sources of truth
about a single run's availability MUST agree.

**Setup**: re-use Scenario A's `/tmp/d6-cargo` (post-Scenario B
state).

**Probe**:
```sh
RUN_ID=$(novetest status 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['latest_run_reference']['run_id'])")
echo "RUN_ID=$RUN_ID"

echo "===STATUS sub_reports==="
novetest status 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['sub_reports'])"

echo "===INSPECT outcomes==="
novetest inspect "$RUN_ID" 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('cov:', d['data']['coverage_outcome']['kind'], '| loc:', d['data']['localization_outcome']['kind'])"

echo "===ON-DISK==="
ls .novetest/coverage/facts/run_$RUN_ID/coverage_facts.json
ls .novetest/localization/findings/run_$RUN_ID/localization_findings.json
```

**What to assert** (all three sources agree):
- `status.sub_reports.coverage == "available"` ↔ `inspect.coverage_outcome.kind == "fact-set"` ↔ `coverage_facts.json` exists on disk
- `status.sub_reports.localization == "available"` ↔ `inspect.localization_outcome.kind == "fact-set"` ↔ `localization_findings.json` exists on disk

### Scenario D — Sub-observation pin: `inspect.coverage_outcome.percent_covered` lives ONLY under `summary`

Per Loc team's handoff §"Sub-observation disposition" — the Manual
Test §H sub-observation `percent_covered: None` was **explained-as-
intended**: the canonical path is `coverage_outcome.summary.percent_covered`,
not `coverage_outcome.percent_covered` (which simply doesn't exist).

**Setup**: re-use Scenario A's `/tmp/d6-cargo`.

**Probe**:
```sh
RUN_ID=$(novetest status 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['latest_run_reference']['run_id'])")

echo "===Canonical path==="
novetest inspect "$RUN_ID" 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['coverage_outcome']['summary']['percent_covered'])"
# Expected: 85.71 (or whatever the real fixture coverage %)

echo "===Top-level (should be ABSENT, not None)==="
novetest inspect "$RUN_ID" 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); co=d['data']['coverage_outcome']; print('percent_covered' in co)"
# Expected: False (KEY ABSENT entirely)
```

**What to assert**:
- `coverage_outcome.summary.percent_covered` is a numeric value (the
  fixture's actual coverage %, e.g., 85.71)
- `'percent_covered' in coverage_outcome` returns `False` (the
  top-level key is genuinely absent — Loc team's regression-pin
  `test_inspect_coverage_percent_covered_lives_under_summary_only`
  asserts this)

This pins the disposition for future Manual Test exploration: don't
re-surface this as a defect; the field is correctly nested.

### Scenario E — Empty / no-facts store keeps sub_reports unavailable

The fix did NOT relax the gate entirely — it just stopped LYING when
facts exist. Verify the gate still correctly reports `"unavailable"`
when no facts exist.

**Setup** (NO `run --coverage`):
```sh
mkdir -p /tmp/d6-empty && cd /tmp/d6-empty
cat > pyproject.toml <<'PYEOF'
[project]
name = "empty-store-test"
version = "0.0.1"
requires-python = ">=3.9"
PYEOF
mkdir tests && cat > tests/test_pass.py <<'PYEOF'
def test_one(): assert True
PYEOF
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run >/dev/null 2>&1   # NO --coverage
novetest status
```

**Expected**:
```json
"sub_reports": {
  "coverage": "unavailable",
  "localization": "unavailable",
  "regression": "unavailable",
  "replay": "unavailable"
}
```

**What to assert**:
- All four sub_reports stay `"unavailable"` (no facts exist on disk
  for this run → all four correctly reported absent)

### Scenario F — Regression flag stays unavailable when no compare has been run

The fix uses `get_regression_facts` (cache-read), NOT `compare_runs`
(which would derive on miss). So a single-run store should keep
`regression: "unavailable"` even though both `coverage` and
`localization` are `"available"`.

**Setup**: re-use Scenario A's `/tmp/d6-cargo` (Scenarios A+B done).

**Probe**:
```sh
novetest status
```

**Expected**:
```json
"sub_reports": {
  "coverage": "available",
  "localization": "available",
  "regression": "unavailable",   // ← single-run; no pair to compare
  "replay": "unavailable"
}
```

**What to assert**:
- `regression == "unavailable"` despite coverage + localization both
  available (proves status reads `get_regression_facts` not
  `compare_runs`)

**Optional follow-up** (if you want to flip the regression flag too):
```sh
# Run a second time to create a pair
novetest run --coverage >/dev/null 2>&1
# Trigger regression derive
novetest regression compare >/dev/null 2>&1 || echo "regression compare may need flags"
novetest status
```

If the regression compare verb succeeds, `sub_reports.regression`
should flip to `"available"` post-compare (and stay `"available"`
on subsequent status calls until a new run breaks the pair).

### Scenario G — Replay flag stays pinned `False` (Phase 5 guard)

**Probe** (re-use any Scenario's store):
```sh
novetest status 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['sub_reports']['replay'])"
```

**Expected**: `unavailable`

**What to assert**:
- `replay == "unavailable"` ALWAYS (regardless of any prior runs / coverage / localization state)
- Per Orch team's handoff §"Open question 1": there's a unit test
  `test_replay_pinned_unavailable_until_phase5` that's a regression-
  pin against accidentally flipping this flag before the Replay
  engine ships.

This is a Phase 5 entry signal — when Replay ships, this scenario
will need an update (and the unit test pin will need to be removed).

## Critical edge cases worth probing

1. **Tombstoned run**: if the latest run is tombstoned (manually
   marking it as orphaned), does `status` correctly report
   `sub_reports.*` as `"unavailable"` even if facts exist on disk?
   The cache-read functions return the cache regardless of tombstone
   status, but the Memory Entry's tombstone flag is the source of
   truth for "is this run analyzable".

2. **Mid-cycle interruption**: if `run --coverage` is killed
   mid-execution (Ctrl-C), the partial state on disk — `coverage_facts.json`
   missing or truncated, run record present — should produce a
   `sub_reports.coverage: "unavailable"` (cache-read returns
   CoverageUnavailable). Worth confirming the failure mode is
   graceful.

3. **Mixed-engine store**: pytest run with `--coverage` THEN cargo
   run with `--coverage` in the same `.novetest/` store. `status`
   should report the LATEST run's sub_reports (cargo's), not the
   pytest's. Resolver is `latest_entry`-based per the handoff.

4. **Concurrent reads**: two `novetest status` calls running
   simultaneously against the same store. Each should produce the
   same envelope (pure cache reads, no mutating state). Worth a
   note if any race condition surfaces.

## What wasn't obvious during merge (Main Branch notes)

- **WORKLOG.md conflict** during Orch's rebase onto post-Loc main
  was resolved surgically with "incoming-on-top" (Orch entry above
  Loc entry). Post-rebase gate confirmed clean (776 + 5).

- **Source-file count check passed for BOTH cycle slices** — neither
  D5 nor D6 added new src files; count stays at 72. mypy `--strict`
  clean.

- **Orch's INDEX.md was included in the rebased commit** — Orch
  regenerated INDEX before commit (worktree had the regen step), so
  the rebase included a single-line INDEX update. Main Branch will
  regen INDEX once more before the verification commits to fold in
  the new verification docs + any additional state changes.

- **Live demonstration of the fix in cycle context**: my Defect 5
  CLI smoke (`novetest localization latest` against `/tmp/d56-cargo`)
  generated a `localization_findings.json` file on disk; then
  `novetest status` correctly reported `sub_reports.localization:
  "available"` — Defects 5 and 6 work together as expected. The
  cycle's empirical evidence shows the two slices compose cleanly.

- **`coverage_outcome.summary.percent_covered == 85.71`** captured
  from the cargo aggregate fixture's actual `cargo-llvm-cov` run on
  equipped host. This matches Manual Test's prior cycle observation
  AND Orch team's seeded value in their integration test.

## End-of-work

- Commit hash for the merged Orch Defect 6 fix: **`0895e59`**.
- Source handoff: `agent-comms/handoffs/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md`.
- Source task: `agent-comms/tasks/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md`.
- Sibling slice in the same cycle: Defect 5 — see
  `agent-comms/verifications/2026-06-01-localization-cache-rederive-defect5.md`.
