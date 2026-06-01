---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-06-01
slug: status-sub-reports-staleness-defect6
related:
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
  - src/novetest/orchestration/workflows/status.py
  - src/novetest/orchestration/workflows/inspect.py
---

# Task: Orchestration — `status.sub_reports.*` reflects on-disk derived facts (Defect 6)

## TL;DR

`novetest status` envelope's `data.sub_reports` dict reports
`"unavailable"` for engines (coverage / localization / etc.) whose
on-disk facts ARE present AND whose dispatch verbs (`inspect`,
`localization latest`, etc.) work correctly. AI agents consuming
`status` as the "is X available?" gate will incorrectly skip
downstream invocations of those engines.

Manual Test reproduced + root-cause-hypothesized:
- `status.sub_reports.localization == "unavailable"` despite
  `inspect.localization_outcome.kind == "fact-set"` AND on-disk
  `localization_findings.json` valid.
- Same symptom for coverage.
- Likely root cause: `status` workflow uses a pre-Defect-4
  precondition probe (e.g., the `mapping_granularity == "per-test"`
  semantics that was relaxed in `retrieval.py` for `latest` resolver
  but NOT in `status` reporting).

**Symmetric fix to Defect 4** likely applies here, in a different
file. ~10-line src change + tests.

**Sub-observation bundled**: `inspect.coverage_outcome.percent_covered`
returns `None` while on-disk `coverage_facts.json.summary.percent_covered`
is `85.71`. Looks like `inspect` reads the wrong nested path
(top-level vs `summary.*`). Bundle into this slice's triage; either
fix or split into Defect 6b at implementer's discretion.

## Why this slice exists (product framing)

`novetest status` is the **canonical "what's available?" gate**. AI
agents pipeline decisions on it:
```python
status_envelope = subprocess_capture("novetest status")
if status_envelope["data"]["sub_reports"]["localization"] == "available":
    derive_localization_finding(...)
else:
    skip()  # ← currently fires even when localization works
```

`status` lying about availability:
- Causes AI agents to skip working functionality
- Causes humans to second-guess working surfaces (since `inspect`
  and direct verbs return real data)
- Undermines the `status` verb's product contract

Fixing this restores the contract: `status.sub_reports.X` is the
truth about whether engine X has data for the latest run.

## Empirical reproduction (verbatim from Manual Test 2026-06-01 findings)

```sh
# Reuses Scenario A's /tmp/d4-cargo state from Defect 4 findings
cd /tmp/d4-cargo  # cargo aggregate run already cached

novetest status 2>&1 | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['sub_reports'])"
# {'coverage': 'unavailable', 'localization': 'unavailable', 'regression': 'unavailable', 'replay': 'unavailable'}

RUN_ID=$(novetest status 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['latest_run_reference']['run_id'])")

novetest inspect "$RUN_ID" 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('loc:', d['data']['localization_outcome']['kind'])"
# loc: fact-set                ← CONTRADICTS status.sub_reports.localization

novetest inspect "$RUN_ID" 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('cov:', d['data']['coverage_outcome']['kind'])"
# cov: fact-set                ← CONTRADICTS status.sub_reports.coverage

ls .novetest/localization/findings/run_$RUN_ID/localization_findings.json
# exists, 1930 bytes, valid

ls .novetest/coverage/facts/run_$RUN_ID/coverage_facts.json
# exists, valid, summary.percent_covered: 85.71
```

Three sources of truth (`status`, `inspect`, on-disk file) MUST agree
on availability. Currently `status` is the outlier.

## Manual Test's hypothesis (verify during implementation)

The `status` workflow's `sub_reports` evaluation likely uses one of:
- A `check_*_availability` function that hasn't been relaxed
  symmetrically to Defect 4
- A direct `mapping_granularity == "per-test"` check (or similar
  over-restrictive precondition)
- A cached state that's not invalidated when new facts persist

`inspect` works correctly — it reads `get_localization_findings` /
`get_coverage_facts` (the actual fact-retrieval functions) which do
match on-disk state. **The fix is likely to align `status`'s probe
with `inspect`'s data-retrieval path** — either by calling the same
underlying retrieval functions and checking for non-`Unavailable`
returns, OR by relaxing whatever precondition check `status` uses.

## Sub-observation — `inspect.coverage_outcome.percent_covered: None`

From Manual Test findings §Scenario H sub-observation:

```
$ novetest inspect $RUN_ID 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['coverage_outcome'].get('summary'))"
# {... 'percent_covered': 85.71, ...}    ← inside .summary

$ novetest inspect $RUN_ID 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['coverage_outcome'].get('percent_covered'))"
# None                                     ← top-level None
```

`inspect` envelope's `coverage_outcome` block has `summary.percent_covered`
correctly populated, but a separate top-level `percent_covered` field
(if any) is `None`. Either:
- The top-level field is intentional (e.g., a legacy field) and
  should be removed
- It's a code path that reads the wrong nested location and should
  be fixed to read `summary.percent_covered`

Implementer investigates + chooses fix path; document in handoff.

## Scope (what this slice DOES)

### 1. Find the `status` workflow's `sub_reports` evaluation

Likely in `src/novetest/orchestration/workflows/status.py` (or a
helper module). Trace:
1. Where `sub_reports` dict is constructed
2. What precondition each engine's `"available"` / `"unavailable"`
   decision uses
3. Why those preconditions disagree with `inspect`'s data-retrieval
   path

### 2. Align with `inspect`'s data path

Likely fix shape (TBD by team after investigation):

```python
# OLD (hypothetical — actual may differ):
if check_localization_availability(store, run_ref):
    sub_reports["localization"] = "available"
else:
    sub_reports["localization"] = "unavailable"

# NEW:
loc_facts = get_localization_findings(store, run_ref)
if not isinstance(loc_facts, LocalizationUnavailable):
    sub_reports["localization"] = "available"
else:
    sub_reports["localization"] = "unavailable"
```

Same pattern for coverage, regression, replay (any sub-report that
shows the same disconnect).

If the actual root cause differs (e.g., it's NOT a precondition
check but a stale-cache issue), document the actual fix in the
handoff.

### 3. Fix `inspect.coverage_outcome.percent_covered: None` sub-observation

Either:
- Remove the top-level `percent_covered` field if it's vestigial
- Fix the code that populates it to read `summary.percent_covered`

Document choice in handoff.

### 4. Tests

- **Unit**: in `tests/unit/orchestration/workflows/test_status.py`
  (or equivalent), add tests pinning:
  1. Run with persisted coverage facts → `sub_reports.coverage:
     "available"` (regression-pin if it works for per-test today;
     NEW assertion for aggregate cargo run)
  2. Run with persisted localization findings →
     `sub_reports.localization: "available"`
  3. Run with NO persisted facts → `sub_reports.*: "unavailable"`
     (regression-pin)
- **Integration**: extend `tests/integration/cli/` with ONE case
  cross-checking `status` ↔ `inspect` ↔ direct verb consistency for
  cargo aggregate run (mirrors Manual Test's Scenario H).
- For the sub-observation: add a regression test pinning
  `inspect.coverage_outcome.percent_covered` matches
  `summary.percent_covered`.

## Out of scope (do NOT touch)

- **`retrieval.py`** (Defect 4 fix) — already correct.
- **Defect 5** (cache flag invalidation) — sibling slice, separate
  Localization team territory.
- **Phase 4 §4 #3 perf NFR** — separate slice.
- **The actual `_derive_*` dispatchers** — only the `status`
  workflow's view of them.

## Pre-flight checks

1. **Full gate green** on equipped host:
   `uv run pytest -q tests/unit tests/integration`
   - Baseline tip (`97285e5` + Defect 4 fix `4b5fd1d`): **762 + 5**
     on equipped host.
   - Your tip = baseline + new tests. No regressions.
2. **mypy strict clean**: 72 source files (this slice may add a
   small helper but no major modules; expect ≤73).
3. **Empirical smoke** — reproduce Defect 6 pre-fix, then confirm
   post-fix:
   ```sh
   # Pre-fix: status sub_reports lies (cargo aggregate run)
   # Post-fix: status agrees with inspect + on-disk for the same run
   ```

## DoD

- [ ] `status.sub_reports.*` reflects on-disk derived facts for
      coverage + localization + regression + replay.
- [ ] Cross-check consistency: `status` ↔ `inspect` ↔ direct
      verb agreement for all 4 sub-engines on a cargo aggregate run.
- [ ] Sub-observation addressed: `inspect.coverage_outcome.percent_covered`
      matches `summary.percent_covered` (or vestigial field removed).
- [ ] Unit + integration tests per §4.
- [ ] Full pytest suite green; mypy strict clean.
- [ ] No `delivery-phasing.md` checkbox movement (bug fix).

## Handoff format

Standard at
`agent-comms/handoffs/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md`.
MUST include:

1. DoD bullets believed closed.
2. **Root cause documented** — what was the actual gap (precondition
   check, stale cache, missing call, etc.)?
3. Pre-flight empirical evidence: pre-fix `status` envelope vs
   post-fix, verbatim.
4. Sub-observation disposition (fixed / removed / explained-as-intended).
5. Open questions for PM.

## Cross-references

- **Origin of Defect 6 + reproduction**:
  `agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md`
  §"Defect 6 surfaced".
- **Symmetric prior fix (Defect 4)**:
  `agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md`
  §"What shipped" — Manual Test hypothesizes the same precondition
  gap applies to `status`.
- **Sibling Defect 5 slice (independent, parallel-dispatchable)**:
  `agent-comms/tasks/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md`.
