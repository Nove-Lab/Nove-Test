---
from: novetest-localization-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-28
slug: engine-completion
related:
  - agent-comms/tasks/localization-team-2026-05-28-engine-completion.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape.md
  - agent-comms/history/2026-05-27-phase3-regression-engine-complete.md
---

# Handoff: Localization engine surface completion (Phase 4 engine close-out)

Engine-only slice — **no CLI / orchestration / envelope changes**.
Implements the 4 items in the task brief 1:1: split
`run_not_analyzable`, add `LocalizationUnavailable.to_dict()`, add
`resolve_latest_analyzable_run`, add `derive_latest_localization`.

**No Manual Test action requested — engine-only slice, no user-facing
surface.** Per the precedent in
`history/2026-05-26-phase3-regression-engine-and-memory-probe.md` +
`history/2026-05-27-phase3-regression-engine-complete.md`, Main Branch
should write a `status: record-only` verification and waive Manual Test.

## Worktree

- Path: `/home/yjshin/dev/novetest-localization-engine-completion`
- Branch: `novetest-localization-engine-completion`
- Base commit: `0c76a21` (current `origin/main` at slice start)

## File-by-file diff summary

**4 src files modified, 0 src files added** (items 3 + 4 extended
`derive.py` per the brief; no new src files needed).

| File | Lines | Change |
|---|---|---|
| `src/novetest/localization/results.py` | +~50 / −~10 | Item 1: `REASON_MISSING_DERIVED_FACTS` added, `KNOWN_REASONS` extended to 5 elements, docstring rewritten to describe the split. Item 2: `to_dict()` method added (3 keys, all always present). |
| `src/novetest/localization/retrieval.py` | +~10 / −~10 | Item 1: `get_localization_findings` cache-empty branch switched from `REASON_RUN_NOT_ANALYZABLE` to `REASON_MISSING_DERIVED_FACTS`; docstring updated. |
| `src/novetest/localization/derive.py` | +~95 | Items 3 + 4: `resolve_latest_analyzable_run` + `derive_latest_localization` appended; `__all__` extended. Two new imports: `check_localization_availability` from `retrieval`, `list_run_history` from `memory.store`. **Item 1 audit:** the only `REASON_RUN_NOT_ANALYZABLE` call site (the tombstoned-input branch) stays — that's the retained-narrower semantic. The cache-read branch in `derive.py` calls `read_localization_findings_raw` directly (not `get_localization_findings`), so it never surfaces an unavailable on a cache hit. |
| `src/novetest/localization/__init__.py` | +~15 / −~5 | Re-export `REASON_MISSING_DERIVED_FACTS`, `resolve_latest_analyzable_run`, `derive_latest_localization`. Docstring rewritten: latest-resolution helpers are now IN-scope; the "wire shape is working draft" caveat removed (decision pinned the shape 2026-05-28). |

**3 test files added, 2 test files updated** (no production code in tests dir).

| File | Tests | Change |
|---|---|---|
| `tests/unit/localization/test_results.py` | 5 → 8 (+3) | Added `test_known_reasons_has_exactly_five_elements`, `test_unavailable_constructable_with_missing_derived_facts`, `test_unavailable_hyphenated_missing_derived_facts_is_rejected`. Existing closure + pinned-string-values tests expanded to include the new reason. |
| `tests/unit/localization/test_retrieval.py` | 8 → 8 (0 net; 1 updated) | `test_get_cache_absent_returns_unavailable` switched assertion from `REASON_RUN_NOT_ANALYZABLE` → `REASON_MISSING_DERIVED_FACTS` and gained a `run_reference` populated assertion. |
| `tests/unit/localization/test_unavailable_to_dict.py` | 0 → 11 (+11) | NEW. Item 2: 3-key shape, parametrized over all 5 `KNOWN_REASONS`, `run_reference` round-trip via `RunReference.to_dict()`, `run_reference=None` → null-not-absent, `detail=None` → null-not-absent, JSON-serializable sanity. |
| `tests/unit/localization/test_latest_resolution.py` | 0 → 9 (+9) | NEW. Items 3 + 4: empty-store → `no_run_evidence`, all-non-analyzable → `run_not_analyzable` with N count, latest analyzable returned, tombstoned-latest skipped, resolver-does-not-derive (monkeypatch spy + no findings file written), happy-path derive, empty-store derive, all-non-analyzable derive, forward-args propagation (`formula="op2"`, `top_n=5`). |
| `tests/integration/localization/test_latest_resolution_e2e.py` | 0 → 2 (+2) | NEW. Real Project Store + 3-run setup (passing-only + failing-no-coverage + failing-with-coverage) → resolver returns the failing-with-coverage one. End-to-end derive_latest writes the canonical `localization_findings.json` and Memory's `has_localization_findings` flag flips on `retrieve_run_evidence` refresh. |

**Total tests added: +25 net** (3 + 0 + 11 + 9 + 2). Brief estimated
"~18–27" — landed near the top of that range.

## Verification result

```
uv run pytest -q tests/unit tests/integration  →  611 passed, 5 skipped in 34.62s
uv run mypy                                    →  Success: no issues found in 69 source files
```

**Pre-slice baseline on the actual worktree base (`0c76a21`)**: **586
passed + 5 skipped**.

The task brief quoted "588 passed + 3 skipped (verified by Manual Test
on 2026-05-28)" from commit `1d12ee5`. The 5 skipped on my worktree vs
3 quoted is a deterministic environment difference — the dev box has
2 extra skips that are environment-conditional (likely Node-dependent
jest integration tests skipping on a slightly different node version);
the brief itself flagged "Pytest baseline drift" as a known phenomenon
in the precedent history doc. The +25 delta is independently
verifiable on the worktree base.

mypy: 69 source files, `--strict` unchanged. **0 new src files added**
(item 3 + 4 extended `derive.py` per the brief's "no new files needed"
guidance — Regression's `b32084d` pattern).

## Item-by-item compliance with the brief

### Item 1 — Split `run_not_analyzable` ✓

- `REASON_MISSING_DERIVED_FACTS = "missing_derived_facts"` added to
  `results.py` with `Final[str]` typing matching the existing 4.
- `KNOWN_REASONS` extended to 5 elements; the new docstring's "When
  does each reason fire" section describes both halves of the split
  explicitly.
- `retrieval.py::get_localization_findings` cache-empty branch
  re-routed to `REASON_MISSING_DERIVED_FACTS`; `detail="findings not
  yet derived"` preserved.
- `derive.py` audit: only one `REASON_RUN_NOT_ANALYZABLE` call site
  exists (the tombstoned-input branch); kept as the retained-narrower
  semantic. The cache-read branch in `derive.py` uses
  `read_localization_findings_raw` directly (not
  `get_localization_findings`), so it does not need re-routing — it
  short-circuits to returning the cached `LocalizationFinding` when
  present, never to any unavailable.

### Item 2 — `LocalizationUnavailable.to_dict()` ✓

- 3-key dict per the brief's exact shape. `run_reference` and `detail`
  emitted as `null` (not omitted) when `None`. Import `from typing
  import Any` added.

### Item 3 — `resolve_latest_analyzable_run` ✓

- Lives in `derive.py` (existing-module extension; mirrors Regression's
  `resolve_latest_baseline` in `compare.py`).
- Iterates `list_run_history(store)` newest-first; first `True` from
  `check_localization_availability` wins.
- Empty store → `LocalizationUnavailable(run_reference=None,
  reason=REASON_NO_RUN_EVIDENCE, detail="no runs in store")`.
- All non-analyzable → `LocalizationUnavailable(run_reference=None,
  reason=REASON_RUN_NOT_ANALYZABLE, detail="no analyzable runs in
  store (N candidates checked)")`.
- Pure read; never derives, never writes — exercised by the spy +
  filesystem assertion in `test_resolve_does_not_invoke_derive`.

### Item 4 — `derive_latest_localization` ✓

- Lives in `derive.py` next to `derive_localization_findings`.
- Signature follows the brief: keyword-only `formula` (default
  `DEFAULT_FORMULA = "ochiai"`), keyword-only `top_n` (default
  `DEFAULT_TOP_N = 10`).
- Pure composition: `resolve_latest_analyzable_run` →
  `derive_localization_findings(store, ref, top_n=..., formula=...)`.

## DoD bullets believed closed

**NONE.** Per the brief's explicit instruction — this slice ships no
CLI / orchestration / envelope changes; all Phase 4 §4 bullets require
the CLI verb cycle.

## Deviations from the brief

**None of substance.** Two minor notes for PM:

1. The brief showed item 4's signature with `formula` before `top_n`
   in the keyword-only block, but the existing
   `derive_localization_findings` declares them as `top_n, *, formula`.
   I kept the order `formula, top_n` on `derive_latest_localization`
   to match the brief's signature exactly; this is functionally
   equivalent since both are keyword-only, but the two functions are
   now ordered differently inside `derive.py`. PM may want to reconcile
   to one canonical order in the v2 supersede decision (Phase 4
   follow-up Orchestration slice exposes both through `--formula` /
   `--top-n` flags — the ordering is purely an internal kwargs surface
   concern).
2. The `detail` string for the all-non-analyzable case is
   `"no analyzable runs in store (N candidates checked)"` where N is
   the exact count probed (matches the brief verbatim). The count
   includes tombstoned entries that were encountered during the walk
   (because `list_run_history` returns both live and tombstoned, and
   `check_localization_availability` is what filters them out). If PM
   would prefer N to count only live runs, that's a tiny tweak to
   surface as a v2 refinement.

## Pinned working-draft details for the v2 supersede

For the post-cycle v2 of `decisions/2026-05-28-localization-finding-shape.md`:

- **§6 `LocalizationUnavailable.to_dict()` shape**: 3 keys in this
  order — `run_reference`, `reason`, `detail`. All always present.
  `run_reference` is `null` or the result of `RunReference.to_dict()`.
  `detail` is `null` or a string. The serialization is JSON-stable
  (verified by `test_to_dict_is_json_serializable`).
- **§X split**: `REASON_MISSING_DERIVED_FACTS = "missing_derived_facts"`
  (underscore form). Cache-empty in `get_localization_findings` →
  this reason. Tombstoned input in `derive_localization_findings` →
  `REASON_RUN_NOT_ANALYZABLE` (narrowed). The hyphenated form
  (`"missing-derived-facts"`) is explicitly rejected by the
  `__post_init__` enum guard — Localization keeps underscore form to
  match its existing convention; the Regression / Localization
  reason-string conventions stay independent.
- **`resolve_latest_analyzable_run` Unavailable shape**: when no
  analyzable run exists, `run_reference=None` (the resolver has no
  single ref to point at — it is a per-store query, not a per-run
  query). This matches `find_runs_for_target` returning `[]` for
  Memory — the latest-resolution helpers never fabricate a ref.
- **`derive_latest_localization` kwargs**: `formula="ochiai"`,
  `top_n=10`. Matches `derive_localization_findings` defaults and
  threads them through unchanged.

## Open items / surprises

None of substance. Two small observations for the PM's follow-up
bookkeeping:

1. **`design/interace-contract/localization.md` is now 100% covered
   on the Internal interface table** — all 5 Internal rows
   (`derive_localization_findings`, `resolve_latest_analyzable_run`,
   `derive_latest_localization`, `get_localization_findings`,
   `check_localization_availability`) are implemented and exported
   from `novetest.localization`. PM may want to mirror Regression's
   2026-05-27 history doc note ("engine surface 100% covered") when
   writing the cycle-close history. The two External rows
   (`novetest localization <run_id>` / `novetest localization latest`)
   are pure CLI projection — Orchestration territory for the next
   cycle, no further engine surface needed.
2. **One docstring forward-reference removed**: the prior
   `__init__.py` docstring listed `resolve_latest_analyzable_run` +
   `derive_latest_localization` as "out of scope for this slice" (a
   correct forward reference at the Phase-4-entry slice). With this
   slice they're in-scope; I moved them into the "Public API exposes"
   section and removed the line from the "Explicitly OUT" list. No
   functional change.

## Charter hooks compliance

- WORKLOG.md: new entry appended to the top per format.
- Handoff (this file): written.
- INDEX.md: regenerated via `python3 tools/regen_comms_index.py`.
- All four (WORKLOG.md + handoff + INDEX.md + src/) staged together
  for one commit — the `PreToolUse` hook will block otherwise.
