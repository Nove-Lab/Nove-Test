---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-05-28
slug: phase4-entry
related:
  - design/implementation-plan/localization-strategy.md
  - design/interace-contract/localization.md
  - design/implementation-plan/delivery-phasing.md
  - src/novetest/regression/__init__.py
  - src/novetest/models/regression_fact_set.py
  - src/novetest/memory/store.py
---

# Task: Phase 4 entry — Localization engine core (per-test SBFL path)

## Mission

Phase 4 entry slice. Build the Localization engine end-to-end for the
**per-test coverage path only** — the strong SBFL story. Defer the two
degraded modes (`sbfl_aggregate`, `failure_proximity`) to follow-up
slices, defer all CLI work to a later Orchestration slice (mirroring
the Regression engine → Regression CLI cadence).

The Localization team activates with this slice (per
`.claude/agents/novetest-localization-team.md` "Activates at Phase 4
entry"). Runs in parallel with the Run team's Go adapter slice;
territories are disjoint (`src/novetest/localization/**` vs
`src/novetest/run/adapters/**`).

**Design decisions are settled** — your job is to *implement* the
design in `design/implementation-plan/localization-strategy.md`, not to
make new design decisions. Section references below all point into
that doc.

## Pre-flight reading (mandatory, in this order)

1. `CLAUDE.md`
2. `.claude/agents/novetest-localization-team.md` (your charter)
3. `agent-comms/INDEX.md`
4. `agent-comms/decisions/` newest first (especially
   `2026-05-25-supported-engine-matrix.md`,
   `2026-05-26-regression-facts-json-layout.md`,
   `2026-05-28-regression-outcome-envelope-shape.md` — for the
   "ship → field-test → freeze" cadence that the Regression engine
   pioneered, which you'll follow).
5. `WORKLOG.md` top 3 entries.
6. **`design/implementation-plan/localization-strategy.md`** — this is
   the design-of-record. Read all 6 sections + Open Items.
7. `design/interace-contract/localization.md` — the 7 interfaces
   (2 External, 5 Internal) you're partially implementing.
8. `design/implementation-plan/engine-adapters.md` §"Cross-Cutting Per-
   Test Coverage Attribution" — explains where per-test coverage
   actually comes from (you depend on Coverage Facts with
   `mapping_granularity: "per-test"`).
9. `src/novetest/models/coverage_fact_set.py` — the input shape to your
   spectra builder. `FileCoverage.line_contexts: dict[int, tuple[str,
   ...]]` is the test-to-code map you turn into the (tests × lines)
   spectra matrix.
10. `src/novetest/regression/__init__.py` and
    `src/novetest/regression/compare.py` — the engine-shape precedent
    (engine surface = pure Python functions; CLI/inspect wiring is a
    later Orchestration slice).
11. `src/novetest/models/regression_fact_set.py` — the dataclass
    pattern (frozen + slots + `to_dict` + `from_dict` + `SCHEMA_VERSION`
    + `CURRENT_SCHEMA_VERSION` ClassVar) you must follow for
    `LocalizationFinding`.
12. `src/novetest/memory/store.py` line 322-325 — the canonical
    persistence path Memory already auto-detects for your findings:
    `<store>/localization/findings/run_<run_id>/localization_findings.json`.

## Pre-slice baseline (verified 2026-05-28)

- `git status`: clean, synced to `origin/main` HEAD `194637b`.
- `uv run pytest -q`: **471 passed, 3 skipped**.
- `src/novetest/localization/` exists with empty `__init__.py` +
  `sbfl/__init__.py` (scaffolding placeholder; you fill it in).
- `tests/unit/localization/` and `tests/unit/localization/sbfl/`
  exist with `.gitkeep` files only.
- `src/novetest/models/localization_finding.py` does **not exist**.
- Memory already auto-flips `has_localization_findings` based on the
  existence of `<store>/localization/findings/run_<id>/localization_findings.json`
  (`src/novetest/memory/store.py:_availability_flags`). You write to
  that path; Memory does the rest.

Run `uv run pytest -q` at your worktree base commit and record the
count in your handoff.

## Model-ownership authorization (CEO-approved 2026-05-28)

You may add `src/novetest/models/localization_finding.py` **directly**.
PM has authorized this exception to the Memory-team-owns-models rule
for this slice (decision: Regression precedent —
`models/regression_fact_set.py` was added by Regression team in the
Phase 3 engine slice; same pattern applies to Localization). This is
not a license to modify other models; touching anything else in
`src/novetest/models/` still requires `agent-comms/questions/`.

The schema for the new model is pinned below — implement exactly this
shape so PM can freeze it via a follow-up decision after Manual Test
fields it (same ship → field-test → freeze cadence Regression
followed).

## Scope — packages, in this order

### 1. `src/novetest/models/localization_finding.py`

Frozen dataclasses, `to_dict`/`from_dict` round-trip on every payload-
bearing dataclass. Pattern: mirror `regression_fact_set.py` exactly
(SCHEMA_VERSION module constant, ClassVar CURRENT_SCHEMA_VERSION,
`_require_keys` helper, `__post_init__` validators for closed enums).

```python
SCHEMA_VERSION: int = 1

# Mode enum — design-of-record §2
LOCALIZATION_MODES: frozenset[str] = frozenset({
    "sbfl_per_test",
    "sbfl_aggregate",       # not produced by this slice; enum value reserved
    "failure_proximity",    # not produced by this slice; enum value reserved
})

# Confidence enum — design-of-record §2
LOCALIZATION_CONFIDENCES: frozenset[str] = frozenset({"high", "medium", "low"})

# Formula enum — design-of-record §1
FORMULAS: frozenset[str] = frozenset({"ochiai", "op2", "dstar2", "tarantula"})

# CodeLocation kind — design-of-record §3
CODE_LOCATION_KINDS: frozenset[str] = frozenset({"symbol", "line", "branch", "file"})
```

```python
@dataclass(slots=True, frozen=True)
class CodeLocation:
    kind: str                              # one of CODE_LOCATION_KINDS
    file: str                              # repo-relative
    symbol: str | None                     # e.g. "BarService.compute"
    line_range: tuple[int, int] | None     # (start_line, end_line) inclusive
    primary_line: int                      # top-ranked line inside the symbol
    evidence_lines: tuple[int, ...]        # other suspicious lines

@dataclass(slots=True, frozen=True)
class EvidenceCitation:
    kind: str                              # "test_result" | "coverage_fact"
    run_reference: RunReference
    selector: dict[str, Any]               # discriminated payload, kind-dependent
    # For this slice's per-test path:
    #   kind == "test_result" → selector = {"test_id": "<nodeid>", "outcome": "failed"}
    #   kind == "coverage_fact" → selector = {"file": "<path>", "lines": [<int>, ...]}
    # Regression-fact citations are reserved for the aggregate-mode slice.

@dataclass(slots=True, frozen=True)
class LocalizationEntry:
    rank: int                              # 1-based dense rank
    tied_with: tuple[str, ...]             # other entry handles sharing this rank
    code_location: CodeLocation
    score_raw: float                       # the `formula` field's score, native value
    score_normalized: float                # min-max within this finding set, [0,1]
    formula: str                           # which formula `rank` derived from
    alternate_scores: dict[str, float]     # {formula -> score} for the other three
    related_failed_tests: tuple[str, ...]  # failed-test node_ids touching this location
    evidence_citations: tuple[EvidenceCitation, ...]

@dataclass(slots=True, frozen=True)
class LocalizationFinding:
    """Top-level persisted localization payload for one run."""
    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    run_reference: RunReference
    engine_name: str
    ecosystem: str
    mode: str                              # one of LOCALIZATION_MODES
    confidence: str                        # one of LOCALIZATION_CONFIDENCES
    formula: str                           # default presentation formula; "ochiai" today
    alternate_scores_available: tuple[str, ...]  # other formulas computed
    top_n: int                             # default 10
    entries: tuple[LocalizationEntry, ...]
    derived_at: int                        # epoch_ms
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.mode not in LOCALIZATION_MODES:
            raise ValueError(...)
        if self.confidence not in LOCALIZATION_CONFIDENCES:
            raise ValueError(...)
        if self.formula not in FORMULAS:
            raise ValueError(...)
        for alt in self.alternate_scores_available:
            if alt not in FORMULAS:
                raise ValueError(...)
```

The wire path for `LocalizationFinding.to_dict()` is what
`localization_findings.json` stores. Today only the outer
`LocalizationFinding.schema_version` is used. (Same pattern as
`CoverageFactSet` — inner blocks can grow their own schema_version
when their shape stabilizes.)

### 2. `src/novetest/localization/__init__.py` — public API

Mirror `src/novetest/regression/__init__.py` shape: a module docstring
explaining what's IN this slice vs OUT, then re-exports of public
symbols. Today's public API:

```python
from novetest.models.localization_finding import (
    SCHEMA_VERSION,
    LOCALIZATION_MODES,
    LOCALIZATION_CONFIDENCES,
    FORMULAS,
    CODE_LOCATION_KINDS,
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
    LocalizationFinding,
)
from novetest.localization.derive import derive_localization_findings
from novetest.localization.results import (
    KNOWN_REASONS,
    REASON_NO_FAILED_TESTS,
    REASON_NO_COVERAGE,
    REASON_NO_RUN_EVIDENCE,
    REASON_RUN_NOT_ANALYZABLE,
    LocalizationUnavailable,
)
from novetest.localization.retrieval import (
    check_localization_availability,
    get_localization_findings,
)
```

The CLI verbs (`novetest localization <run_id>` /
`novetest localization latest` / `inspect` Localization section) are
**explicitly OUT** of this slice — they live in a later Orchestration
slice. State that in the docstring (precedent:
`src/novetest/regression/__init__.py` did this for its CLI).

### 3. `src/novetest/localization/results.py` — Unavailable result

```python
REASON_NO_FAILED_TESTS = "no_failed_tests"
REASON_NO_COVERAGE = "no_coverage"
REASON_NO_RUN_EVIDENCE = "no_run_evidence"
REASON_RUN_NOT_ANALYZABLE = "run_not_analyzable"

KNOWN_REASONS: frozenset[str] = frozenset({
    REASON_NO_FAILED_TESTS,
    REASON_NO_COVERAGE,
    REASON_NO_RUN_EVIDENCE,
    REASON_RUN_NOT_ANALYZABLE,
})

@dataclass(slots=True, frozen=True)
class LocalizationUnavailable:
    """Discriminator for the unavailable-localization outcome.

    Mirrors `RegressionUnavailable` / `CoverageUnavailable` so the
    eventual CLI projection at the orchestration layer follows the
    same `kind: "fact-set" | "unavailable"` discriminator pattern.
    """
    run_reference: RunReference | None
    reason: str
    detail: str | None

    def __post_init__(self) -> None:
        if self.reason not in KNOWN_REASONS:
            raise ValueError(...)
```

When does each reason fire (this slice):

- `no_run_evidence` — `retrieve_run_evidence` raises
  `RunEvidenceNotFoundError` for the requested run_id, OR the
  Memory Entry exists but has no Run Record on disk.
- `run_not_analyzable` — the Run Record is tombstoned (mirror the
  regression engine's policy of remaining strict about tombstoned
  inputs; per design-of-record §5 the AI consumer "will spend tokens
  reasoning over noise" if we soft-fail). Reuse the precedent.
- `no_failed_tests` — Run Record has 0 failed test results.
- `no_coverage` — Run Record has failed tests but
  `get_coverage_facts(store, run_ref)` returns `CoverageUnavailable`
  (i.e. no Coverage Facts at all). In a *later slice* this would
  trigger `failure_proximity` mode; today it surfaces as Unavailable.
  Document this loudly in `no_coverage`'s `detail`:
  `"coverage facts unavailable; failure_proximity mode is not yet
  implemented (Phase 4 follow-up)"`.

What about "coverage exists but `mapping_granularity != per-test`"? In
this slice — same `no_coverage` reason with a different `detail`:
`"coverage mapping_granularity={...} is not per-test;
sbfl_aggregate mode is not yet implemented (Phase 4 follow-up)"`. The
aggregate-mode slice will replace these branches with real findings.

### 4. `src/novetest/localization/sbfl/spectra.py`

Build the `(tests × statements)` spectra matrix from a per-test
`CoverageFactSet`. Surface:

```python
import numpy as np
from novetest.models.coverage_fact_set import CoverageFactSet

@dataclass(slots=True, frozen=True)
class Spectra:
    test_ids: tuple[str, ...]              # row order
    locations: tuple[tuple[str, int], ...] # (file_path, line) per column
    matrix: np.ndarray                     # shape = (len(test_ids), len(locations)), uint8
    test_outcomes: np.ndarray              # shape = (len(test_ids),), uint8 (1=failed, 0=passed)

def build_spectra(
    coverage_facts: CoverageFactSet,
    failed_test_ids: frozenset[str],
) -> Spectra:
    """Build (tests × statements) spectra from per-test line_contexts.

    Iterates `coverage_facts.files[*].line_contexts` (the
    `dict[int, tuple[str, ...]]` test-to-code map) and assembles a
    dense boolean matrix. Sparse representation is Open Question #11
    (engine-adapters.md / localization-strategy.md Open Items) —
    revisit when a fixture exceeds the threshold; for this slice ship
    dense.
    """
```

Precondition: caller has already verified
`coverage_facts.mapping_granularity == "per-test"`. The spectra
builder fails loudly if `line_contexts` is empty everywhere (defensive
parsing per supported-engine-matrix decision).

### 5. `src/novetest/localization/sbfl/{ochiai,op2,dstar,tarantula}.py`

One numpy vector op per formula. The math is in design-of-record §1's
table:

```python
# ochiai.py
import numpy as np

def ochiai(ef: np.ndarray, ep: np.ndarray, nf: np.ndarray, np_: np.ndarray) -> np.ndarray:
    """ef / sqrt((ef + nf) * (ef + ep)); 0 when denominator is 0."""
    denom = np.sqrt((ef + nf) * (ef + ep))
    return np.where(denom > 0, ef / denom, 0.0)
```

All four take the four count vectors (ef, ep, nf, np_) — same input
shape, same output shape `(num_locations,)`. Tarantula's formula
needs a tie-break guard against `0/0` (when no test passed AND no test
failed touches a location); fall through to 0 (mirrors Ochiai's
`denom > 0` guard).

The count-vector computation lives in `derive.py` (next file) once;
each formula module is pure math.

### 6. `src/novetest/localization/symbol_resolver.py` — Python `ast` only

```python
def resolve_python_symbol(file_path: Path, line: int) -> tuple[str | None, tuple[int, int] | None]:
    """Map `(file, line)` to `(qualified_symbol, line_range)`.

    Parses `file_path` with `ast`, walks `FunctionDef` / `AsyncFunctionDef`
    / `ClassDef` nodes, finds the smallest enclosing one. Returns the
    dotted-qualified symbol (`"Foo.bar"` for a method, `"baz"` for a
    module-level function) and its `(lineno, end_lineno)` range.

    Returns `(None, None)` when:
    - File is not parseable as Python (syntax error).
    - File does not exist.
    - Line is outside any function/method (module-level top code).

    In all `(None, None)` cases the caller falls back to file-level
    CodeLocation (`kind="file"`).
    """
```

This is the **only** language resolver in this slice. Per design-of-
record §3 + delivery-phasing.md Phase 4 risks: "Phase 4 ships with
file-level fallback for ecosystems whose resolver is not yet ready."
JS/Java/Go/Rust/C# resolvers ship in **later slices** — NOT yours.

What if the Run engine emitted a non-Python `engine_name`? Today the
per-test path only fires for `engine_name=="pytest"` (the only engine
with per-test coverage attribution per `engine-adapters.md`). Other
engines hit `no_coverage` via the per-test precondition. So the slice
naturally restricts itself to Python — but you must NOT hard-code that
assumption in `derive.py`. Code the path conditional on
`mapping_granularity == "per-test"` and let the engine-name dispatch
emerge naturally; if a future per-test-capable engine lands, the
fallback is `(None, None)` → file-level CodeLocation, which is the
correct degraded behavior.

### 7. `src/novetest/localization/derive.py` — `derive_localization_findings`

End-to-end composition:

```python
def derive_localization_findings(
    store: ProjectStore,
    run_reference: RunReference,
    *,
    top_n: int = 10,
    formula: str = "ochiai",
) -> LocalizationFinding | LocalizationUnavailable:
    """Engine entry point. Cache-aware: writes localization_findings.json
    on first derivation, reads it on subsequent calls (mirror
    `compare_runs` / `derive_coverage_facts` cache-then-derive pattern).

    Pipeline (per-test path only this slice):
      1. retrieve_run_evidence — raises → REASON_NO_RUN_EVIDENCE
      2. tombstoned? → REASON_RUN_NOT_ANALYZABLE
      3. failed tests = 0? → REASON_NO_FAILED_TESTS
      4. get_coverage_facts → unavailable → REASON_NO_COVERAGE
      5. coverage_facts.mapping_granularity != "per-test"?
           → REASON_NO_COVERAGE (detail = "sbfl_aggregate not yet
             implemented")
      6. build_spectra
      7. compute ef/ep/nf/np per location, call all 4 formulas
      8. rank by `formula` (default ochiai)
      9. aggregate up to symbols via Python ast resolver (max(score)
         per symbol per design-of-record §3)
     10. min-max normalize within finding set; dense 1-based rank;
         compute tie groups
     11. take top_n
     12. build EvidenceCitations per entry (test_result for related
         failed tests + coverage_fact for the implicated lines)
     13. assemble LocalizationFinding and persist to
         <store>/localization/findings/run_<id>/localization_findings.json
         (atomic write via tempfile + rename, mirror Regression's
         persist helper)
     14. return
    """
```

### 8. `src/novetest/localization/retrieval.py`

```python
def get_localization_findings(
    store: ProjectStore,
    run_reference: RunReference,
) -> LocalizationFinding | LocalizationUnavailable:
    """Cache-read only. Returns LocalizationUnavailable(reason=
    REASON_RUN_NOT_ANALYZABLE, detail="findings not yet derived") when
    the file does not exist.
    """

def check_localization_availability(
    store: ProjectStore,
    run_reference: RunReference,
) -> bool:
    """Eligibility flag — used by Orchestration's
    `evaluate_stage_eligibility`. Returns True iff:
      1. Run exists and is not tombstoned.
      2. Has at least one failed test.
      3. Has Coverage Facts with mapping_granularity == "per-test".

    Does NOT actually derive; this is a cheap precondition check.
    """
```

`check_localization_availability` mirrors
`check_regression_availability`'s shape exactly — it's the eligibility
flag for the orchestration layer.

## Persistence path (load-bearing)

Write to: `<store>/localization/findings/run_<run_id>/localization_findings.json`

This filename and directory layout is **load-bearing** — Memory's
`_availability_flags` (`src/novetest/memory/store.py` line ~309)
probes for this exact path to auto-flip `has_localization_findings`.
Do NOT use a different filename. Atomic write (`tempfile.NamedTemporaryFile`
in the same parent dir + `os.replace`) per the Memory persistence
convention.

Create the parent directories on first write.

## Fixture project — `tests/fixtures/projects/localization-branch/`

Per `delivery-phasing.md` Phase 4: "a deliberate single-line bug with
rich coverage". You own the fixture under your charter
(Localization-team-owned by territory since it exercises YOUR engine —
coordinate via questions if your charter is ambiguous).

Shape:
- Python project with a `pyproject.toml`, a small module
  (e.g. `branchy.py`) with 4-6 functions, and a pytest test file with
  multiple tests where ONE specific test fails and the failing
  function has high suspicion under Ochiai.
- The test suite must produce per-test coverage when run with
  `pytest --cov=. --cov-context=test` (so the `line_contexts` map is
  populated — exactly what `pytest-coverage` fixture already does;
  use that fixture as your template).
- Must NEVER import `novetest`.

The fixture is the smoke test for end-to-end derivation. Your
integration test runs the full `novetest run --coverage` flow against
it (or uses a recorded Run Record + Coverage Facts), then calls
`derive_localization_findings`, then asserts the buggy function is
ranked top-1 (per `delivery-phasing.md` DoD bullet [186] — though
that bullet doesn't tick until the CLI lands).

## Test surface

### Unit tests — `tests/unit/localization/`

Mirror `tests/unit/regression/` organization. Aim for ~30-40 tests
across these files:

- `tests/unit/localization/sbfl/test_ochiai.py` — math correctness on
  hand-picked vectors (single-fault localization, no-fault zero, edge
  case where every test passes/fails).
- `tests/unit/localization/sbfl/test_op2.py`,
  `test_dstar.py`, `test_tarantula.py` — same shape, formula-specific
  edge cases.
- `tests/unit/localization/sbfl/test_spectra.py` — build_spectra
  correctness across small CoverageFactSet shapes (one test/one line,
  many tests/many lines, no per-test contexts → fails loudly).
- `tests/unit/localization/test_symbol_resolver.py` — Python ast
  resolution: function, method, nested function, syntax error
  (returns None), file-not-found (returns None), module-level code
  (returns None).
- `tests/unit/localization/test_results.py` — `LocalizationUnavailable`
  validation, KNOWN_REASONS enum closure, REASON_* constant identity.
- `tests/unit/localization/test_derive.py` — the orchestrating
  function. Cover each pipeline branch:
  - Run not found → REASON_NO_RUN_EVIDENCE.
  - Run tombstoned → REASON_RUN_NOT_ANALYZABLE.
  - No failed tests → REASON_NO_FAILED_TESTS.
  - Coverage unavailable → REASON_NO_COVERAGE.
  - Coverage present but mapping_granularity == "aggregate"
    → REASON_NO_COVERAGE with the documented detail.
  - Per-test path happy-path: assert ranking, normalization, tie
    detection, top_n cutoff, EvidenceCitations populated.
  - Cache: second call after first persistence returns the cached
    finding without re-deriving (assert by spying on `build_spectra`
    or by mutating coverage_facts.json in between and observing the
    cached result).
- `tests/unit/localization/test_retrieval.py` —
  `get_localization_findings` cache-read (present + absent) and
  `check_localization_availability` (3 branches: not-found,
  no-failed-tests, no-per-test-coverage, true).
- `tests/unit/localization/test_localization_finding_model.py` —
  `to_dict`/`from_dict` round-trip, `__post_init__` validators for
  closed enums, schema_version mismatch raises.

### Integration test — `tests/integration/localization/`

ONE meaningful integration test under
`tests/integration/localization/test_localization_branch_basic.py`:
real `novetest run --coverage` against
`tests/fixtures/projects/localization-branch/`, then
`derive_localization_findings`, then assert top-1 is the buggy
function. Skip cleanly when pytest/coverage tooling is missing (same
pattern as the existing jest integration tests).

### Aim

Final pytest count should be roughly **501-511 passed + 3 skipped +
small N skipped** (the integration test may skip on a minimal box).

## Algorithm notes (cribbed from design-of-record so you don't have to dig)

### From §1 — formulas, with `ef, ep, nf, np_` arrays per location

| Formula | Math | Bounds |
|---|---|---|
| Ochiai | `ef / sqrt((ef + nf) * (ef + ep))` | [0, 1] |
| Op2 | `ef - ep / (ep + np_ + 1)` | unbounded |
| DStar (`*`=2) | `ef ** 2 / (ep + nf)` (return 0 when denom==0) | unbounded |
| Tarantula | `(ef/(ef+nf)) / (ef/(ef+nf) + ep/(ep+np_))` (return 0 when denom==0) | [0, 1] |

### Aggregation up to symbol (§3)

For each `(file, symbol)` group: take `max(line_score)` of all lines
inside the symbol's `line_range`. **Do NOT mean** — mean dilutes by
symbol size. The `evidence_lines` field carries the top-K suspicious
lines inside the symbol (for AI consumer transparency); `primary_line`
is the single highest-scored line.

When the resolver returns `(None, None)` (e.g. module-level code or
file-level fallback), the CodeLocation is `kind="file"` with `symbol=
None, line_range=None, primary_line=<top_line>, evidence_lines=<top-K
lines in this file>`. Per design-of-record §3 huge-file pathology
note, file-level entries DO appear in the ranking — but only when no
symbol resolver matches; not as a default.

### Normalization (§4)

- `score_raw` — the formula's native value for the entry's score
  (i.e. the entry's `formula` field's score, NOT a fixed Ochiai-only
  pick).
- `score_normalized` — min-max within the finding set. Apply BEFORE
  top_n truncation per the literature (normalize the whole ranking
  so the truncation does not concentrate the [0,1] range to a
  sub-window). Document this in the code.
- `rank` — 1-based dense (ties share a rank, next rank skips).
- `tied_with` — list of OTHER entries' identifying handles sharing
  this rank. Use `entry_index_<i>` strings since entries don't have
  natural IDs in this slice; finalize the convention by tying via
  index. Manual Test will field-test this and PM will freeze in a
  follow-up decision.
- `alternate_scores` — `{formula: score}` map of the other three
  formulas' scores for the SAME location (so AI consumers can compare
  without re-derive).

### Top-N default = 10 (§4)

Hard-coded default; accept `top_n: int = 10` parameter on
`derive_localization_findings` for future CLI plumbing but don't add
a CLI surface today.

## Out-of-scope (DO NOT do in this slice)

- **CLI verbs** (`novetest localization <run_id>` /
  `novetest localization latest`) — Orchestration slice later,
  following the Regression-engine → Regression-CLI cadence.
- **`inspect` Localization section wiring** — Orchestration slice.
- **`sbfl_aggregate` mode** including FLUCCS regression-aware
  reweighting (design-of-record §2) — follow-up Localization slice.
- **`failure_proximity` mode** (no-coverage fallback) — follow-up
  Localization slice.
- **`resolve_latest_analyzable_run`** + `derive_latest_localization`
  — follow-up slice (mirrors Regression's baseline-resolution
  separate slice).
- **Non-Python symbol resolvers** (JS/TS, Java/Kotlin, Go, Rust, C#)
  — file-level fallback for now; per-language resolvers ship in
  later slices.
- **Branch-level granularity** — auxiliary evidence inside `evidence_lines`
  is OK; `kind="branch"` is reserved but not produced today.
- **Cross-run reweighting (DeepFL-style)** — explicitly out, per
  design-of-record Open Items #4.
- **Sparse spectra representation** — Open Question #11; defer to a
  later slice when a fixture exceeds threshold.
- **Modifications to `src/novetest/models/*` other than the new
  `localization_finding.py`** — write a question if needed.
- **Modifications to other engine packages** (`coverage/`,
  `regression/`, `memory/`, etc.) — strictly OUT.
- **Modifications to `agent-comms/decisions/*.md` or
  `design/*.md`** — PM territory.

## DoD bullets

This slice does NOT directly close any `delivery-phasing.md` `- [ ]`
bullet. Phase 4's bullets [186-189] require the full CLI surface plus
mode coverage; this slice is the *engine foundation* for them. Report
in your handoff under "Phase progress: Phase 4 entry — engine core
(per-test path) landed; CLI + aggregate/proximity modes follow-up".

## Handoff requirements

Standard handoff (`agent-comms/handoffs/localization-team-2026-05-28-phase4-entry.md`)
with the usual sections, plus:

- **Worktree** path / branch / base commit / push status.
- **Files written/modified** with the new package laid out.
- **Tests**: `uv run pytest -q` final count + comparison to baseline;
  `uv run mypy --strict` clean.
- **WORKLOG.md entry text**: paste here. Phase-4-entry is a
  load-bearing event; the worklog entry should make it visible.
- **Schema decisions you made** during implementation that PM should
  freeze in a follow-up `decisions/` entry. At minimum:
  - The `LocalizationFinding` shape (exact `to_dict()` output).
  - The `LocalizationUnavailable` shape + the 4-reason closed enum.
  - The `tied_with` convention (entry_index strings — propose
    alternatives if you discover a better handle during
    implementation).
  - Persistence path `<store>/localization/findings/run_<id>/localization_findings.json`.
- **Open items** for follow-up slices: aggregate mode, proximity
  mode, latest-resolution, CLI, per-language resolvers.
- **Observed behaviors not pinned by design** — anything Manual Test
  should pay attention to (e.g. tie-handling on top-N truncation
  boundary, file-level fallback for module-level code, etc.). PM
  will collect these for the freeze decision.

Run `python3 tools/regen_comms_index.py` before committing the
handoff.

## Reporting back

After your handoff is committed, Main Branch will merge, write
verification, push. Manual Test then field-tests the engine surface
(invokes `derive_localization_findings` via Python repl since no CLI
exists yet — mirrors how they exercised the Regression engine pre-CLI
in the Phase 3 engine slice). Findings come back to PM, who freezes
the shape in `decisions/`. Then the Orchestration team gets a CLI
slice in a subsequent cycle.

The cadence — ship working draft → field-test → PM freeze — is the
same Regression followed across its three cycles. The Localization
team is now on that same cadence.
