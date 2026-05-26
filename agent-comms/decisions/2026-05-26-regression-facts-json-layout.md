---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-26
slug: regression-facts-json-layout
related:
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md
  - agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - design/interace-contract/regression.md
  - design/workflows/regression.md
  - design/requirements-analysis/requirements-specification/groups/regression.md
---

# Decision: `regression_facts.json` v1 on-disk layout + Regression contract resolutions (frozen)

CEO-approved on 2026-05-26 as part of Phase 3 entry. Promotes the
Regression team's `questions/regression-team-2026-05-25-charter-update.md`
sections A.1 / A.3 / A.4 / A.5 / A.7 / A.8 to a binding contract so the
first implementation slice (and Memory's companion availability-flag
slice in the same cycle) can land against fixed wire format and
fixed unavailability semantics — mirroring how
`decisions/2026-05-15-coverage-facts-json-layout.md` pinned Coverage
before any cross-engine consumer touched it.

Companion decisions (deliberately out of scope here):
`regression_outcome` and `regression_delta` envelope shapes will land
under their own decisions **after** the first CLI slice ships and
Manual Test fields the shape — same ship → field-test → freeze cadence
that worked for the two Coverage envelope decisions.

---

## Decision

### 1. On-disk path

`regression_facts.json` is persisted at:

```
<store>/regression/pairs/run_<baseline_run_id>__run_<target_run_id>/regression_facts.json
```

- The directory name embeds **both** Run IDs joined by a literal `__`
  (double-underscore). One directory level deeper than Coverage's
  `<store>/coverage/facts/run_<id>/` (pair-keyed rather than single-run-keyed).
- The pair key uses the **literal argument order** passed to
  `compare_runs(baseline, target)`. `compare_runs(rA, rB)` and
  `compare_runs(rB, rA)` are **distinct operations** with distinct persisted
  files — transition direction is order-significant (pass→fail vs fail→pass).
  Same precedent as `coverage diff <a> <b>`.
- `get_regression_facts(baseline, target)` resolves by literal argument
  order and returns
  `RegressionUnavailable(reason=REASON_MISSING_DERIVED_FACTS)` when the
  pair directory does not exist.
- The path itself is **load-bearing** — Memory's `_availability_flags`
  probe scans `<store>/regression/pairs/` for any directory whose name
  contains `run_<run_id>` (either baseline or target position) to flip
  `MemoryEntry.has_regression_facts`. Renaming this layout requires a
  coordinated change in Memory + Regression + a `schema_version` bump.

### 2. Argument order convention

In **every** function signature taking two Run References positionally —
`compare_runs(baseline, target)`, `get_regression_facts(baseline, target)`,
`derive_regression_facts(baseline, target)`, and any read-side helper —
**arg1 = baseline (older / reference), arg2 = target (newer / candidate)**.

Identical to Coverage's `(baseline_run_reference, target_run_reference)`
convention in `compare_coverage_facts`.

`resolve_latest_baseline(test_target)` returns the canonical pair as
`(baseline_run_reference, target_run_reference)` — i.e. `(older, newer)` —
matching this order.

**Contract-doc clarification:** `design/interace-contract/regression.md:28`
currently reads "Pair of Run References (current, previous)" for
`resolve_latest_baseline`. This is ambiguous against the
`compare_runs(baseline, target)` order above. The first Regression
implementation slice (task
`tasks/regression-team-2026-05-26-compare-runs-impl.md`) will edit that
line to read **"Pair of Run References (baseline_run_reference,
target_run_reference)"** — explicit, eliminating the inversion ambiguity
forever. (Regression team's territory to edit; PM cannot touch
`design/interace-contract/regression.md` directly.)

### 3. Dataclass tree (frozen)

The persisted shape of `regression_facts.json` is defined by these
frozen dataclasses (target module: `src/novetest/models/regression_fact_set.py`):

```python
SCHEMA_VERSION: int = 1

# Closed enum, validated at TestTransition construction.
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
    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION
    __test__: ClassVar[bool] = False     # pytest collection guard (mirrors TestResult)

    node_id: str
    category: str                         # one of TRANSITION_CATEGORIES
    baseline_outcome: str | None          # None when category == "added"
    target_outcome: str | None            # None when category == "removed"
    baseline_failure_reference: str | None
    target_failure_reference: str | None
    baseline_duration_ms: int | None
    target_duration_ms: int | None
    schema_version: int = SCHEMA_VERSION

@dataclass(slots=True, frozen=True)
class RegressionSummary:
    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    regressed: int
    fixed: int
    still_failing: int
    still_passing: int
    still_skipped: int
    newly_skipped: int
    newly_active: int
    added: int
    removed: int
    total_baseline_tests: int             # convenience aggregate (in-both + removed)
    total_target_tests: int               # convenience aggregate (in-both + added)

@dataclass(slots=True, frozen=True)
class OutputDiffRecord:
    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    baseline_stdout_sha256: str | None
    target_stdout_sha256: str | None
    baseline_stderr_sha256: str | None
    target_stderr_sha256: str | None
    stdout_identical: bool
    stderr_identical: bool
    baseline_stdout_path: str | None      # Project-Store-relative
    target_stdout_path: str | None
    baseline_stderr_path: str | None
    target_stderr_path: str | None

@dataclass(slots=True, frozen=True)
class RegressionFactSet:
    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    baseline_run_reference: RunReference
    target_run_reference: RunReference
    baseline_engine_name: str
    target_engine_name: str
    baseline_engine_version: str | None
    target_engine_version: str | None
    derived_at: int                       # epoch_ms
    summary: RegressionSummary
    test_transitions: tuple[TestTransition, ...]
    output_diff: OutputDiffRecord | None  # None when neither side has stdout/stderr
    coverage_change: dict[str, Any] | None # CoverageDelta.to_dict() when both have facts
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
```

### 4. Persisted JSON shape

```jsonc
{
  "schema_version": 1,
  "baseline_run_reference": {
    "schema_version": 1,
    "run_id": "<26-char ULID>",
    "created_at": <epoch_ms>
  },
  "target_run_reference":   { /* same shape */ },
  "baseline_engine_name": "pytest",
  "target_engine_name":   "pytest",
  "baseline_engine_version": "8.2.0",        // may be null
  "target_engine_version":   "8.2.0",        // may be null
  "derived_at": <epoch_ms>,
  "summary": {
    "regressed": 0, "fixed": 1, "still_failing": 0, "still_passing": 12,
    "still_skipped": 0, "newly_skipped": 0, "newly_active": 0,
    "added": 1, "removed": 0,
    "total_baseline_tests": 13, "total_target_tests": 14
  },
  "test_transitions": [
    {
      "schema_version": 1,
      "node_id": "tests/test_x.py::test_a",
      "category": "fixed",
      "baseline_outcome": "failed",
      "target_outcome": "passed",
      "baseline_failure_reference": "blobs/sha256/abc...",
      "target_failure_reference": null,
      "baseline_duration_ms": 12,
      "target_duration_ms": 9
    }
    // ...
  ],
  "output_diff": {
    "baseline_stdout_sha256": "abc...",
    "target_stdout_sha256":   "def...",
    "baseline_stderr_sha256": null,
    "target_stderr_sha256":   null,
    "stdout_identical": false,
    "stderr_identical": true,
    "baseline_stdout_path": "run/artifacts/run_<baseline>/native/stdout.log",
    "target_stdout_path":   "run/artifacts/run_<target>/native/stdout.log",
    "baseline_stderr_path": null,
    "target_stderr_path":   null
  },
  "coverage_change": {
    // CoverageDelta.to_dict() embedded verbatim; null when either side
    // has no coverage_facts.json
    "schema_version": 1,
    "baseline_run_reference": { /* ... */ },
    "target_run_reference":   { /* ... */ }
    /* ... full CoverageDelta payload ... */
  },
  "warnings": [],
  "metadata": {}
}
```

### 5. Binding constraints

1. **`schema_version` is mandatory at every dataclass that has it.**
   `from_dict` MUST raise `ValueError` on mismatch — same posture as
   `CoverageFactSet`, `TestResult`, `MemoryEntry`. Read-side never
   silently downgrades.

2. **`TRANSITION_CATEGORIES` is a closed enum.** Construction with a
   category outside the set is a programmer error (assert at
   `TestTransition.__post_init__` time). Outcome bucketing is:
   - **pass-like** = `passed`, `xpassed`
   - **fail-like** = `failed`, `errored`
   - **skip-like** = `skipped`, `xfailed`

   The native engine's raw `outcome` string is preserved in
   `baseline_outcome` / `target_outcome` (per `TestResult.outcome`'s
   intentional non-enum-locked design at v1 — `test_result.py:22-26`),
   so consumers needing the raw string still have it. The 9-category
   bucket is for grep / summary / Localization input. Outcome strings
   outside the union of those six fall into the closest bucket
   defensively AND emit a one-shot warning into
   `RegressionFactSet.warnings` (well-known code:
   `"unknown-outcome:<engine>:<raw>"`) — mirrors the supported-engine-matrix
   decision's defensive-parsing principle.

3. **`test_transitions` is sorted by `node_id` ascending.** Write-side
   sorts; read-side does not reorder. Determinism is load-bearing
   (NFR-REG-001 — regression results deterministic for the same stored
   evidence state).

4. **Native-output diff = SHA-256 + path reference only, NOT body text.**
   Justification:
   - `regression_facts.json` is read by `inspect`, `regression compare`,
     Localization (Phase 4), `compare`. A 10,000-test pytest run can
     carry multi-MB stdout/stderr; embedding diff text pushes the JSON
     into a size class that breaks NFR-REG-002's 5s re-parse budget.
   - Determinism (NFR-REG-001) is preserved by SHA-256 of the captured
     artifact bytes — independent of locale / line endings as long as
     capture is byte-stable (we use raw-bytes capture via
     `utils/asyncio_subprocess.run_subprocess`, so it is).
   - Per-test failure context is already on
     `TestResult.failure_reference` (an opaque handle into the stored
     Native Result) — the load-bearing signal for Localization, not
     aggregate stdout.
   - A future slice that introduces a CLI verb wanting unified textual
     diff (`novetest regression compare --include-output-diff`) can
     compute it on demand from the artifact paths in
     `OutputDiffRecord.*_path`.

   When both sides' artifacts are missing (e.g. very old runs whose
   artifacts were pruned), `output_diff` is `None` — same null-pattern
   Coverage uses for missing coverage facts.

5. **`OutputDiffRecord.*_path` fields are Project-Store-relative.**
   Same convention as `RunRecord.artifact_paths`. Portable; never
   absolute.

6. **`coverage_change` embeds `CoverageDelta.to_dict()` verbatim or is
   `None`.** Read-side calls `CoverageDelta.from_dict()`, which
   validates its own `schema_version`. See C.6 below for the
   Coverage-coupling rule.

7. **`metadata` is explicitly NOT part of the wire contract.** Mirrors
   constraint #7 of the Coverage facts-layout decision. Consumers MUST
   NOT pattern-match on its keys for behavior. A future change to
   `metadata` does not bump `schema_version`.

8. **`warnings` is a tuple of well-known short codes** (e.g.
   `"engine-version-drift"`, `"target-type-drift"`,
   `"unknown-outcome:<engine>:<raw>"`). The read-side may surface them
   in `inspect` or `regression compare` envelopes. Not a hard
   unavailability — the fact set is still authoritative.

### 6. Persistence write-time = lazy on first compare

**Mirror Coverage: lazy.** `derive_regression_facts(baseline, target)`
is called on-read by `compare_runs` (and transitively by
`regression compare` / `regression latest` / `inspect` when it composes
the Regression section). It writes
`<store>/regression/pairs/run_<a>__run_<b>/regression_facts.json` on
success; subsequent calls hit the cache via `get_regression_facts`.

`novetest run` does **NOT** eagerly derive Regression facts. Reasoning:

- Eager derivation forces every Run to scan Run History for the most
  recent comparable baseline — extra I/O per run, especially as
  history grows.
- Most runs (CI-driven, watch-mode-driven) never have their Regression
  facts consumed; the eager work is wasted.
- Coverage's lazy precedent has held up across Phases 2 + 2.5 without a
  perceived UX cost.

A future "warm cache" task can add an eager mode behind a flag if a
specific workflow demands it.

### 7. Unavailable outcome (explicit return, NOT exception)

Mirror Coverage's `CoverageUnavailable` shape. Target module:
`src/novetest/regression/results.py`:

```python
REASON_RUN_NOT_FOUND: Final[str] = "run-not-found"
REASON_RUN_TOMBSTONED: Final[str] = "run-tombstoned"
REASON_NO_COMPARABLE_BASELINE: Final[str] = "no-comparable-baseline"
REASON_MISSING_DERIVED_FACTS: Final[str] = "missing-derived-facts"
REASON_ENGINE_MISMATCH: Final[str] = "engine-mismatch"
REASON_TARGET_MISMATCH: Final[str] = "target-mismatch"

KNOWN_REASONS: frozenset[str] = frozenset({
    REASON_RUN_NOT_FOUND,
    REASON_RUN_TOMBSTONED,
    REASON_NO_COMPARABLE_BASELINE,
    REASON_MISSING_DERIVED_FACTS,
    REASON_ENGINE_MISMATCH,
    REASON_TARGET_MISMATCH,
})

@dataclass(slots=True, frozen=True)
class RegressionUnavailable:
    reason: str
    detail: str | None = None
    baseline_run_reference: RunReference | None = None
    target_run_reference: RunReference | None = None
```

Discriminator pattern (`isinstance(result, RegressionUnavailable)`) is
identical to Coverage's. Adding a new `REASON_*` requires a follow-up
decision update.

### 8. Read-side tolerance (compatibility seam)

`from_dict` accepts these deviations to keep cross-engine integration
loose while the wire format is young — NOT relaxations of the
write-side contract:

- `warnings` may be omitted on read (defaults to `()`).
- `metadata` may be omitted on read (defaults to `{}`).
- `output_diff` may be `null` on read (defaults to `None`).
- `coverage_change` may be `null` on read (defaults to `None`).
- `baseline_engine_version` / `target_engine_version` may be `null` on
  read (defaults to `None`).
- `baseline_failure_reference` / `target_failure_reference` /
  `baseline_duration_ms` / `target_duration_ms` may be `null` on read.

Any other omitted required field raises `ValueError` at `from_dict`
time.

### 9. Out of scope (intentionally NOT frozen here)

- **`regression_outcome` envelope shape** (`inspect`'s Regression
  section discriminator). Pinned in a follow-up decision after the
  first CLI slice ships and Manual Test fields the shape. Pattern
  mirrors `coverage_outcome` — ship → field-test → freeze.
- **`regression_delta` / `regression_pair` envelope shape**
  (`regression compare` and `compare` orchestration verb). Same
  ship-then-freeze treatment.
- **`RegressionDelta` / `RegressionAvailability`** (operation-result
  types, not persisted) — owned by Regression Team and may evolve
  without a `schema_version` bump (same posture as
  `CoverageDelta` / `CoverageAvailability` per
  `decisions/2026-05-15-coverage-facts-json-layout.md`).
- **Localization (Phase 4) input shape requirements** — `TestTransition`
  exposes enough today (node_id, category, both outcomes, both
  failure_references, durations) for SBFL scoring. If Localization
  activation surfaces a missing field, it lands as a non-breaking
  optional field on the existing schema (no version bump).

---

## C-section resolutions (from `questions/regression-team-2026-05-25-charter-update.md`)

The question raised 7 open items requiring PM/CEO decisions before the
first Regression implementation slice ships. Resolutions:

### C.1 — Tombstoned baseline = **fail-hard**

`compare_runs(tombstoned_baseline, live_target)` returns
`RegressionUnavailable(reason=REASON_RUN_TOMBSTONED,
baseline_run_reference=..., target_run_reference=...)` regardless of
whether `regression_facts.json` already exists on disk for that pair.

Rationale: tombstones are a deletion gesture. Surfacing pre-existing
facts derived from a now-tombstoned source would treat stale data as
fresh signal and violate the deletion principle. Active deletion of
the cached pair directory (the question's option (c)) is too
aggressive for v1 — leave the pair directory on disk for audit but do
not return it.

Symmetric handling: tombstoned **target** triggers the same outcome
(same reason code; populate both `baseline_run_reference` and
`target_run_reference` and surface which side was tombstoned via
`detail`).

### C.2 — Envelope shapes (`regression_outcome`, `regression_delta`) → ship-then-freeze

The first Regression CLI slice may emit any reasonable envelope shape
for `regression_outcome` (single-run "is a baseline resolvable?"
section in `inspect`) and `regression_delta` (two-run comparison
body). PM freezes both shapes in companion decisions AFTER Manual Test
fields them and reports back — the exact cadence the two Coverage
envelope decisions followed.

Rationale: over-design before any consumer touches the shape is the
opposite of the Coverage discipline that worked. The current pin (the
on-disk fact-set shape and the Unavailable enum) is enough for cross-
engine consumers; envelope projection is a lighter concern that
benefits from one round of field exercise.

### C.3 — Engine-version drift across compared runs = **compare with warning**

`compare_runs(baseline, target)` proceeds when
`baseline.run_record.engine_version` ≠
`target.run_record.engine_version`. Both versions are recorded in
`RegressionFactSet.baseline_engine_version` / `target_engine_version`.
A `"engine-version-drift"` code is appended to
`RegressionFactSet.warnings`.

Rationale: "comparable" per the domain model = "share a resolved test
target and enough normalized evidence." Per
`decisions/2026-05-25-supported-engine-matrix.md`, engine patch /
minor bumps overwhelmingly preserve test-result shape; blocking
comparison on version drift breaks the realistic "I bumped pytest"
workflow. Major-version bumps remain possible — surface the drift as a
warning, not a refusal.

Engine **name** mismatch (e.g. pytest vs jest) is a different concern:
that returns `RegressionUnavailable(reason=REASON_ENGINE_MISMATCH)`
because the outcome semantics aren't interchangeable (different status
strings, different node_id shapes).

### C.4 — `resolve_latest_baseline` return-tuple ordering = **pin to `(baseline, target)`**

`design/interace-contract/regression.md:28` currently reads:

> Pair of Run References **(current, previous)** for the most recent comparable runs sharing the same resolved Test Target

This phrasing is ambiguous against the `compare_runs(baseline, target)`
order pinned above (arg1=older, arg2=newer). The natural read of
"(current, previous)" would put `current` in arg1 and `previous` in
arg2, inverting transition direction (all transitions would be reported
backwards).

**Resolution:** the first Regression implementation slice will edit
that line to read:

> Pair of Run References **(baseline_run_reference, target_run_reference)** for the most recent comparable runs sharing the same resolved Test Target

Explicit naming eliminates the ambiguity forever. Task
`tasks/regression-team-2026-05-26-compare-runs-impl.md` carries the
one-line edit (Regression team's territory).

### C.5 — `MemoryEntry.has_regression_facts` flip-time wiring = **Memory owns the probe**

Memory Team's `_availability_flags` probe gains a Regression branch
that scans `<store>/regression/pairs/` for any directory whose name
contains `run_<run_id>` as a substring (either baseline or target
position). When found → `has_regression_facts = True`.

Rationale: consistent with Coverage's precedent — Memory owns the
probe, the engine team owns the file shape. Section 1 of this decision
pins the directory naming so the probe has a stable contract.

Dispatched in the same cycle as the first Regression impl slice
(task `tasks/memory-team-2026-05-26-has-regression-facts.md`) so the
test surface (existing `_availability_flags` tests) is updated in
lockstep.

### C.6 — Coverage schema evolution coupling = **embed accepted; stale-on-read at v-bump**

`RegressionFactSet.coverage_change` embeds `CoverageDelta.to_dict()`
verbatim. When (future) Coverage v2 lands and bumps `CoverageDelta`'s
schema:

- Any **existing** `regression_facts.json` whose embedded
  `coverage_change.schema_version` is below current is treated as
  **stale on read** — `get_regression_facts` returns
  `RegressionUnavailable(reason=REASON_MISSING_DERIVED_FACTS,
  detail="coverage-schema-stale")`.
- The next `compare_runs(baseline, target)` re-derives both halves
  freshly and writes a new `regression_facts.json` with the current
  Coverage shape.

Rationale: same posture Coverage uses for its own schema bumps (read
raises `ValueError` → caller re-derives). Acceptable coupling cost in
exchange for not duplicating the Coverage projection logic. If a real
Coverage v2 ever materializes and the cost looks different in
retrospect, the decision can be revisited.

### C.7 — Localization (Phase 4) input shape = **ship current shape, extend later if needed**

`TestTransition` (section 3 above) exposes everything an SBFL formula
needs at the Regression boundary:

- `node_id` — the test identifier
- `category` — for filtering to the "suspect" universe
  (`{"regressed", "still_failing"}` typically, plus `category=="added"`
  with target_outcome fail-like for newly-introduced failures)
- `baseline_outcome` / `target_outcome` — raw native strings preserved
- `baseline_failure_reference` / `target_failure_reference` — opaque
  handles for failure context
- `baseline_duration_ms` / `target_duration_ms` — for failure-proximity
  scoring

If Localization activation in Phase 4 surfaces a missing field, it
lands as a non-breaking optional field on the existing schema (no
version bump per the forward-compatible-extension rule mirroring
Coverage's). No Phase 3 blocker.

---

## Forward-compatible extension rules

- Adding a new optional field to any dataclass is non-breaking (mirror
  the Coverage convention).
- Adding a new `TRANSITION_CATEGORIES` value is **breaking** —
  consumers that pattern-match on the closed set need updating.
  Requires a `schema_version` bump.
- Adding a new `REASON_*` constant is non-breaking but requires
  updating section 7's enum list above (decision update).
- Adding a new well-known `warnings` code is non-breaking; document
  in the team charter when introduced.
- Changing the directory-naming layout (section 1) is breaking —
  coordinated change across Memory + Regression + decision supersession.

---

## Affected teams / files

- **Regression Team** — owner of
  `src/novetest/models/regression_fact_set.py`,
  `src/novetest/regression/results.py`,
  `src/novetest/regression/compare.py`,
  `src/novetest/regression/retrieval.py` (and any other future
  `regression/*` modules). Any change to the persisted shape now
  requires `schema_version` bump + migration plan + this decision's
  supersession. The first impl slice (task
  `tasks/regression-team-2026-05-26-compare-runs-impl.md`) implements
  sections 1–8 verbatim.

- **Memory Team** — `_availability_flags` probe gains a Regression
  branch (task `tasks/memory-team-2026-05-26-has-regression-facts.md`).
  The probe relies on the directory naming pinned in section 1; any
  future change to that naming requires Memory coordination.

- **Coverage Team** — `CoverageDelta.to_dict()` is embedded in
  `regression_facts.json`. Coverage v2 schema bumps will trigger the
  C.6 stale-on-read path; coordinate with Regression on any breaking
  Coverage change.

- **Localization Team (Phase 4)** — consumes `test_transitions` for
  SBFL scoring. The shape pinned here is the contract; missing fields
  surface as non-breaking schema extensions.

- **Orchestration Team** — `regression compare`, `regression latest`,
  `compare`, and `inspect`'s Regression section consume these facts.
  Envelope projection shapes (`regression_outcome` /
  `regression_delta`) are pinned in **separate** decisions after the
  first CLI slice ships.

- **PM** — owns this decision; owns the
  `.claude/agents/novetest-regression-team.md` charter additions
  (sections A.2 / A.6 / A.9 + reporting hint from the question's
  section B); owns the future `regression_outcome` /
  `regression_delta` envelope decisions when those land.

---

## Effective date

2026-05-26.

## Supersedes

None. First binding decision on the Regression on-disk wire format.
Companion to the Coverage facts-layout decision
(`2026-05-15-coverage-facts-json-layout.md`); together they pin the
two structured-facts contracts cross-engine consumers can rely on.
