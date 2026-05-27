---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-05-27
slug: regression-cli
related:
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md
  - agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md
  - design/interace-contract/regression.md
  - design/interace-contract/orchestration.md
  - design/implementation-plan/delivery-phasing.md
---

# Task: Phase 3 Regression CLI surface + `inspect` Regression section

Project the now-100%-complete Regression engine surface onto the CLI
envelope. This is a **pure projection slice** — no engine work, no Memory
work, no new `REASON_*` / `TRANSITION_CATEGORIES`. All five Regression
helpers (`compare_runs`, `resolve_latest_baseline`,
`derive_latest_regression`, `get_regression_facts`,
`check_regression_availability`) already exist and are exhaustively
tested. Your job: wrap them in Cyclopts commands and add a Regression
section to `InspectView`.

This single slice closes **Phase 3 DoD bullets `[156] [157] [158]`** in
`design/implementation-plan/delivery-phasing.md`.

---

## Pre-flight reading (mandatory)

1. `.claude/agents/novetest-orchestration-team.md` (your charter)
2. `CLAUDE.md`
3. `agent-comms/INDEX.md`
4. `agent-comms/decisions/2026-05-26-regression-facts-json-layout.md` —
   the binding contract for `regression_facts.json` and the 6 `REASON_*`
   constants. **Especially §C.1 (tombstone fail-hard) and §C.2 (envelope
   freeze cadence: ship → Manual Test field → PM freezes).**
5. `agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md`
   and `agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md`
   — the **pattern you are mirroring** for `regression_outcome` and the
   `compare` verb's combined block.
6. `WORKLOG.md` top 3 entries.
7. `design/interace-contract/regression.md` (read-only — Regression team's
   territory; you are a consumer).
8. `design/interace-contract/orchestration.md` (your own contract — note
   the three rows you are implementing: `novetest regression compare`,
   `novetest regression latest`, `novetest compare`, plus `inspect`'s
   extended Regression section per the row's "when resolvable" clause).
9. **Read the current `src/novetest/cli/app.py` end-to-end before
   editing.** The file is ~700 lines; the patterns you are following are
   `coverage_show` / `coverage_diff` / `_coverage_outcome_payload` /
   `_coverage_delta_payload` / `_resolve_run_reference` / `inspect_cmd`.
   Mirror those patterns exactly — same naming style, same error
   structure, same use of `_require_store`, same exit codes.

---

## Pre-slice baseline (verified by PM at the base commit)

- Base commit: `82e1775` (`comms: close Phase 3 regression
  baseline-resolution cycle`).
- `uv run pytest -q tests/unit tests/integration` → **442 passed + 3
  skipped** (PM ran this on 2026-05-27 against the exact base commit; the
  3 skips are the pre-existing Node-dependent jest integration tests on
  this dev host — same as the prior cycle).
- `uv run mypy` → clean (57 source files, `--strict`).
- The expected post-slice baseline is roughly **470+3 to 480+3** given
  the test surface itemised in §Test surface below. The exact number is
  not load-bearing; the delta is.

---

## Scope

### What lands

1. **Three new CLI verbs** replacing existing stubs in
   `src/novetest/cli/app.py`:
   - `novetest regression compare <baseline_run_id> <target_run_id>`
   - `novetest regression latest`
   - `novetest compare <baseline_run_id> <target_run_id>`
2. **`inspect` Regression section** in
   `src/novetest/orchestration/workflows/inspect.py` — `InspectView`
   gains a `regression_outcome` field; `to_dict()` emits the matching
   block and flips `sub_reports["regression"]` from the current
   hardcoded `"unavailable"`.
3. **Three new envelope payload helpers** in `cli/app.py` (mirroring the
   coverage helpers byte-for-byte in structure — see §Envelope shapes):
   - `_regression_outcome_payload(outcome)` — projects
     `RegressionFactSet | RegressionUnavailable` onto a discriminated
     `{kind, ...}` dict.
   - `_compare_payload(regression_outcome, coverage_delta_outcome)` — or
     equivalent inline composition in `compare_cmd` — composes the two
     blocks into the `compare` verb's `data`.
   - (Reuse existing `_coverage_delta_payload` for the `compare` verb's
     coverage block — DO NOT duplicate.)
4. **Test surface** per §Test surface.

### What does NOT land (out of scope — keep diff surgical)

- **No `regression/**` or `memory/**` source changes.** You are a pure
  consumer.
- **No new `REASON_*` constants, no new `TRANSITION_CATEGORIES` values,
  no new envelope discriminator kinds.** Use only the 6 reasons and 9
  transition categories pinned by
  `decisions/2026-05-26-regression-facts-json-layout.md` §3 / §7.
- **No envelope-shape freeze.** The `regression_outcome` shape in
  §Envelope shapes is a **working draft for this slice**. Per decision
  §C.2 cadence, PM freezes it AFTER Manual Test fields it — same
  ship → field-test → freeze pattern the two Coverage envelope decisions
  followed.
- **No `--baseline=<run_id>` / `--since` overrides for `regression
  latest`.** `delivery-phasing.md` lists those under "Risks" as a future
  parameterisation — out of scope for this slice (the default policy is
  "latest two by `created_at`"; that's what `derive_latest_regression`
  already implements).
- **No default-verb alias** (`novetest <target>` ≡ `novetest test
  <target>`). That is Phase 6 (`design/interace-contract/orchestration.md`
  §Notes "Default verb (planned, Phase 6 activation)").
- **No `test`, `replay`, `localization` stub replacement.** Those stubs
  stay registered; only `compare` and the `regression` group are
  replaced. Update the `for _name in (...)` loop accordingly — see
  §Source changes 1c.
- **No new `tests/perf/` benchmarks.** Phase 3 has no NFR-REG-* perf
  bullet (unlike NFR-COV-002).
- **No `coverage_delta` shape changes.** The block is already frozen by
  `decisions/2026-05-16-coverage-delta-envelope-shape.md` — you import
  the existing `_coverage_delta_payload` projection and reuse it in
  `compare_cmd`. If you find yourself wanting to change its shape, stop
  and write a `questions/` for PM.

---

## Source changes

### 1. `src/novetest/cli/app.py`

#### 1a. New imports (top of file, alongside existing coverage imports)

```python
from novetest.regression import (
    RegressionFactSet,
    RegressionUnavailable,
    compare_runs,
    derive_latest_regression,
)
```

You do **not** need `resolve_latest_baseline`, `derive_regression_facts`,
or `get_regression_facts` in `cli/app.py` — `regression latest` calls
only `derive_latest_regression`, and `regression compare` /
`compare` call `compare_runs` directly. (`inspect.py` is a separate
file; its imports are in §2.)

#### 1b. New verb: `regression compare <baseline_run_id> <target_run_id>`

Register `regression_app = App(name="regression", help="Regression
commands.")`, attach via `app.command(regression_app)`. Mirror
`coverage_app` exactly. Then:

```python
@regression_app.command(name="compare")
def regression_compare(baseline_run_id: str, target_run_id: str) -> None:
    """Compare two specific Run Records and emit Regression Facts.

    Calls compare_runs(store, baseline_ref, target_ref) — the cache-aware
    entry point. On cache miss derives and persists; on cache hit reads.
    Tombstoned inputs surface REASON_RUN_TOMBSTONED per decision §C.1
    even when a stale cached file exists on disk.
    """
    store = _require_store("regression.compare")
    baseline_ref = _resolve_run_reference(store, "regression.compare", baseline_run_id)
    target_ref = _resolve_run_reference(store, "regression.compare", target_run_id)
    outcome = compare_runs(store, baseline_ref, target_ref)
    _emit_and_exit(
        Envelope(
            command="regression.compare",
            ok=True,
            data={"regression_outcome": _regression_outcome_payload(outcome)},
        ),
        EXIT_OK,
    )
```

`ok=True` even when `outcome` is `RegressionUnavailable` — the envelope
**transport** succeeded; the unavailable state is data, not a transport
error. This mirrors `coverage_show` / `coverage_diff` exactly. The CLI
exit code stays `EXIT_OK` (0) in both success and unavailable cases —
also mirroring Coverage.

The `_resolve_run_reference` helper already exists in `app.py` (around
line 420 — used by `coverage_show` and `coverage_diff`); reuse it. It
emits a `not-found` envelope and exits `EXIT_USAGE` (2) when the run_id
doesn't resolve in Memory — so a typo in either ID short-circuits before
`compare_runs` is called.

#### 1c. New verb: `regression latest`

```python
@regression_app.command(name="latest")
def regression_latest() -> None:
    """Resolve the latest comparable pair for the active target and emit Regression Facts.

    Composes the engine's derive_latest_regression(store) end-to-end:
    latest live run → its target_expression → most recent prior live run
    on the same target → compare_runs of the pair.
    """
    store = _require_store("regression.latest")
    outcome = derive_latest_regression(store)
    _emit_and_exit(
        Envelope(
            command="regression.latest",
            ok=True,
            data={"regression_outcome": _regression_outcome_payload(outcome)},
        ),
        EXIT_OK,
    )
```

#### 1d. New top-level verb: `compare <baseline_run_id> <target_run_id>`

```python
@app.command(name="compare")
def compare_cmd(baseline_run_id: str, target_run_id: str) -> None:
    """Composed Regression + Coverage view for a specific pair.

    Emits both regression_outcome and coverage_delta in the same envelope.
    The coverage_delta block is the same shape coverage diff emits — when
    either side lacks coverage facts, it surfaces kind="unavailable" with
    the propagated reason. Distinct from regression compare, which emits
    regression_outcome only.
    """
    store = _require_store("compare")
    baseline_ref = _resolve_run_reference(store, "compare", baseline_run_id)
    target_ref = _resolve_run_reference(store, "compare", target_run_id)
    regression_outcome = compare_runs(store, baseline_ref, target_ref)
    coverage_outcome = compare_coverage_facts(store, baseline_ref, target_ref)
    _emit_and_exit(
        Envelope(
            command="compare",
            ok=True,
            data={
                "regression_outcome": _regression_outcome_payload(regression_outcome),
                "coverage_delta": _coverage_delta_payload(coverage_outcome),
            },
        ),
        EXIT_OK,
    )
```

#### 1e. Stub registration cleanup

Current state (around line 595):

```python
for _name in ("test", "compare", "replay", "localization"):
    _register_flat_stub(_name)
_register_group_stub("regression", ("compare", "latest"))
```

After this slice:

```python
for _name in ("test", "replay", "localization"):
    _register_flat_stub(_name)
# "compare" promoted to real verb above.
# "regression" promoted to real sub-app above.
```

#### 1f. The `_regression_outcome_payload` helper

```python
def _regression_outcome_payload(
    outcome: RegressionFactSet | RegressionUnavailable,
) -> dict[str, Any]:
    """Project a Regression outcome onto the envelope wire shape.

    Working draft for this slice; PM freezes the shape via a `decisions/`
    entry AFTER Manual Test fields it (decision §C.2 cadence). See
    §Envelope shapes in the task brief for the draft.
    """
    if isinstance(outcome, RegressionFactSet):
        body = outcome.to_dict()
        body.pop("schema_version", None)  # envelope versioning lives at top-level `schema`
        return {"kind": "fact-set", **body}
    return {
        "kind": "unavailable",
        "baseline_run_reference": (
            outcome.baseline_run_reference.to_dict()
            if outcome.baseline_run_reference is not None
            else None
        ),
        "target_run_reference": (
            outcome.target_run_reference.to_dict()
            if outcome.target_run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }
```

The `schema_version` strip mirrors `_coverage_delta_payload` exactly
(top-level `"schema": "novetest/v1"` carries the envelope version).

**Note** — `RegressionUnavailable` carries `baseline_run_reference` and
`target_run_reference` as **two distinct optional fields** (per decision
§7) so the consumer can tell WHICH side is missing — analogous to but
richer than `CoverageUnavailable.run_reference` (a single field). Verify
the actual attribute names by reading
`src/novetest/regression/results.py` before coding the projection. If the
attribute names differ from this draft, USE the actual names — do not
introduce shape divergence by editing the source. Surface any mismatch
in your handoff so PM can pick it up at decision-write time.

### 2. `src/novetest/orchestration/workflows/inspect.py`

#### 2a. New imports

```python
from novetest.memory import (
    ProjectStore,
    RunEvidenceNotFoundError,
    find_runs_for_target,        # NEW
    list_run_history,
    retrieve_run_evidence,
)
from novetest.regression import (
    REASON_NO_COMPARABLE_BASELINE,  # NEW
    RegressionFactSet,              # NEW
    RegressionUnavailable,          # NEW
    compare_runs,                   # NEW
)
```

#### 2b. Extend `InspectView`

```python
@dataclass(slots=True, frozen=True)
class InspectView:
    entry: MemoryEntry
    coverage_outcome: CoverageFactSet | CoverageUnavailable
    regression_outcome: RegressionFactSet | RegressionUnavailable  # NEW

    def to_dict(self) -> dict[str, object]:
        record = self.entry.run_record
        coverage_present = isinstance(self.coverage_outcome, CoverageFactSet)
        regression_present = isinstance(self.regression_outcome, RegressionFactSet)
        return {
            "run_reference": record.run_reference.to_dict(),
            "run_summary": { ... unchanged ... },
            "coverage_outcome": _coverage_outcome_section(self.coverage_outcome),
            "regression_outcome": _regression_outcome_section(self.regression_outcome),  # NEW
            "sub_reports": {
                "coverage": "available" if coverage_present else "unavailable",
                "regression": "available" if regression_present else "unavailable",  # CHANGED
                "localization": "unavailable",
                "replay": "unavailable",
            },
        }
```

#### 2c. Extend `build_inspect_view` — Regression resolution composition

```python
def build_inspect_view(store: ProjectStore, run_id: str) -> InspectView | None:
    history = list_run_history(store)
    target = next(
        (e for e in history if e.run_record.run_reference.run_id == run_id),
        None,
    )
    if target is None:
        return None
    ref = target.run_record.run_reference
    try:
        entry = retrieve_run_evidence(store, ref)
    except RunEvidenceNotFoundError:
        return None
    return InspectView(
        entry=entry,
        coverage_outcome=get_coverage_facts(store, ref),
        regression_outcome=_resolve_inspect_regression(store, entry),  # NEW
    )


def _resolve_inspect_regression(
    store: ProjectStore,
    inspected: MemoryEntry,
) -> RegressionFactSet | RegressionUnavailable:
    """Resolve the baseline-for-this-specific-run and call compare_runs.

    The engine's resolve_latest_baseline returns the GLOBAL latest two
    runs on a target — wrong fit for `inspect <some_old_run>`, which
    wants "the most recent live run that is strictly OLDER than this
    one on the same target". Composed at the orchestration layer using
    Memory's find_runs_for_target + Regression's compare_runs. No new
    engine surface is added (decision: keep engine surface frozen, the
    composition is a 5-line orchestration concern — see PM cycle plan
    2026-05-27).

    Tombstoned inspected run: compare_runs returns
    RegressionUnavailable(REASON_RUN_TOMBSTONED) naturally per decision
    §C.1 — no special-case needed here.
    """
    inspected_ref = inspected.run_record.run_reference
    siblings = find_runs_for_target(
        store,
        inspected.run_record.target_expression,
        include_tombstoned=False,
    )
    prior = [
        s for s in siblings
        if s.run_record.run_reference.created_at < inspected_ref.created_at
    ]
    if not prior:
        return RegressionUnavailable(
            reason=REASON_NO_COMPARABLE_BASELINE,
            detail=inspected.run_record.target_expression,
            baseline_run_reference=None,
            target_run_reference=inspected_ref,
        )
    prior.sort(key=lambda e: e.run_record.run_reference.created_at, reverse=True)
    baseline_ref = prior[0].run_record.run_reference
    return compare_runs(store, baseline_ref, inspected_ref)
```

Verify `RegressionUnavailable`'s exact constructor signature in
`src/novetest/regression/results.py` and adjust the keyword arguments to
match. If the dataclass requires positional construction or differs from
the four-field shape above, USE the actual signature.

#### 2d. New `_regression_outcome_section` helper

In the same file, immediately below `_coverage_outcome_section`. Same
shape as `_regression_outcome_payload` in `cli/app.py` — duplicated
intentionally to avoid an `orchestration → cli` import cycle (the
Coverage analog already does this; see the existing comment on
`_coverage_outcome_section`). The shape is frozen by a future
`decisions/` entry, so drift risk is bounded.

---

## Envelope shapes — working drafts (DO NOT freeze in this slice)

### `regression_outcome` (NEW; this slice ships, PM freezes after Manual Test)

```json
// kind: "fact-set"
{
  "kind": "fact-set",
  "baseline_run_reference": { "run_id": "...", "created_at": "..." },
  "target_run_reference":   { "run_id": "...", "created_at": "..." },
  "engine_name": "pytest",
  "ecosystem": "python",
  "target_type": "path",
  "target_expression": "tests/",
  "summary": { /* 9 categories + 2 totals = 11 keys */ },
  "test_transitions": [ /* sorted by node_id */ ],
  "output_diff": null | { "stdout_changed": true|false, "stderr_changed": true|false,
                          "baseline_stdout_sha256": "...", "target_stdout_sha256": "...",
                          "baseline_stderr_sha256": "...", "target_stderr_sha256": "..." },
  "coverage_change": null | { /* CoverageDelta.to_dict() embedded verbatim */ },
  "warnings": [ /* zero or more "unknown-outcome:engine:raw" strings */ ],
  "metadata": { /* read-side-tolerant escape hatch, empty at v1 */ },
  "derived_at": "<ISO8601-UTC>"
}

// kind: "unavailable"
{
  "kind": "unavailable",
  "baseline_run_reference": null | { ... },
  "target_run_reference":   null | { ... },
  "reason": "run-not-found" | "run-tombstoned" | "no-comparable-baseline"
          | "missing-derived-facts" | "engine-mismatch" | "target-mismatch",
  "detail": "human-readable string"
}
```

The body of `kind: "fact-set"` is `RegressionFactSet.to_dict()` with
`schema_version` stripped — verify the exact key list by reading
`src/novetest/models/regression_fact_set.py` and updating this draft if
the source differs. The decision-time freeze will use the actual
source-of-truth shape, not this draft.

### `compare` verb envelope

```json
{
  "schema": "novetest/v1",
  "command": "compare",
  "ok": true,
  "data": {
    "regression_outcome": { ... regression_outcome shape above ... },
    "coverage_delta":     { ... existing coverage_delta shape (frozen) ... }
  },
  "errors": [],
  "warnings": []
}
```

The `coverage_delta` block is **already frozen** by
`decisions/2026-05-16-coverage-delta-envelope-shape.md` — you reuse the
existing `_coverage_delta_payload` projection function from
`cli/app.py`; no new shape work for the coverage half.

### `inspect` envelope (extended)

The existing inspect envelope grows one new top-level data field
(`regression_outcome`) and the `sub_reports.regression` value flips from
hardcoded `"unavailable"` to `"available"` / `"unavailable"` based on
the actual computed outcome. All other inspect fields unchanged.

---

## Test surface

Mirror the directory layout of the source you touch. Estimated 25–35
new tests total.

### `tests/unit/cli/test_regression_compare.py` (NEW; ~10 cases)

- Happy: two valid run_ids on the same target → envelope carries
  `regression_outcome.kind == "fact-set"`, `summary.regressed >= 0`, all
  9 summary keys present.
- Cache-hit path: call twice with the same args → second call returns the
  same `derived_at` (proves cache hit through the CLI layer).
- Each of the 6 `REASON_*` propagated: `run-not-found` (typo in
  baseline OR target — `_resolve_run_reference` catches this BEFORE
  `compare_runs` and returns `EXIT_USAGE`; the envelope is the
  `not-found` shape, not `regression_outcome.kind == "unavailable"`),
  `run-tombstoned` (baseline OR target tombstoned),
  `engine-mismatch` (pytest vs jest), `target-mismatch` (same engine
  different target), `missing-derived-facts` (covered by happy path's
  cache miss — surface `fact-set`, not `unavailable`),
  `no-comparable-baseline` (not exercised here — this reason is for
  `regression latest` / `inspect`, not explicit pair `compare`).
- Tombstone-after-cache override per decision §C.1: derive once
  (cached), tombstone target, call again → envelope =
  `regression_outcome.kind == "unavailable", reason == "run-tombstoned"`
  even though the cache file still exists on disk.

### `tests/unit/cli/test_regression_latest.py` (NEW; ~5 cases)

- Happy: store with 2+ live runs on the same target → envelope =
  `fact-set`.
- Empty store: → envelope = `unavailable, reason == "no-comparable-baseline",
  detail == "no-runs"`.
- Single run on target: → `unavailable, reason ==
  "no-comparable-baseline", detail == <target_expression>` (per the
  gotcha pinned in `derive_latest_regression`'s test, the detail is the
  target expression, NOT `"no-runs"`).
- Latest run tombstoned, prior live runs exist on different target: the
  "active target" is resolved from the latest LIVE run per
  `derive_latest_regression`'s contract — verify the envelope reflects
  the live-anchor target's pair, not the tombstoned-anchor's.
- Engine mismatch in the latest-two: pytest run followed by jest run on
  the same target_expression → `unavailable, reason == "engine-mismatch"`.

### `tests/unit/cli/test_compare.py` (NEW; ~6 cases)

- Both sides have coverage: envelope carries both
  `regression_outcome.kind == "fact-set"` AND `coverage_delta.kind ==
  "delta"`.
- Only baseline has coverage: `regression_outcome.kind == "fact-set"`
  AND `coverage_delta.kind == "unavailable", reason ==
  "missing-derived-facts"`.
- Neither has coverage: same as above (coverage unavailable).
- Tombstoned target: `regression_outcome.kind == "unavailable", reason ==
  "run-tombstoned"`; `coverage_delta` should also reflect the propagated
  `CoverageUnavailable` per `compare_coverage_facts`'s existing behavior.
- Engine mismatch: regression_outcome = engine-mismatch; verify the
  envelope still carries a coverage_delta block (whatever
  `compare_coverage_facts` returns for that pair — likely also
  unavailable on different engines).

### `tests/unit/orchestration/test_inspect_regression.py` (NEW; ~8 cases)

- Inspected run is the latest of two on a target → `regression_outcome.kind
  == "fact-set"`, `target_run_reference.run_id == <inspected_id>`,
  `baseline_run_reference.run_id == <prior_id>`.
- Inspected run is an OLD run (not the latest) on a target with 3 runs:
  → the section shows the comparison vs the run IMMEDIATELY before this
  one, NOT vs the global latest pair. Pin the baseline_run_id explicitly.
- Only run on its target → `unavailable, reason ==
  "no-comparable-baseline"`, `target_run_reference` carries the
  inspected run's reference, `baseline_run_reference` is null.
- Tombstoned inspected run with live prior on same target →
  `unavailable, reason == "run-tombstoned"` (the engine fails hard per
  §C.1 — the inspected run reaches `compare_runs` and `compare_runs`
  rejects).
- Live inspected run with tombstoned-only priors →
  `unavailable, reason == "no-comparable-baseline"` (the
  `find_runs_for_target(include_tombstoned=False)` filter drops them
  upstream).
- Sibling runs exist for DIFFERENT targets only →
  `unavailable, reason == "no-comparable-baseline"` (the
  target_expression filter excludes them).
- Engine mismatch between inspected and the most-recent-prior → engine-
  mismatch propagated from `compare_runs`.
- `sub_reports["regression"]` flips correctly across the
  available/unavailable cases (pin at least 2 cases for this assertion
  specifically).

### `tests/integration/cli/test_regression_e2e.py` (NEW; ~3 cases)

Invoke `novetest` as a real subprocess against a tmp Project Store seeded
with two real `RunRecord`s via `store_run_evidence`. Pattern: mirror
the existing `tests/integration/cli/` Coverage tests.

- `novetest regression compare <a> <b>` → exit 0, JSON envelope on
  stdout, `regression_outcome.kind == "fact-set"`.
- `novetest regression latest` → exit 0, envelope same shape.
- `novetest compare <a> <b>` → exit 0, both blocks present in `data`.

### `tests/unit/orchestration/test_inspect.py` updates (if it exists)

If the file already exists and currently asserts
`sub_reports["regression"] == "unavailable"` for a happy case, that
assertion needs updating now that the section can flip. Touch lightly —
add the new field assertions only where the existing tests construct an
`InspectView` directly.

---

## Coding-guideline reminder (from `CLAUDE.md`)

Before editing any source file, invoke the
`andrej-karpathy-skills:karpathy-guidelines` skill via the Skill tool.
1. Think Before Coding · 2. Simplicity First · 3. Surgical Changes ·
4. Goal-Driven Execution. The whole point of "pure projection slice" is
that no creativity in the engine layer is needed — preserve that
discipline at the CLI layer too. If a Cyclopts oddity forces creativity
(e.g. sub-app registration quirk), document it inline.

---

## DoD bullets this slice fully satisfies

In `design/implementation-plan/delivery-phasing.md` lines 156–158
(verbatim):

- `[156]` `novetest regression latest` resolves the latest pair for the
  resolved Test Target and returns Regression Facts (with Coverage
  changes when available).
- `[157]` `novetest compare` returns the composed Regression + Coverage
  delta.
- `[158]` `inspect` populates Regression section using the resolved
  baseline.

Include all three in your handoff's "DoD bullets believed closed" list.
PM ticks them at cleanup time (only PM can edit `delivery-phasing.md`).

---

## Handoff requirements (per your charter)

1. Append a new `WORKLOG.md` entry following the format documented at the
   top of that file. Include: src files touched, exact pytest count
   (was 442+3 → is X+3), mypy delta, a 1-line summary of the new
   `regression_outcome` shape draft (so PM can lift it directly into the
   freeze decision), and any gotchas you encountered.
2. Write `agent-comms/handoffs/orchestration-team-2026-05-27-regression-cli.md`
   with the standard "DoD bullets believed closed" list (the three
   above) and any **envelope-shape divergences** you had to make from
   §Envelope shapes above (e.g. attribute name on
   `RegressionUnavailable` differs from the draft) — PM needs these to
   write the freeze decision faithfully.
3. Run `python3 tools/regen_comms_index.py`.
4. Stage `WORKLOG.md`, the new `agent-comms/` files, and `INDEX.md`
   alongside source.
5. The hook will block your commit if `WORKLOG.md` is not staged with
   `src/` or `tests/` changes — that is expected, not a bug.

---

## Out-of-band questions

If during implementation you find:
- An ambiguity in the Regression engine's contract that the existing
  test suite does NOT resolve → write
  `agent-comms/questions/orchestration-team-2026-05-27-<slug>.md` for PM
  to route. Do NOT modify `src/novetest/regression/**`.
- The `_resolve_run_reference` helper's behavior doesn't fit
  `regression compare` (e.g. you want to allow a typo'd run_id to fall
  through to `REASON_RUN_NOT_FOUND` at the engine instead of
  `EXIT_USAGE` at the CLI) → ask before changing. The brief assumes the
  existing helper is reused as-is.
- Cyclopts requires a subcommand naming workaround (e.g.
  `regression compare` collides with the import name) → document inline,
  reference the existing precedent (`def run_cmd` registered as
  `name="run"` in `cli/app.py`).

Everything else: implement per this brief, ship, hand off.

---

## What happens after your handoff

1. Main Branch team merges your worktree, writes verification, **pushes**
   (the push-omission pattern from the last two cycles is being watched
   — if Main Branch forgets again, PM pushes as courier and escalates to
   CEO).
2. Manual Test re-engages (no `status: record-only` this time — CLI
   surface change requires exploratory field-test):
   - Exercise all 4 verbs against a real Project Store.
   - Probe each `REASON_*` propagation path.
   - Validate the `compare` envelope's combined shape.
   - Report any UX friction in findings.
3. PM writes a `decisions/2026-05-XX-regression-outcome-envelope-shape.md`
   pinning the `regression_outcome` shape (mirrors
   `2026-05-16-coverage-outcome-envelope-shape.md`), gets CEO approval,
   commits.
4. PM does cycle cleanup: tick DoD bullets `[156] [157] [158]`, write
   the history entry, delete the 4 transient files, regen INDEX.
