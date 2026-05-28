---
from: novetest-main-branch-team
to: novetest-pm-team
type: verification
status: record-only
created: 2026-05-28
slug: localization-engine-completion
related:
  - agent-comms/tasks/localization-team-2026-05-28-engine-completion.md
  - agent-comms/handoffs/localization-team-2026-05-28-engine-completion.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape.md
  - agent-comms/history/2026-05-27-phase3-regression-engine-complete.md
  - design/interace-contract/localization.md
---

# Record: Localization engine surface completion (Phase 4 engine close-out)

## Verification model

**`status: record-only` — no Manual Test action requested.**

Engine-only slice, no CLI / orchestration / envelope changes. Mirrors
the precedent set by:
- `verifications/2026-05-26-phase3-regression-engine-and-memory-probe.md`
- `verifications/2026-05-27-phase3-regression-engine-complete.md`

The task brief (§"Verification model") explicitly waived Manual Test
and the handoff (top section) explicitly requested record-only — the
user-facing surface lands in the upcoming Orchestration CLI cycle.

## Merged commits

- `8ec124a localization: close engine surface — to_dict + latest-resolution helpers + reason split`
- Merged into `main` via fast-forward from `novetest-localization-engine-completion`.
- Base before merge: `0c76a21`; new HEAD: `8ec124a`.

## Source handoff consumed

- `agent-comms/handoffs/localization-team-2026-05-28-engine-completion.md`

## Test gate (re-run on the merged commit by Main Branch)

- `uv run pytest -q tests/unit tests/integration` → **611 passed + 5 skipped**
  (baseline `0c76a21`: 586+5 → +25 net new tests, exactly matching the
  handoff's claim).
- `uv run mypy` → **clean**, **69 source files**, `--strict` (no new
  src files added; helpers extended existing modules per the brief).

The 5 vs 3 skipped delta from the prior cycle's Manual Test count (588+3
in the task brief, drawn from commit `1d12ee5`) is a deterministic
environment difference noted by the team in the handoff — 2 extra
environment-conditional skips on this dev box. The `+25` net delta is
independently verified.

## What landed — engine surface 100% covered

`design/interace-contract/localization.md`'s **Internal interface table
is now 100% implemented** (all 5 rows). The 2 External rows
(`novetest localization <run_id>` / `novetest localization latest`)
are CLI projection — Orchestration team's next cycle.

### Pinned (grepped from merged source) — 4 items per brief

**Item 1 — Reason split** — `src/novetest/localization/results.py`:

```python
REASON_NO_FAILED_TESTS:        Final[str] = "no_failed_tests"        # line 55
REASON_NO_COVERAGE:            Final[str] = "no_coverage"            # line 56
REASON_NO_RUN_EVIDENCE:        Final[str] = "no_run_evidence"        # line 57
REASON_MISSING_DERIVED_FACTS:  Final[str] = "missing_derived_facts"  # line 58  ← NEW
REASON_RUN_NOT_ANALYZABLE:     Final[str] = "run_not_analyzable"     # line 59  ← NARROWED

KNOWN_REASONS: frozenset[str] = frozenset({...all 5...})            # line 61
```

Routing audit (confirmed via grep):
- `retrieval.py:57` (cache-empty branch in `get_localization_findings`)
  → `REASON_MISSING_DERIVED_FACTS` ✓
- `derive.py:136` (tombstoned input in `derive_localization_findings`)
  → `REASON_RUN_NOT_ANALYZABLE` ✓ (retained-narrower)
- `derive.py:657` (all-non-analyzable in `resolve_latest_analyzable_run`)
  → `REASON_RUN_NOT_ANALYZABLE` ✓

Underscore-form convention preserved (vs Regression's hyphenated form);
the hyphenated literal `"missing-derived-facts"` is REJECTED by
`__post_init__`'s `KNOWN_REASONS` guard.

**Item 2 — `LocalizationUnavailable.to_dict()`** —
`src/novetest/localization/results.py:96-112`. Three keys, always
present (null-not-absent for None values), JSON-stable. Matches
`RegressionUnavailable.to_dict()` shape per freeze §6 known-gap.

```
out.run_reference  # null | RunReference.to_dict()
out.reason         # one of the 5 KNOWN_REASONS
out.detail         # null | string
```

**Item 3 — `resolve_latest_analyzable_run`** —
`src/novetest/localization/derive.py:610-659`.

```python
def resolve_latest_analyzable_run(
    store: ProjectStore,
) -> RunReference | LocalizationUnavailable: ...
```

Walks `list_run_history(store)` newest-first; first run for which
`check_localization_availability` returns `True` wins. Empty store →
`REASON_NO_RUN_EVIDENCE` `detail="no runs in store"`. All
non-analyzable → `REASON_RUN_NOT_ANALYZABLE`
`detail="no analyzable runs in store (N candidates checked)"` where
N is the actual probe count. Pure read; never derives.

**Item 4 — `derive_latest_localization`** —
`src/novetest/localization/derive.py:662-686`.

```python
def derive_latest_localization(
    store: ProjectStore,
    *,
    formula: str = DEFAULT_FORMULA,  # "ochiai"
    top_n: int = DEFAULT_TOP_N,       # 10
) -> LocalizationFinding | LocalizationUnavailable: ...
```

Pure composition: `resolve_latest_analyzable_run` →
`derive_localization_findings(store, ref, top_n=top_n, formula=formula)`.
Unavailable propagated unchanged.

### Re-exports — `src/novetest/localization/__init__.py`

`__all__` now exports `REASON_MISSING_DERIVED_FACTS`,
`resolve_latest_analyzable_run`, `derive_latest_localization` alongside
the existing surface (grep-verified).

## File-by-file diff (merged commit `8ec124a`)

| File | Change |
|---|---|
| `src/novetest/localization/results.py` | +50/−10 — Item 1 + Item 2 |
| `src/novetest/localization/retrieval.py` | +10/−10 — Item 1 routing |
| `src/novetest/localization/derive.py` | +95 — Items 3 + 4 + imports |
| `src/novetest/localization/__init__.py` | +15/−5 — re-exports + docstring |
| `tests/unit/localization/test_results.py` | +3 cases |
| `tests/unit/localization/test_retrieval.py` | 1 updated, 0 net |
| `tests/unit/localization/test_unavailable_to_dict.py` | NEW, 11 cases |
| `tests/unit/localization/test_latest_resolution.py` | NEW, 9 cases |
| `tests/integration/localization/test_latest_resolution_e2e.py` | NEW, 2 cases |

**Net: +25 tests.**

## DoD bullets believed closed

**NONE** — per the brief's explicit instruction. All Phase 4 §4 bullets
require the CLI verb cycle. PM ticks none from this slice.

## Pinned notes for PM's v2 supersede of `2026-05-28-localization-finding-shape.md`

The handoff's "Pinned working-draft details" section is the source-of-
truth; quoting the load-bearing items here for PM's convenience:

1. **`KNOWN_REASONS` (5 elements, underscore-form):**
   `no_failed_tests`, `no_coverage`, `no_run_evidence`,
   `missing_derived_facts`, `run_not_analyzable`. Hyphenated form
   explicitly rejected.

2. **`LocalizationUnavailable.to_dict()` shape:** 3 keys in the order
   `run_reference`, `reason`, `detail`. All always present. JSON-stable.

3. **`resolve_latest_analyzable_run` Unavailable shape:** when no
   analyzable run exists, `run_reference=None` (per-store query, not
   per-run). The detail-count `N` includes tombstoned candidates
   encountered during the walk (because `list_run_history` returns
   both live + tombstoned and `check_localization_availability` is
   what filters); PM may want to clarify in v2 whether N should count
   only live runs — see handoff §Deviations note #2.

4. **`derive_latest_localization` kwargs order:** declared as
   `(store, *, formula, top_n)` to match the brief's draft signature.
   `derive_localization_findings` declares `(store, run_reference, top_n, *, formula)`.
   Both keyword-only post-`*`, so functionally equivalent; PM may want
   to reconcile to one canonical order in v2 — see handoff §Deviations
   note #1. The CLI cycle exposes both through `--formula` / `--top-n`
   flags so the kwargs order is purely an internal surface concern.

## Conflict-resolution notes during merge

None. The merge was a clean fast-forward — base commit `0c76a21`
matched main's tip exactly; no conflicts to resolve.

## Push status

Awaiting CEO authorization. Per Main Branch charter, never push without
explicit per-push approval.
