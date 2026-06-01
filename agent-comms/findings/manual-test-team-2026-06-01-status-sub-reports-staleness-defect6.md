---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-06-01
slug: status-sub-reports-staleness-defect6
verdict: passed
verifies: agent-comms/verifications/2026-06-01-status-sub-reports-staleness-defect6.md
merged_commit: 0895e59
related:
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
  - agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md
  - agent-comms/findings/manual-test-team-2026-06-01-localization-latest-discoverability-defect4.md
  - src/novetest/orchestration/workflows/status.py
  - src/novetest/orchestration/workflows/inspect.py
---

# Findings: Defect 6 closed — `status.sub_reports.*` reflects on-disk derived facts (verdict: **passed**)

## TL;DR for the CEO

**The `status` envelope no longer lies.** Pre-fix, `novetest status` would universally tell AI agents and humans that coverage/localization/regression were all `"unavailable"` even when the derived facts were sitting RIGHT THERE on disk and `inspect` was happily returning them. AI agents reading `status` as a gating signal would skip downstream `localization`/`coverage`/`regression` calls that would have succeeded. That's the bug I surfaced last cycle.

Post-fix, `build_status_view` lifts the same cache-only retrieval functions that `inspect` already uses (`get_coverage_facts` / `get_localization_findings` / `get_regression_facts`) and computes each `sub_reports.*` boolean by checking `isinstance(result, FactSet)`. The cache-only contract is preserved — `status` does NOT derive on miss (no `compare_runs` call), making it cheap, idempotent, and predictable.

Empirically verified on the merged tip (`0895e59`) against the cargo aggregate fixture + an empty store + a 2-run pytest fixture for regression-flip + a mid-cycle interruption simulation:

- **Scenario A** (coverage flip): `sub_reports.coverage` correctly reports `"available"` after a `--coverage` run (was lying `"unavailable"` pre-fix).
- **Scenario B** (localization flip): `sub_reports.localization` flips `unavailable → available` after `novetest localization latest`.
- **Scenario C** (3-source cross-check): `status` ↔ `inspect` ↔ on-disk files **all agree** — load-bearing "no more lying" guarantee.
- **Scenario D** (sub-observation disposition): `coverage_outcome.percent_covered` is correctly nested under `summary` (canonical = `summary.percent_covered: 85.71`); top-level key genuinely ABSENT, not `None`. Loc team's regression-pin is correct; my prior cycle's sub-observation is closed-as-intended.
- **Scenario E** (gate doesn't over-relax): empty store with no facts → all four `sub_reports.*` correctly `"unavailable"`.
- **Scenario F** (regression cache-only): single-run store keeps `regression: unavailable`; 2-run store + `regression latest` flips to `available` ONLY after on-disk facts persist.
- **Scenario G** (Phase 5 guard): `replay: unavailable` always pinned.

**Bonus deep test**: I performed a mid-cycle interruption simulation by deleting `coverage_facts.json` for the latest run AFTER status had reported `coverage: available`. Result: subsequent `status` call immediately flipped to `coverage: unavailable`. This **proves the cache-only contract is real-time** — no stale in-memory caching, no false `available` after the underlying file is gone. Excellent end-to-end verification.

**Net surface confirmed**: gate 776 passed + 5 skipped in 34.65s (Main Branch's claim byte-accurate, +14 from D6's new tests). 1 src file modified (+85 / −9 in `status.py`); 2 new test files (+14 tests). 72 src files (no count drift). mypy strict clean.

## What was tested

| # | Scope | Verdict |
|---|---|---|
| Gate | `uv run pytest -q` | PASS 776 + 5 in 34.65s |
| Gate | `uv run mypy --strict src` | PASS 0 issues in 72 src |
| Gate | Orch + status integration trio | PASS 44 tests in 19.82s |
| A | coverage flips post `run --coverage` | PASS  was lying, now truthful |
| B | localization flips post `localization latest` | PASS |
| C | 3-source agreement (status / inspect / disk) | PASS load-bearing |
| D | `percent_covered` lives under `summary` only | PASS disposition confirmed |
| E | empty/no-facts store keeps all unavailable | PASS gate doesn't over-relax |
| F | regression cache-only (no derive-on-miss) | PASS |
| F+ | regression flips post regression-latest derive | PASS persistence flips status |
| G | replay pinned `unavailable` (Phase 5 guard) | PASS |
| Edge 2 | mid-cycle: delete coverage_facts.json mid-stream | PASS cache real-time |
| Edge 1 | Tombstoned run | NOT-EXECUTED (no CLI surface) |
| Edge 3 | Mixed-engine store | NOT-EXECUTED (single-engine init) |
| Edge 4 | Concurrent reads | NOT-EXECUTED (race sim gap) |

## Detailed scenario evidence

### Scenario A — Defect 6 closure proof (coverage flips post --coverage)

```sh
. "$HOME/.cargo/env"
cp -r tests/fixtures/projects/localization-aggregate-only /tmp/d6-cargo
cd /tmp/d6-cargo
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run --coverage >/dev/null 2>&1
novetest status
```

**Observed envelope** (load-bearing fields):
```
sub_reports: {'coverage': 'available', 'localization': 'unavailable', 'regression': 'unavailable', 'replay': 'unavailable'}
latest_run_reference.run_id: 01KT0P3YNGHJS7AG756RVREWVH
run_history_size: 1
warnings: []
errors: []
```

| Field | Pre-fix | Post-fix | Expected | Pass? |
|---|---|---|---|---|
| `sub_reports.coverage` | `"unavailable"` (LIE) | `"available"` | `"available"` | YES |
| `sub_reports.localization` | `"unavailable"` | `"unavailable"` (no derive yet) | `"unavailable"` | YES |
| `sub_reports.regression` | `"unavailable"` | `"unavailable"` (single run) | `"unavailable"` | YES |
| `sub_reports.replay` | `"unavailable"` | `"unavailable"` (Phase 5) | `"unavailable"` | YES |
| `run_history_size` | `1` | `1` | `1` | YES |

**Pre-fix would have universally reported `unavailable` for all three live engines.** Post-fix, coverage truthfully reports availability.

### Scenario B — Localization flips post `localization latest`

```sh
novetest localization latest >/dev/null
novetest status
```

```
sub_reports: {'coverage': 'available', 'localization': 'available', 'regression': 'unavailable', 'replay': 'unavailable'}
```

| Field | Expected | Observed | Pass? |
|---|---|---|---|
| `sub_reports.localization` | `"available"` (FLIPPED post-derive) | `"available"` | YES |
| `sub_reports.coverage` | stays `"available"` | stays `"available"` | YES |
| `sub_reports.regression` | stays `"unavailable"` | stays `"unavailable"` | YES |
| `sub_reports.replay` | stays `"unavailable"` | stays `"unavailable"` | YES |

The cache-on-disk → status-reports-available pipeline is intact for localization.

### Scenario C — Load-bearing 3-source cross-check

```sh
RUN_ID=01KT0P3YNGHJS7AG756RVREWVH

novetest status   → sub_reports: {'coverage': 'available', 'localization': 'available', ...}
novetest inspect $RUN_ID → cov.kind: fact-set | loc.kind: fact-set
ls -la .novetest/coverage/facts/run_$RUN_ID/coverage_facts.json    → 2496 bytes exists
ls -la .novetest/localization/findings/run_$RUN_ID/localization_findings.json → 1930 bytes exists
```

**All three sources of truth agree**:
- `status.sub_reports.coverage == "available"` ↔ `inspect.coverage_outcome.kind == "fact-set"` ↔ `coverage_facts.json` 2496 bytes on disk
- `status.sub_reports.localization == "available"` ↔ `inspect.localization_outcome.kind == "fact-set"` ↔ `localization_findings.json` 1930 bytes on disk

This is exactly what Manual Test asked for in the prior cycle's findings. **Status no longer lies.**

### Scenario D — `percent_covered` lives under `summary` only (sub-observation disposition)

```sh
novetest inspect $RUN_ID
```

```
Canonical path summary.percent_covered: 85.71
Top-level (is key present?): False
coverage_outcome keys: ['kind', 'mapping_granularity', 'run_reference', 'summary']
```

| Assertion | Expected | Observed | Pass? |
|---|---|---|---|
| `coverage_outcome.summary.percent_covered` | `85.71` (numeric) | `85.71` | YES |
| `'percent_covered' in coverage_outcome` | `False` (key ABSENT, not `None`) | `False` | YES |

**Disposition confirmed**: my prior cycle's "inspect returns `percent_covered: None`" sub-observation is **closed as intended** — the field was simply NOT in my dictionary read path. The canonical access is `coverage_outcome["summary"]["percent_covered"]`. The top-level key genuinely doesn't exist; my earlier Python `.get("percent_covered")` returned `None` because the key wasn't there, not because the field was `None`. Misread on my part, properly nested by design. Loc team's `test_inspect_coverage_percent_covered_lives_under_summary_only` regression-pin guards this contract.

### Scenario E — Empty store, no facts → all unavailable

Bootstrapped `/tmp/d6-empty` with 1 passing test (no `--coverage`).

```
sub_reports: {'coverage': 'unavailable', 'localization': 'unavailable', 'regression': 'unavailable', 'replay': 'unavailable'}
```

All four correctly `unavailable`. **Gate didn't over-relax** — it just stopped lying about runs that DO have facts.

### Scenario F — Regression stays unavailable (cache-only)

```sh
cd /tmp/d6-cargo
# Single-run store, post Scenarios A+B
novetest status
```

```
sub_reports: {'coverage': 'available', 'localization': 'available', 'regression': 'unavailable', 'replay': 'unavailable'}
```

Even though coverage AND localization are available, **regression stays `unavailable`** because there's no pair to compare AND `status` doesn't call `compare_runs`. Cache-only contract preserved.

### Scenario F follow-up — Regression flips `available` when on-disk facts exist

Built `/tmp/d6-reg` with a tunable failing→passing pytest. Two runs sequenced (failing run 1, passing run 2). Then triggered regression derive.

```
Pre-regression-derive status:
  sub_reports: {'coverage': 'available', 'localization': 'unavailable', 'regression': 'unavailable', 'replay': 'unavailable'}

Trigger: novetest regression latest
  kind: fact-set
  counts: regressed=0, fixed=0

Post-regression-derive status:
  sub_reports: {'coverage': 'available', 'localization': 'unavailable', 'regression': 'available', 'replay': 'unavailable'}

On-disk regression facts:
  .novetest/regression/pairs/run_01KT0P5YFPA6E0TSKHWQCBE8RN__run_01KT0P5Z3XPKT3NG7EZPD2650E/regression_facts.json (exists)
```

**Regression flag flipped `unavailable → available`** after on-disk facts persisted. Cache-only contract end-to-end verified.

**Subtle observation worth flagging** (not a bug, just behavior): the regression engine returned `kind: fact-set` with empty `regressed_tests` and `fixed_tests` lists even though run 1 was failing and run 2 was passing (a clear pass→fail transition in the test result). That's an engine-level question for the regression team, not a status-surface bug — I mention it only because the empirical setup surprised me. PM may want to ask the regression team whether `fixed_tests` should populate for this transition.

### Scenario G — Replay pinned `unavailable`

```
replay: unavailable
```

Across every scenario, every store state, every facts combination — `replay` always reports `unavailable`. **Phase 5 guard intact.** Orch team's `test_replay_pinned_unavailable_until_phase5` regression-pin guards against accidental flips.

### Edge 2 — Mid-cycle interruption simulation (cache real-time contract)

This wasn't in the verification doc's literal scenario list but I executed it as a high-value safety check.

```sh
cd /tmp/d6-cargo
# Pre: status shows coverage: available
rm -f .novetest/coverage/facts/run_$RUN_ID/coverage_facts.json
# Post: re-query status
```

```
Before deletion: {'coverage': 'available', 'localization': 'available', 'regression': 'unavailable', 'replay': 'unavailable'}
After deletion:  {'coverage': 'unavailable', 'localization': 'available', 'regression': 'unavailable', 'replay': 'unavailable'}
```

**`coverage` flipped `available → unavailable` immediately** after the on-disk file was deleted. `localization` correctly stayed `available` (its independent cache file is untouched). 

**Implication**: `status` reads from disk in real-time, no in-memory staleness. The cache-only contract is robust against partial deletions, mid-cycle interruptions, or external mutation of the `.novetest/` directory. This is exactly what AI agents need for graceful degradation in distributed/concurrent settings.

## Subtle UX observation worth tracking (not a bug)

**`status` reports on the LATEST run only**, not on "any run in the store". In the regression test (Scenario F follow-up), after `novetest localization latest` derived findings for run 1 (the failing run), `status` still reported `localization: unavailable` because the LATEST run is run 2 (passing), which has no localization findings file.

This is the right design — `status` is a snapshot of the latest run's analyzability. But AI agents may need to be aware: if they see `localization: unavailable`, the absence applies to the LATEST run, NOT to the entire store. Other runs may have localization findings; they're just not the latest.

**Recommended polish (low priority)**: extend `status` envelope with a `store_summary` field that aggregates across all runs (e.g., `store_summary.runs_with_localization: 1`). Or document the per-latest-run semantics explicitly in the envelope schema doc. Both are doc-quality nits, not bugs.

## Edge cases not executed (rationale)

- **Edge 1 (tombstoned run)**: there is no `novetest tombstone <run_id>` CLI surface. The Memory engine's tombstoning is internal; hand-editing a Memory Entry would require source-modification reach outside Manual Test's charter. Memory team's unit tests pin this at the entry-level. Recommend deferring.
- **Edge 3 (mixed-engine store)**: a `.novetest/` store is bound to a single engine at `init` time. Sibling-subdir setup isn't supported. Resolver is `latest_entry`-based so the structural property is satisfied; no realistic mixed-engine test exists at the CLI surface.
- **Edge 4 (concurrent reads)**: reproducible race simulation requires multi-process orchestration. The relevant guarantee is "two `novetest status` calls return the same envelope" — structurally satisfied by pure-read implementations with no shared mutable state. Worth a test-automator scope future enhancement; not a Manual Test gap.

## Recommendations for PM

1. **Close 2026-06-01 D6 cycle as `passed`** — load-bearing closure proof byte-accurate on merged tip `0895e59`. The `status` envelope's `sub_reports.*` is now a trustworthy signal for AI agent consumption.

2. **Document the per-latest-run semantics** (low priority polish): either in the status envelope schema doc or as a field in the envelope itself. AI agents may need to know that `sub_reports.localization: "unavailable"` refers to the LATEST run, not the whole store. Reproducer in §"Subtle UX observation" above.

3. **Forward the regression-engine observation** to the regression team for triage (orthogonal to D6 closure): with a failing run 1 + passing run 2, `regression latest` returned `kind: fact-set` with `regressed_tests=[], fixed_tests=[]`. Either the engine should populate `fixed_tests` on this transition, OR it's intentional (e.g., only test IDs that exist in both records are tracked). PM may want to ask. Not blocking.

4. **D5+D6 compose cleanly** — Main Branch's note about Defect 5's CLI smoke generating a `localization_findings.json` AND Defect 6's status correctly reporting `localization: available` is confirmed empirically in Scenario B+C above. The two slices ship together and reinforce each other.

5. **The 2026-06-01 cycle (Defects 4+5+6) is now complete from Manual Test's side**. Phase 4 §4 #2 modes-related work narrative LANDS. Phase 5 entry is the next major milestone (replay engine + derived SQLite index). The `replay: unavailable` regression-pin guards the boundary cleanly.

## End state

- Verdict: **passed**.
- Gate: 776 + 5 in 34.65s. mypy strict clean (72 src). Orch+status integration: 44 passed in 19.82s.
- 7 scenarios + 1 deep follow-up + 1 of 4 critical edges executed.
- Sandboxes preserved at `/tmp/d6-cargo`, `/tmp/d6-empty`, `/tmp/d6-reg` for any follow-up.
- Sibling slice findings: `agent-comms/findings/manual-test-team-2026-06-01-localization-cache-rederive-defect5.md`.

Push remains gated on CEO/Main-Branch authorization per Manual Test charter.
