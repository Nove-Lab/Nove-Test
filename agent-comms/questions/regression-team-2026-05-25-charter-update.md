---
from: novetest-regression-team
to: novetest-pm-team
type: question
status: pending
created: 2026-05-25
slug: charter-update
related:
  - .claude/agents/novetest-regression-team.md
  - design/interace-contract/regression.md
  - design/workflows/regression.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md
  - agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/tasks/memory-team-2026-05-25-find-runs-for-target.md
---

# Question: Promote the placeholder Regression charter into concrete conventions + reporting + risk register

## Question

Phase 3 entry — Regression team is being woken up. The charter
(`.claude/agents/novetest-regression-team.md`) explicitly says "flesh out
the conventions / contracts when the team is woken up." This question
proposes the concrete additions, derived from the binding contracts
(`regression.md`, `regression.md` workflow), Coverage's frozen precedents,
and the activation task's checklist. PM owns charter edits; please either
(a) write the charter additions directly from sections A and B below, or
(b) route the schema sketch (A.1 + A.3 + A.4 + A.5) through a
`decisions/2026-05-XX-regression-facts-json-layout.md` mirroring Coverage's
`2026-05-15-coverage-facts-json-layout.md` shape, so the contract is
permanent before the first implementation slice ships.

## Context

Pre-flight reading completed (all 8 documents named by the task plus
companion material):

- Contract docs: `design/interace-contract/regression.md`,
  `design/workflows/regression.md`,
  `design/interace-contract/coverage.md`,
  `design/workflows/coverage.md`,
  `design/interace-contract/memory.md`,
  `design/workflows/memory.md`.
- Requirements: `design/requirements-analysis/requirements-specification/groups/regression.md`
  (REQ-REG-001..004, NFR-REG-001..002) +
  `design/requirements-analysis/domain-model.md` (Regression Fact entity:
  `factId, baseRunId, comparedRunId, transitionType`; "comparable" = "share
  a resolved test target and enough normalized evidence").
- Precedent code: `src/novetest/models/coverage_fact_set.py`,
  `src/novetest/coverage/compare.py` (`CoverageDelta` + `FileCoverageDelta`),
  `src/novetest/coverage/results.py` (`REASON_*` enum + `CoverageUnavailable`),
  `src/novetest/models/{memory_entry,run_record,test_result,run_reference}.py`.
- Decisions: facts-layout, outcome-envelope, delta-envelope,
  supported-engine-matrix.
- Companion: `tasks/memory-team-2026-05-25-find-runs-for-target.md` (pins
  the upstream Memory primitive that `resolve_latest_baseline` will call).
- Recent cycle history (`history/2026-05-21-*.md`).

The charter currently pins one durable convention — directory layout
`<store>/regression/pairs/run_<a>__run_<b>/regression_facts.json` — and
defers the rest. The proposals below mirror Coverage's frozen patterns
(schema-versioned, frozen dataclasses with slots, hand-rolled
`to_dict`/`from_dict`, explicit unavailable outcomes, file-only
persistence) unless a Regression-specific need justifies divergence.

---

## A. Conventions (proposed additions to the charter "Conventions" section)

### A.1 — `regression_facts.json` directory layout and lookup

**Confirm the charter's stub.** Persisted path:

```
<store>/regression/pairs/run_<baseline_run_id>__run_<target_run_id>/regression_facts.json
```

- The directory name embeds **both** Run IDs joined by a literal `__`
  (double-underscore). Mirrors Coverage's `<store>/coverage/facts/run_<id>/`
  shape (single-run-keyed) at one level deeper (pair-keyed).
- The pair key uses the **literal argument order** passed to
  `compare_runs(baseline, target)`. `compare_runs(rA, rB)` and
  `compare_runs(rB, rA)` are **distinct operations** with distinct
  persisted files — transition direction is order-significant (pass→fail
  vs fail→pass). Same precedent as `coverage diff <a> <b>` (the
  `CoverageDelta` is order-significant per
  `decisions/2026-05-16-coverage-delta-envelope-shape.md`).
- `get_regression_facts(rA, rB)` resolves by literal argument order and
  returns `RegressionUnavailable(reason="missing-derived-facts")` when the
  pair directory does not exist.

### A.2 — Baseline-pair identity (canonical ordering)

**Pin:** in any function signature taking two Run References positionally
(`compare_runs(baseline, target)`, `get_regression_facts(baseline, target)`,
`check_regression_availability` callers downstream), the **first argument
is the older / reference run, the second is the newer / candidate run**.
Identical to Coverage's `(baseline_run_reference, target_run_reference)`
convention in `compare_coverage_facts`.

`resolve_latest_baseline(test_target)` returns the canonical pair as
`(previous, current)` — i.e. `(baseline, target)` — matching this
ordering. The contract doc currently phrases its output as "Pair of Run
References (current, previous)"; recommend PM clarifies this docstring to
the `(baseline, target)` order to remove the inversion ambiguity (see
section C, open question #4).

### A.3 — Regression Facts dataclass tree

Mirror `CoverageFactSet`'s shape: a top-level entity that aggregates
per-element records, a summary block, embedded `RunReference`s for
NFR-REG-001 traceability, schema-versioned with hand-rolled round-trip.

```python
# src/novetest/models/regression_fact_set.py (proposed)

SCHEMA_VERSION: int = 1

TRANSITION_CATEGORIES: frozenset[str] = frozenset({
    "regressed",        # B=pass-like, T=fail-like
    "fixed",            # B=fail-like, T=pass-like
    "still_failing",    # B=fail-like, T=fail-like
    "still_passing",    # B=pass-like, T=pass-like
    "still_skipped",    # B=skip-like, T=skip-like
    "newly_skipped",    # B=active,    T=skip-like
    "newly_active",     # B=skip-like, T=active
    "added",            # B=missing,   T=present (any outcome)
    "removed",          # B=present,   T=missing (any outcome)
})

@dataclass(slots=True, frozen=True)
class TestTransition:
    node_id: str
    category: str                          # one of TRANSITION_CATEGORIES
    baseline_outcome: str | None           # None when category == "added"
    target_outcome: str | None             # None when category == "removed"
    baseline_failure_reference: str | None # opaque handle into Memory
    target_failure_reference: str | None
    baseline_duration_ms: int | None
    target_duration_ms: int | None

@dataclass(slots=True, frozen=True)
class RegressionSummary:
    regressed: int
    fixed: int
    still_failing: int
    still_passing: int
    still_skipped: int
    newly_skipped: int
    newly_active: int
    added: int
    removed: int
    # convenience aggregates the CLI / inspect surface will want
    total_baseline_tests: int
    total_target_tests: int

@dataclass(slots=True, frozen=True)
class OutputDiffRecord:
    # Per A.5 — hash + path, not full text. Empty when both sides identical.
    baseline_stdout_sha256: str | None
    target_stdout_sha256: str | None
    baseline_stderr_sha256: str | None
    target_stderr_sha256: str | None
    stdout_identical: bool
    stderr_identical: bool
    baseline_stdout_path: str | None   # Project-Store-relative
    target_stdout_path: str | None
    baseline_stderr_path: str | None
    target_stderr_path: str | None

@dataclass(slots=True, frozen=True)
class RegressionFactSet:
    baseline_run_reference: RunReference
    target_run_reference: RunReference
    baseline_engine_name: str
    target_engine_name: str
    baseline_engine_version: str | None
    target_engine_version: str | None
    derived_at: int                              # epoch_ms
    summary: RegressionSummary
    test_transitions: tuple[TestTransition, ...]
    output_diff: OutputDiffRecord | None         # None when neither side has stdout/stderr artifacts
    coverage_change: dict[str, Any] | None       # CoverageDelta.to_dict() when both sides have facts; else None
    warnings: tuple[str, ...] = ()               # e.g. "engine-version-drift"
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
```

Notes:

- `test_transitions` is sorted by `node_id` (deterministic for NFR-REG-001).
  Read-side does not reorder; write-side does.
- `coverage_change` embeds `CoverageDelta.to_dict()` verbatim rather than
  re-modelling it. Read-side calls `CoverageDelta.from_dict()` which
  validates its own `schema_version`. A future Coverage v2 bump requires a
  Regression-side migration plan (recorded in section C, risk #6).
- `OutputDiffRecord.*_path` fields are **Project-Store-relative** (mirroring
  `RunRecord.artifact_paths` convention) so the file is portable.
- `warnings` is a tuple of well-known short codes (e.g.
  `"engine-version-drift"`, `"target-type-drift"`) — the read-side may
  surface them in `inspect` or `regression compare` envelopes. Not a hard
  unavailability.
- `metadata` is open-ended and explicitly **NOT part of the wire
  contract** (Coverage's pattern, constraint #7 of the facts-layout
  decision).

### A.4 — Outcome transition taxonomy (closed enum) — pinned

The 9 categories in `TRANSITION_CATEGORIES` above. Categorization rules
to apply when building a `TestTransition`:

- **pass-like** = `passed`, `xpassed`
- **fail-like** = `failed`, `errored`
- **skip-like** = `skipped`, `xfailed`

The native engine's raw `outcome` string is preserved in
`baseline_outcome` / `target_outcome` (per `TestResult.outcome`'s
intentional non-enum-locked design at v1 — see `test_result.py:22-26`),
so consumers that need the raw string still have it. The 9-category
bucket is for grep / summary / Localization input. Unknown outcomes
collapse defensively to the nearest bucket via the table above; an
outcome string outside the union of those six raises a documented
parse-time warning (mirrors the supported-engine-matrix decision's
defensive-parsing principle).

### A.5 — Native-output diff strategy

**Hash + path reference, NOT full text.** Justification:

- `regression_facts.json` is read by `inspect`, `regression compare`,
  Localization (Phase 4), and a future `compare` envelope. A 10,000-test
  pytest run can carry multi-MB stdout/stderr; embedding a unified diff
  pushes the JSON into a size class that breaks NFR-REG-002's 5s budget
  for re-parse.
- Determinism (NFR-REG-001) is preserved by SHA-256 of the captured
  artifact bytes — independent of locale / line endings as long as
  capture is byte-stable (we use raw-bytes capture via
  `utils/asyncio_subprocess.run_subprocess`, so it is).
- Per-test failure context is already on `TestResult.failure_reference`
  (an opaque handle into the stored Native Result) — that is the
  load-bearing signal for Localization, not aggregate stdout.
- A future slice that introduces a CLI verb wanting a textual diff
  (`novetest regression compare --include-output-diff`) can compute it
  on demand from the artifact paths in `OutputDiffRecord.*_path`.

When both sides' artifacts are missing (e.g. very old runs whose
artifacts were pruned), `output_diff` is `None` — same null-pattern
Coverage uses for missing coverage facts.

### A.6 — Persistence write-time (lazy on first compare)

**Mirror Coverage: lazy.** `derive_regression_facts(baseline, target)` is
called on-read by `compare_runs` (and transitively by `regression compare`
/ `regression latest` / `inspect` when it composes the Regression
section). It writes `<store>/regression/pairs/run_<a>__run_<b>/regression_facts.json`
on success; subsequent calls hit the cache via `get_regression_facts`.

`novetest run` does **NOT** eagerly derive Regression facts. Reasoning:

- Eager derivation forces every Run to scan Run History for the most
  recent comparable baseline — extra I/O per run, especially as history
  grows.
- Most runs (CI-driven, watch-mode-driven) never have their Regression
  facts consumed; the eager work is wasted.
- Coverage's lazy precedent has held up across Phases 2 + 2.5 without a
  perceived UX cost.

A future "warm cache" task can add an eager mode behind a flag if a
specific workflow demands it.

### A.7 — Unavailable outcome (explicit, NOT exception)

Mirror Coverage's `CoverageUnavailable` shape. Propose:

```python
# src/novetest/regression/results.py (proposed)

REASON_RUN_NOT_FOUND: Final[str] = "run-not-found"
REASON_RUN_TOMBSTONED: Final[str] = "run-tombstoned"
REASON_NO_COMPARABLE_BASELINE: Final[str] = "no-comparable-baseline"
REASON_MISSING_DERIVED_FACTS: Final[str] = "missing-derived-facts"
REASON_ENGINE_MISMATCH: Final[str] = "engine-mismatch"
REASON_TARGET_MISMATCH: Final[str] = "target-mismatch"

@dataclass(slots=True, frozen=True)
class RegressionUnavailable:
    reason: str
    detail: str | None = None
    baseline_run_reference: RunReference | None = None
    target_run_reference: RunReference | None = None
```

Discriminator pattern (`isinstance(result, RegressionUnavailable)`) is
identical to Coverage's. The `regression_outcome` envelope shape this
implies will likely need its own `decisions/` entry (companion to
`coverage-outcome-envelope-shape`) when the first CLI surface ships;
flagged in section C, risk #2.

### A.8 — Schema-versioned wire format

Pin `schema_version: 1` on `RegressionFactSet`, `TestTransition`,
`RegressionSummary`, `OutputDiffRecord`. Same construction-time validation
+ read-side tolerance pattern as `CoverageFactSet`. Read-side defaults:
`warnings` defaults to `()`, `metadata` defaults to `{}`,
`output_diff` and `coverage_change` may be `None` on read.

### A.9 — Memory availability flag wiring

The `MemoryEntry.has_regression_facts: bool` flag already exists (see
`memory_entry.py:42`). It must flip to `True` exactly when **any**
`regression_facts.json` referencing this run as either baseline OR target
is present on disk. Concrete implementation Memory's `_availability_flags`
probe will need to do: scan `<store>/regression/pairs/` for any directory
name containing the run's ID. PM may want to route this through a
Memory-team task in the same cycle as Regression's first real
implementation slice, so the flag's flip-time is wired before any
consumer relies on it. (Not a question for Regression team to answer
unilaterally — flagging in section C, risk #5.)

---

## B. Reporting (proposed additions to the charter "Reporting back" section)

Coverage's handoff format (per `agent-comms/README.md` standard sections
and the most recent cycle handoffs) covers everything Regression slices
will need. No Regression-specific reporting additions are needed. The
charter's current line ("Standard handoff sections (see
`agent-comms/README.md`)") stays as-is. The README's `handoffs/` section
already lists: Worktree, Files written, Verification result, Worklog
entry text, DoD bullets believed closed, Open items.

The only Regression-specific reporting hint worth pinning into the
charter is:

> When a slice produces a new `regression_facts.json` schema field or a
> new `RegressionUnavailable` reason, the handoff MUST flag it as a
> contract change that needs a `decisions/` follow-up (mirroring the
> Coverage team's discipline around `REASON_*` and the on-disk schema).

That single sentence is the only divergence from the boilerplate; the
rest of the reporting section can stay unchanged.

---

## C. Open questions / risks (need PM or CEO decision before implementation lands)

### C.1 — Tombstoned-run-as-baseline (fail-soft vs fail-hard)

A user deletes the baseline run (creates a tombstone). Later, the user
or `regression latest` requests `compare_runs(tombstoned_baseline,
live_target)`. Three options:

- **(a) Fail-hard** — return `RegressionUnavailable(reason="run-tombstoned")`.
  Tombstone semantics say the active record is gone; treating it as
  fresh signal is misleading.
- **(b) Fail-soft via cached facts** — if `regression_facts.json`
  already exists on disk for the pair (derived before the tombstone),
  return it. Otherwise return `RegressionUnavailable`.
- **(c) Always fail-hard regardless of cache** — same as (a) plus
  delete any pair directory referencing the tombstoned run.

**Recommendation: (a).** Tombstones are a deletion gesture; downstream
consumers should respect them. Pre-existing facts on disk become stale
the moment the source record is tombstoned; surfacing them as fresh would
violate the principle. Option (c)'s active deletion is too aggressive
for v1 — leave the pair directory for audit but do not return it.

### C.2 — Envelope shapes for `regression compare` / `regression latest` / `inspect` Regression section

Phase 3 will introduce CLI verbs that need wire-format envelope shapes
parallel to:

- `coverage_outcome` (`decisions/2026-05-16-coverage-outcome-envelope-shape.md`)
- `coverage_delta` (`decisions/2026-05-16-coverage-delta-envelope-shape.md`)

Likely names: `regression_outcome` (single-run "is there a baseline?"
section in `inspect`) and `regression_delta` / `regression_pair` (the
two-run comparison body).

**Question:** does PM want the shape proposed in this question now (so a
companion `decisions/2026-05-XX-regression-envelope-shapes.md` lands
alongside the implementation slice), or should the first implementation
slice ship the shape uncodified and PM freeze it on Manual Test's
approval (the pattern that worked for the original
`coverage_outcome` decision)?

**Recommendation:** ship uncodified in the first slice, freeze after
Manual Test approval. Coverage's two-step pattern (ship → field-test →
freeze) is good precedent and avoids over-design before any consumer
has touched it.

### C.3 — Engine-version drift across compared runs

A user upgrades pytest from 8.1 → 8.2 between baseline and target.
Memory stores `engine_version` per `RunRecord`. Should `compare_runs`:

- **(a) Compare anyway**, recording both versions in the fact set's
  `metadata` and surfacing a `"engine-version-drift"` warning in
  `RegressionFactSet.warnings`.
- **(b) Require strict version equivalence** — return
  `RegressionUnavailable(reason="engine-version-drift")`.

**Recommendation: (a).** "Comparable" per the domain model assumption is
"share a resolved test target and enough normalized evidence". Engine
patch / minor bumps overwhelmingly preserve test-result shape (per the
supported-engine-matrix decision); blocking comparison on version drift
breaks the realistic "I bumped pytest" workflow. Major-version bumps
remain possible — surface the drift as a warning, not a refusal.

### C.4 — `resolve_latest_baseline` return-tuple ordering ambiguity

The interface contract phrases its output as **"Pair of Run References
(current, previous)"**. The Regression workflow then calls
`regression/compare_runs(run_reference_1, run_reference_2)` — which, per
section A.2, treats arg1 as **baseline (previous)** and arg2 as **target
(current)**. The natural read of the contract sentence ("current,
previous") would put `current` in arg1 and `previous` in arg2, inverting
the intended direction (transitions would all be reported backwards).

**Recommendation:** PM either (a) edits the contract sentence in
`design/interace-contract/regression.md:28` to read "Pair of Run
References (previous, current)" — same order as `(baseline, target)` —
or (b) names the tuple explicitly: `(baseline_run_reference,
target_run_reference)`. Option (b) preferred — eliminates the ambiguity
forever.

This is a contract-doc clarification, not a behavioral change. Likely
small enough to be a PM-side edit + a one-line note in a future cycle's
history.

### C.5 — `MemoryEntry.has_regression_facts` flip-time wiring

Per section A.9 — the existing `MemoryEntry.has_regression_facts: bool`
must flip to `True` when a `regression_facts.json` referencing this run
exists. Memory's current `_availability_flags` probe (see Memory team's
recent work) checks `<store>/coverage/facts/run_<id>/coverage_facts.json`
for the Coverage flag. Regression needs an analogous probe but with
**directory scan**, not single-path probe (the run ID appears in either
`run_<A>__run_<B>` or `run_<B>__run_<A>` positions).

**Question:** is the Memory team the owner of this probe change, or is
Regression expected to expose a helper (`regression.has_facts_for_run`)
that Memory calls? Coverage's precedent is the former (Memory owns the
probe, Coverage owns the file shape).

**Recommendation:** PM dispatches a Memory-team task in the same cycle
as Regression's first implementation slice — narrow scope: scan
`<store>/regression/pairs/` for any directory containing
`run_<run_id>` substring. The task can ship behind Regression's slice so
the test surface (existing `_availability_flags` tests) is updated in
lockstep.

### C.6 — Coverage schema evolution coupling

`RegressionFactSet.coverage_change` embeds `CoverageDelta.to_dict()`
verbatim. This couples the Regression on-disk schema to the Coverage
on-disk schema: a Coverage v2 bump (Coverage Team owns `CoverageDelta`
per `decisions/2026-05-15-coverage-facts-json-layout.md`'s "operation-result
types are owned by Coverage Team and may evolve") could invalidate
previously-stored `regression_facts.json` files.

**Recommendation:** at Coverage v2 time, treat any existing
`regression_facts.json` whose embedded `coverage_change.schema_version`
is below current as **stale on read** — return
`RegressionUnavailable(reason="missing-derived-facts")` and let the next
`compare_runs` re-derive. This is the same posture Coverage uses for its
own schema bumps (read raises `ValueError`, caller can re-derive).

The decision PM needs to confirm: this coupling is acceptable. Alternative
would be to store a thinner Coverage delta projection inside the fact set
(decoupled, but duplicated logic). Recommendation prefers the embedded
approach for simplicity until a real schema bump forces the question.

### C.7 — Localization (Phase 4) input shape

`design/interace-contract/regression.md` notes: "Localization consumes
Regression Facts via `get_regression_facts` to focus on changed behavior
when available." Localization's first slice will read
`RegressionFactSet.test_transitions` and filter for the
`{"regressed", "still_failing", "new_failure"}` subset (the "suspect"
universe SBFL needs to score).

**Risk:** Localization team is currently dormant. The proposed
`TestTransition` shape (section A.3) exposes `node_id`, `category`,
`baseline_outcome`, `target_outcome`, both `failure_reference` handles,
and durations. This is everything an SBFL formula needs at the boundary
(failure node IDs + the corresponding test universe).

**Recommendation:** ship the shape proposed here; if Localization
activation in Phase 4 surfaces a missing field, add it as a non-breaking
optional field on the existing schema (no version bump per the
forward-compatible-extension rule mirroring Coverage's). No question
blocking Regression's Phase 3 work today; flagging for cross-team
visibility.

---

## Blocking?

**No.** Regression team is not blocked from starting Phase 3
implementation by this question. The proposals above are the team's
default direction; PM can:

- Lift sections A and B verbatim into the charter (low ceremony), and
- Route sections C.1, C.4, C.5, and (optionally) C.2 / C.3 / C.6 / C.7
  through `decisions/` entries or follow-up tasks at PM's discretion.

The team will treat the recommendations in section C as the working
assumptions until PM directs otherwise. The first Phase 3 implementation
slice (presumably `compare_runs` + facts persistence, dispatched next
cycle per the activation task's "What happens next" note) can proceed
on this basis.

---

## Pre-flight verification (per task `Verification` section)

- [x] All 8 documents in the task's pre-flight reading list were read in
      full, plus companion docs (requirements-specification/regression.md,
      domain-model.md, supported-engine-matrix decision, both Coverage
      envelope decisions, both recent cycle histories).
- [x] No `src/`, `tests/`, or `design/interace-contract/regression.md` /
      `design/workflows/regression.md` files were modified.
- [x] `.claude/agents/novetest-regression-team.md` was read but NOT
      edited (PM territory).
- [x] This question file contains sections A, B, C as required.
- [x] Recommendations are concrete enough that PM can act on them
      directly — either by editing the charter, opening a `decisions/`
      entry, or dispatching a follow-up task.
