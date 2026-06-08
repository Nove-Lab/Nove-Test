---
from: novetest-regression-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-06-08
slug: fixed-tests-spec
related:
  - agent-comms/tasks/regression-team-2026-06-08-fixed-tests-spec.md
  - agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
---

# Handoff — Regression engine `fixed_tests` 명세 정리

## Verdict

**INTENT** (not bug). D6 Scenario F+ behavior is the intended design.
Phase 2a — strengthen contract docs + pin tests — was executed.

## D6 Scenario F+ interpretation

Manual Test 2026-06-01 observed `summary.regressed == 0 AND
summary.fixed == 0` despite one run failing and another passing.
Under the documented (and now contract-pinned) Transition Detection
Semantics, this is the **correct behavior** when the two Run Records'
`test_results` `node_id` sets are disjoint: the per-test signal lives
entirely in `summary.added` and `summary.removed`. A consumer reading
`regressed == 0 AND fixed == 0` MUST also read `added` and `removed`
before concluding "nothing changed" — this is now explicit in the
interface contract under "Transition Detection Semantics" §
"Disjoint test sets are still a valid comparison".

Likely cause of the D6 observation: the two runs Manual Test was
comparing went through different code paths that resulted in
non-overlapping `node_id` discovery — for example, one run errored
before pytest collected any test, so its `RunRecord.test_results`
came back empty/different, while the other ran the full suite. The
fact set was correct under the intent; the operator's intuition
("fail vs pass → fixed transitions expected") inverted the binding
rule.

## Evidence supporting INTENT

1. **Decision §3 closed enum** (`decisions/2026-05-26-regression-facts-json-layout.md`):
   `added` is `(B=missing, T=present (any outcome))` and `removed` is
   `(B=present, T=missing (any outcome))`. The "any outcome" qualifier
   is explicit and load-bearing.
2. **Decision §C.7 consumer guidance**: already tells future Localization
   to filter via `category=="added" AND target_outcome fail-like` for
   newly-introduced failures. This wording only makes sense if
   `regressed` deliberately does NOT cover the "test newly appeared
   AND fails" case — proving the separation is intentional.
3. **Source `compare.py:_build_transitions`** (lines 386-406): walks
   `sorted(set(baseline_by_id) | set(target_by_id))` — the UNION. The
   `if baseline_tr is None and target_tr is not None: category = "added"`
   / `elif target_tr is None and baseline_tr is not None: category = "removed"`
   branches fire BEFORE the bucket classifier runs — structurally
   separating set-membership classification from outcome-bucket
   classification.
4. **Model docstring invariant** (`regression_fact_set.py:69`):
   `baseline_outcome is None EXACTLY when category == "added"`. The
   schema literally cannot encode "fixed with no baseline outcome".

## Worktree

- **Path**: `/home/yjshin/dev/aispace/novetest-regression-fixed-tests-spec`
- **Branch**: `regression-team/fixed-tests-spec`
- **Base commit**: `4184cd1` (current main tip)
- **Tip commit**: `a70f1f1 docs(regression): pin transition-detection set semantics + D6 F+ tests (intent verdict)`

Single commit. Ready to FF-merge after the parallel `localization` slice
(per task §"Main Branch merge 순서": alphabetic `localization` → `regression`).

## Files written / modified

| File | Status | Purpose |
| --- | --- | --- |
| `design/interace-contract/regression.md` | modified | +29 lines — new "Transition Detection Semantics" subsection (the binding contract for set-membership classification + consumer guidance for newly-introduced failures/passes) |
| `tests/unit/regression/test_compare.py` | modified | +52 lines — one new headline pin `test_disjoint_test_sets_yield_zero_regressed_and_zero_fixed`, placed adjacent to the 9 existing `test_category_*` cases so the canonical grep target for transition semantics carries the D6 resolution |
| `tests/integration/regression/test_transition_set_semantics.py` | NEW | 4 new integration tests: (1) same-`node_id` fail→pass populates `fixed`, (2) symmetric same-`node_id` pass→fail populates `regressed`, (3) **D6 F+ reproducer** — disjoint sets yield zero regressed+fixed with non-zero added+removed, (4) mixed-set independent classification |
| `WORKLOG.md` | modified | +10 lines — phase3 / B1-polish entry per charter format |

Zero source changes. The intent verdict means the existing logic is correct;
only documentation + tests needed strengthening.

## Verification result

- **mypy**: `uv run mypy --strict src/novetest` → **clean, 92 source files**.
- **Focused regression suite**: `uv run pytest -q tests/unit/regression tests/integration/regression` → **94 passed in 0.19s** (was 90, +4 new tests).
- **Full unit + integration sweep**: `uv run pytest -q tests/unit tests/integration` → **1180 passed + 26 skipped + 1 failed in 31.67s**.
  - The 1 failure is `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter`, which requires `.NET SDK 8.0+` on PATH (not equipped on this general host).
  - **Verified environmental**: the same test was re-run against the unmodified main checkout tip `4184cd1` (`/home/yjshin/dev/aispace/Nove-Test`) and failed identically. This is pre-existing, NOT caused by this slice.
  - Per task §"§2.5 equip-and-exercise 게이트": this slice touches NEITHER native adapter src NOR Run-team integration tests → §2.5 gate does not fire → general host is the acceptable verification environment.

## Worklog entry text

(Pasted verbatim from `WORKLOG.md` as appended in commit `a70f1f1`.)

```
## 2026-06-08 — B1 polish / regression-fixed-tests-spec (intent verdict + contract strengthening)

- Landed: Q&A slice for the D6 Scenario F+ carry-forward — Manual Test
  2026-06-01 observed `summary.regressed == 0 AND summary.fixed == 0`
  despite one run failing and another passing. **Verdict: INTENT, not
  bug.** Zero source changes. Evidence grounded in (a) `decisions/
  2026-05-26-regression-facts-json-layout.md` §3 closed 9-category
  taxonomy where `added`/`removed` are explicitly outcome-direction-
  agnostic (`(any outcome)` qualifier), (b) decision §C.7 which already
  tells consumers to filter `category == "added" AND target_outcome
  fail-like` for newly-introduced failures (proving the design
  separates same-set transitions from set-membership changes), (c)
  `src/novetest/regression/compare.py:_build_transitions` walking the
  **union** of `node_id`s with structural branching that sends only-
  baseline→`removed` / only-target→`added` BEFORE the bucket
  classifier runs, (d) `src/novetest/models/regression_fact_set.py:69`
  docstring encoding the invariant `baseline_outcome is None iff
  category=="added"`. The behavior is the intended design; the gap was
  documentation. `design/interace-contract/regression.md` gains a new
  "Transition Detection Semantics" subsection with the binding
  language: union-walk over `node_id`s, same-`node_id`-required-for-
  `fixed`/`regressed`, target-only→`added`-regardless-of-outcome,
  baseline-only→`removed`-regardless-of-outcome, plus consumer
  guidance for the "newly-introduced failure" filter (cross-referenced
  to decision §C.7). One new unit test under
  `tests/unit/regression/test_compare.py::test_disjoint_test_sets_yield_zero_regressed_and_zero_fixed`
  pins the headline finding (placed adjacent to the 9
  `test_category_*` cases so the canonical grep target carries the D6
  resolution). Three new integration tests under
  `tests/integration/regression/test_transition_set_semantics.py`: (1)
  `test_same_node_id_fail_to_pass_populates_fixed` (symmetric positive
  control), (2) `test_same_node_id_pass_to_fail_populates_regressed`
  (the regressed counterpart), (3) `test_disjoint_test_sets_yield_empty_fixed_and_regressed`
  (the D6 reproducer at the full Memory+Persistence+Engine seam), (4)
  `test_mixed_sets_classify_each_node_id_independently` (shared
  transition + target-only fail + baseline-only pass — proves each
  `node_id` is classified independently per the union walk).
- Verified: `uv run mypy --strict src/novetest` → **clean, 92 source
  files**. `uv run pytest -q tests/unit/regression
  tests/integration/regression` → **94 passed in 0.19s** (was 90, +4
  new tests). `uv run pytest -q tests/unit tests/integration` →
  **1180 passed + 26 skipped + 1 failed** — the 1 failure is
  `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter`
  requiring `.NET SDK 8.0+` on PATH (not equipped on this general
  host; pre-existing, verified by running the same test against the
  unmodified main checkout tip `4184cd1` — fails identically). Per
  task §"§2.5 equip-and-exercise 게이트" this slice does NOT touch
  Run-team src + integration tests simultaneously → §2.5 gate does
  NOT fire → general host is acceptable.
- Left open: None within this slice's scope. The 4 carry-forward D6-
  F+ observations are now documented + pinned. If future Manual Test
  surfaces a *different* surprise around set semantics (e.g. an
  outcome string nobody expected lands in the unknown-outcome
  warning surface), the existing `unknown-outcome:<engine>:<raw>`
  channel handles it.
- Gotcha: (a) The task brief used the shorthand `fixed_tests` /
  `regressed_tests` but the actual data shape uses `summary.fixed` /
  `summary.regressed` (counts) + `test_transitions[].category ==
  "fixed" | "regressed"` (per-test) — there are NO top-level array
  fields named `fixed_tests` / `regressed_tests`. The Manual Test
  observation translates cleanly because the operator was reading the
  inspect-envelope's projection where those counts surface.
  Documented this implicitly by referencing `summary.fixed` /
  `summary.regressed` in the contract doc, not the shorthand. (b) The
  intent is encoded across THREE source-of-truth surfaces: decision
  §3 (closed enum), `_build_transitions` structural branching, AND
  the model dataclass docstring's invariant. Any future "let's add a
  category that mixes outcome with set-membership" idea would have to
  update all three; the closed-enum + schema_version-bump rule from
  decision "Forward-compatible extension rules" enforces this. (c)
  The unit test placement next to the 9 `test_category_*` cases is
  deliberate: a grep for `test_category_` is the canonical entry
  point for "what does each category mean"; placing the disjoint-set
  test there means future operators reading that file find the D6
  resolution in the same scroll. (d) The integration test seeded the
  disjoint-set case with `baseline_status="failed"` and target's
  default `passed` — the `RunRecord.status` field is independent of
  per-test outcomes (it's an aggregate set by the adapter), and the
  engine does NOT use it to gate transition detection. The contract
  walked the per-`node_id` `test_results`, not the aggregate status.
- Next: PM dispatches Main Branch team to FF-merge worktree
  `regression-team/fixed-tests-spec` (alphabetic order: `localization`
  → `regression`, per task §"Main Branch merge 순서"). Manual Test
  verifies the contract addition reads naturally for an operator who
  saw the D6 F+ surprise, and re-runs a fresh disjoint-set comparison
  through `novetest regression compare` to confirm the documented
  behavior + envelope shape align.
```

## DoD bullets believed closed

**None.** This slice is a polish / Q&A cycle for a deferred carry-forward
observation; it does not close any unchecked DoD bullet in
`design/implementation-plan/delivery-phasing.md`. The previously closed
Regression Phase 3 bullets are unaffected.

## Open items / surprises

- **Not a contract-shape change**: the slice strengthens the interface-contract
  document but introduces NO new dataclass field, NO new `REASON_*` constant,
  NO new `TRANSITION_CATEGORIES` value, NO new well-known `warnings` code. Per
  charter "Reporting back" hint, no `decisions/` follow-up is needed.
- **No envelope-shape change**: the slice does NOT introduce a new
  `regression_outcome` / `regression_delta` envelope variant; the already-frozen
  `decisions/2026-05-28-regression-outcome-envelope-shape.md` covers the
  existing wire shape unchanged.
- **Pre-existing dotnet-test environmental failure**: noted in Verification
  above; environmental, not caused by this slice. Per the §2.5 decision, this
  general host is the correct verification environment for a docs+tests slice
  that does not touch Run-team src.
- **Parallel cycle pair**: the Localization team's `defect7-failure-proximity-warning-loop`
  slice is running in parallel (per task §"Cross-team coordination"). Zero file
  footprint overlap by design; Main Branch FF-merges in alphabetic order
  `localization` → `regression` per the brief.
- **No `agent-comms/INDEX.md` regen committed in the worktree** — the worktree
  only carries the four code/docs files + WORKLOG. The handoff file landing in
  the same worktree means Main Branch will see this handoff when reading
  `agent-comms/handoffs/` on the merged tip. PM regenerates INDEX as part of
  the standard cycle close.

## Manual Test recommendations

After Main Branch merge, suggested Manual Test scenarios:

1. **Contract readability check**: read the new "Transition Detection Semantics"
   subsection in `design/interace-contract/regression.md` from the perspective
   of an operator who saw the D6 F+ surprise. Does it answer "why are
   `regressed`/`fixed` both zero when one run failed and the other passed?"
   without requiring the reader to also open `decisions/2026-05-26-...`.
2. **End-to-end disjoint-set reproducer via CLI**: against a fresh project
   store, run `novetest run` twice with intentionally disjoint test selections
   (e.g. `pytest tests/foo.py` then `pytest tests/bar.py`), then
   `novetest regression compare <run1> <run_id> <run2_id>` — confirm the
   resulting `regression_outcome.kind == "fact-set"` envelope carries
   `summary.regressed == 0 AND summary.fixed == 0 AND summary.added >= 1
   AND summary.removed >= 1`. This is the CLI-level translation of the
   integration test `test_disjoint_test_sets_yield_empty_fixed_and_regressed`.
3. **Same-set sanity check**: run pytest against the same fixture twice with
   the SAME test selection, but flip a single test's outcome between runs
   (edit fixture between calls). Confirm the resulting fact set carries the
   `fixed` or `regressed` count >= 1 on the appropriate side. Cross-validates
   that the contract pin doesn't accidentally suppress the populated case.
