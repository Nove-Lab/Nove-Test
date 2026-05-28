---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-05-28
slug: engine-completion
related:
  - agent-comms/decisions/2026-05-28-localization-finding-shape.md
  - agent-comms/history/2026-05-28-gotest-adapter-and-localization-phase4-entry.md
  - agent-comms/history/2026-05-27-phase3-regression-engine-complete.md
  - design/implementation-plan/delivery-phasing.md
  - design/interace-contract/localization.md
---

# Task: Localization engine surface completion (Phase 4 engine close-out)

This slice finishes the Localization engine's internal interface
surface so the upcoming CLI verb cycle (Orchestration team, next
planning cycle) is pure CLI projection on top of a complete engine
boundary. **Engine-only slice — no CLI / orchestration / envelope
changes in this brief.**

Mirrors the precedent set by the Regression team's baseline-resolution
slice (`b32084d`, cycle close
`history/2026-05-27-phase3-regression-engine-complete.md`).

## Mandatory pre-flight reading

In order:

1. `.claude/agents/novetest-localization-team.md` (your charter)
2. `agent-comms/decisions/2026-05-28-localization-finding-shape.md` —
   the freeze that pins the contracts you are now extending. §X is
   the binding directive for item 1 below.
3. `agent-comms/history/2026-05-27-phase3-regression-engine-complete.md`
   — the precedent cycle. Item 3 + 4 below mirror Regression's
   `resolve_latest_baseline` / `derive_latest_regression` pattern.
4. `src/novetest/regression/results.py` lines 28–66 — the reference
   pattern for items 1 (split) and 2 (`to_dict()`).
5. `src/novetest/localization/results.py` — current source-of-truth
   you're modifying.
6. `src/novetest/localization/retrieval.py` — the cache-empty path
   you're re-routing.

## Scope — 4 items, all small

### Item 1 — Split `run_not_analyzable` (CEO-approved per freeze §X)

The current `run_not_analyzable` reason code is overloaded across two
semantically distinct sub-cases. Split per the freeze decision §X
table:

| Reason | New meaning (post-split) |
|---|---|
| `missing_derived_facts` (NEW) | Cache empty — `get_localization_findings` called before `derive_localization_findings`. Recoverable: caller should `derive`. |
| `run_not_analyzable` (RETAINED, NARROWED) | Run is structurally non-derivable: tombstoned Run Record, evidence corruption. NOT recoverable. |

**Required changes:**

- `src/novetest/localization/results.py`:
  - Add `REASON_MISSING_DERIVED_FACTS: Final[str] = "missing_derived_facts"`
    constant.
  - Extend `KNOWN_REASONS` frozenset to include it (final 5-element
    set: `no_failed_tests`, `no_coverage`, `no_run_evidence`,
    `missing_derived_facts`, `run_not_analyzable`).
  - Update the docstring "When does each reason fire" section to
    describe the new split (cache-empty → `missing_derived_facts`;
    tombstoned-or-corrupt → `run_not_analyzable`).
- `src/novetest/localization/retrieval.py`:
  - The cache-empty branch in `get_localization_findings` (the one
    that today returns `LocalizationUnavailable(reason=REASON_RUN_NOT_ANALYZABLE, detail="findings not yet derived")`)
    must switch to `REASON_MISSING_DERIVED_FACTS`. Keep the `detail`
    string informative (e.g. `"findings not yet derived"`).
  - Any other path inside this module that currently surfaces
    `run_not_analyzable` for cache-empty reasons must also move; any
    path that surfaces it for actually-tombstoned / corrupted records
    stays.
- `src/novetest/localization/derive.py` and any other module:
  - Audit for usages of `REASON_RUN_NOT_ANALYZABLE`. Each call site
    must be classified: keep (tombstoned/corrupt) or migrate
    (cache-empty / missing-derived).

**Tests to add/update** (`tests/unit/localization/`):

- New: `missing_derived_facts` is in `KNOWN_REASONS`.
- New: `LocalizationUnavailable(reason=REASON_MISSING_DERIVED_FACTS)`
  constructs successfully.
- Existing test that asserted "cache empty → `run_not_analyzable`"
  must update to "cache empty → `missing_derived_facts`".
- New: a test that exercises the tombstoned-run path AND asserts
  `run_not_analyzable` is the result (proves the retained-narrower
  branch still works).
- Negative: `LocalizationUnavailable(reason="missing-derived-facts")`
  (the hyphenated form Regression uses) is REJECTED — Localization
  uses underscore_form to match its existing convention.

### Item 2 — Add `LocalizationUnavailable.to_dict()`

Currently absent; flagged as a "known gap" in freeze §6. Mirror
`RegressionUnavailable.to_dict()` shape.

**Required changes:**

- `src/novetest/localization/results.py`:
  - Add `def to_dict(self) -> dict[str, Any]:` method on
    `LocalizationUnavailable`.
  - Output shape (3 keys, all always present):
    ```python
    {
        "run_reference": (
            None if self.run_reference is None
            else self.run_reference.to_dict()
        ),
        "reason": self.reason,
        "detail": self.detail,
    }
    ```
  - `detail` is emitted as `null` when `None` — DO NOT omit the key.
  - `run_reference` likewise — emit `null` when `None`, do not omit.
  - Required import: `from typing import Any`.

**Tests to add** (`tests/unit/localization/`):

- `to_dict()` returns the 3 keys for each of the 5 `KNOWN_REASONS`.
- `run_reference` round-trips through `.to_dict()` correctly (use
  `RunReference.to_dict()` as the inner shape).
- `run_reference = None` → output key is `null`, not absent.
- `detail = None` → output key is `null`, not absent.

### Item 3 — `resolve_latest_analyzable_run`

The cheap-resolution helper that returns the most-recent Run Reference
in the store for which `check_localization_availability` would return
True. Used by item 4 and (next cycle) by `novetest localization latest`.

**Signature:**

```python
def resolve_latest_analyzable_run(
    store: ProjectStore,
) -> RunReference | LocalizationUnavailable: ...
```

(`ProjectStore` typing: import from `novetest.memory.store` — match
the pattern existing localization functions use.)

**Required behavior:**

- Iterates `memory/list_run_history` in reverse-chronological order
  (latest first).
- For each candidate, runs `check_localization_availability(store, ref)`
  (the cheap probe). Returns the first reference for which it returns
  True.
- If NO analyzable run exists in the store:
  - If the store has zero runs total → return
    `LocalizationUnavailable(run_reference=None, reason=REASON_NO_RUN_EVIDENCE, detail="no runs in store")`.
  - If the store has runs but NONE are analyzable → return
    `LocalizationUnavailable(run_reference=None, reason=REASON_RUN_NOT_ANALYZABLE, detail="no analyzable runs in store (N candidates checked)")`
    where N is the actual count probed.
- Does NOT actually derive findings (cheap-only).
- Pure read; no side effects on disk.

**File placement:** module of your choosing within
`src/novetest/localization/` (existing module extension preferred — no
new files needed; see Regression's pattern in `b32084d`'s diff).

**Tests** (`tests/unit/localization/` + at least one in
`tests/integration/localization/`):

- Returns the latest analyzable run when multiple exist.
- Skips a tombstoned run and returns the next analyzable one.
- Returns `REASON_NO_RUN_EVIDENCE` Unavailable when store is empty.
- Returns `REASON_RUN_NOT_ANALYZABLE` Unavailable when all runs are
  non-analyzable (e.g. all lacking coverage).
- Does NOT trigger `derive_localization_findings` as a side effect
  (verifiable via spy on the derive function or absence of writes
  under `<store>/localization/findings/`).
- Integration: real Project Store fixture with one passing run +
  one failing-no-coverage run + one failing-with-coverage run →
  returns the failing-with-coverage one.

### Item 4 — `derive_latest_localization`

Composition: `resolve_latest_analyzable_run` + `derive_localization_findings`.

**Signature:**

```python
def derive_latest_localization(
    store: ProjectStore,
    *,
    formula: str = "ochiai",
    top_n: int = 10,
) -> LocalizationFinding | LocalizationUnavailable: ...
```

(Match `derive_localization_findings`'s kwargs surface — same defaults,
same parameter semantics. If `derive_localization_findings` accepts
more kwargs today, pass them through.)

**Required behavior:**

- Calls `resolve_latest_analyzable_run(store)`.
- If result is `LocalizationUnavailable` → return it unchanged
  (caller sees the same reason/detail).
- If result is a `RunReference` → call
  `derive_localization_findings(store, ref, formula=formula, top_n=top_n)`
  and return whatever it returns.
- No additional logic. Pure composition.

**File placement:** same module as `derive_localization_findings`
(`src/novetest/localization/derive.py`).

**Tests** (`tests/unit/localization/` + at least one in
`tests/integration/localization/`):

- Happy path: store has one analyzable run → returns
  `LocalizationFinding` with `run_reference` matching the resolved
  run.
- Empty store: returns `LocalizationUnavailable(reason=REASON_NO_RUN_EVIDENCE)`.
- All non-analyzable: returns
  `LocalizationUnavailable(reason=REASON_RUN_NOT_ANALYZABLE)`.
- Integration: end-to-end through real Project Store + per-test
  coverage fixture (you may reuse the `localization-branch` fixture
  the Phase 4 entry slice already exercises).
- Forward args propagation: `formula="op2", top_n=5` reaches the
  underlying derive call (verifiable via the resulting finding's
  `formula` field and `len(entries) <= 5`).

## Out of scope

These belong to the NEXT cycle (Orchestration team) — do NOT touch:

- `novetest localization <run_id>` or `novetest localization latest`
  CLI verbs.
- `localization_outcome` envelope projection.
- `--formula` / `--top-n` / `--mode` CLI flags.
- `inspect` Localization section extension.
- `sbfl_aggregate` or `failure_proximity` modes (still reserved enum
  values; producers ship later).

## Test gate

Before handoff:

```bash
uv run pytest -q tests/unit tests/integration
uv run mypy
```

Baseline on main as of merge of `1d12ee5` is **588 passed + 3 skipped**
(verified by Manual Test on 2026-05-28). Expected post-slice: ~600+
passed + 3 skipped (you're adding ~18–27 tests across the 4 items).
**Run the baseline yourself on the pre-slice commit and quote the
exact number in your handoff** — per the lesson logged in
`history/2026-05-27-phase3-regression-engine-complete.md` "Pytest
baseline drift" section.

mypy must remain clean (currently 69 source files; you may add 0–1
files. Strict mode unchanged.).

## Verification model — expected `status: record-only`

This slice ships NO CLI / orchestration / envelope changes, so Main
Branch should write a `status: record-only` verification and waive
Manual Test, mirroring the precedent in
`2026-05-26-phase3-regression-engine-and-memory-probe.md` and
`2026-05-27-phase3-regression-engine-complete.md`. Your handoff should
explicitly state "no Manual Test action requested — engine-only
slice, no user-facing surface" so Main Branch picks up the convention
unambiguously.

## Handoff expectations

In your `agent-comms/handoffs/localization-team-2026-05-28-engine-completion.md`:

- Commit SHA + worktree path + branch name.
- File-by-file diff summary (which modules grew, by how much).
- Test count (new tests by item) + final pytest count.
- mypy: clean confirmation.
- **DoD bullets believed closed:** state explicitly **"NONE"** for
  this slice — Phase 4 §4 bullets all require the CLI verb cycle.
- Any deviations from this brief (with rationale).
- Any pinned working-draft details PM should freeze in the v2
  supersede decision after cycle close (e.g. unexpected `to_dict()`
  shape choices, edge cases in `resolve_latest_analyzable_run`).

## Post-cycle PM follow-up (informational — not your responsibility)

After this cycle closes cleanly, PM will write a v2 supersede of
`decisions/2026-05-28-localization-finding-shape.md` per its §X
("When implemented, this decision is superseded by v2"). The v2 will
codify:
- Final 5-element `KNOWN_REASONS`.
- `LocalizationUnavailable.to_dict()` shape pinned.
- Any working-draft details you surface in the handoff.

You do not draft this; PM does it as cycle-close work.

## Charter hooks reminder

Per `.claude/agents/novetest-localization-team.md` and the cross-cutting
PM oversight protocol:

1. Append a new entry to the top of `WORKLOG.md` per its format.
2. Write the handoff referenced above.
3. Run `python3 tools/regen_comms_index.py`.
4. Stage `WORKLOG.md` + handoff + INDEX alongside source.
5. The `PreToolUse` hook will block `git commit` if `WORKLOG.md` is
   not staged with `src/` changes.

If anything in this brief is unclear or you discover a design issue
during implementation, escalate via
`agent-comms/questions/<team>-<date>-<slug>.md` rather than guessing.
