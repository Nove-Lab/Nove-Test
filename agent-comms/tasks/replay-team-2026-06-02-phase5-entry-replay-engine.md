---
from: novetest-pm-team
to: novetest-replay-team
type: task
created: 2026-06-02
slug: phase5-entry-replay-engine
status: pending
related:
  - design/implementation-plan/delivery-phasing.md
  - design/interace-contract/replay.md
  - design/workflows/replay.md
  - design/requirements-analysis/requirements-specification/groups/replay.md
  - agent-comms/decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md
  - agent-comms/history/2026-06-02-phase1-and-phase6-complete-recommendation-synthesis-lands.md
---

# Phase 5 entry — Replay engine

## TL;DR

Implement the Replay engine — `src/novetest/replay/` is currently empty;
this slice fills it with `replay_run` / `reconstruct_replay_context` /
`classify_replay_consistency` / `get_replay_result` /
`check_replay_availability` + the canonical `ReplayResult` model under
`src/novetest/models/` + the `novetest replay <run_id>` CLI verb + a
deliberately-flaky `flaky-python/` fixture. The slice **closes Phase 5
(3 DoD bullets at `delivery-phasing.md:221-223`)** and **activates the
`flaky_suspected` recommendation category for real** (currently
mock-tested only). After this slice **Phase 5 → 100% complete** and MVP
scope reduces to: Phase 3 JUnit + Phase 3 .NET (Open-Q-gated) + Phase 7
MCP (post-MVP).

**SQLite is explicitly out of scope** for this slice — deferred until a
cross-run aggregation verb lands per
`decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md`.
**Do not create `.novetest/memory/index.db`.** Do not create
`memory/migrations/`. Do not introduce `sqlite3` as an import. If you
find yourself wanting any of those, stop and re-read the decision file.

The `delivery-phasing.md` Phase 5 "Persistence" paragraph has been
rewritten to reflect this; `foundations.md` §4 forward-note settings
remain unchanged as binding intent for a future cycle.

## Product framing

Before this slice:

```
$ novetest replay <run_id>
[ JSON envelope: kind=stub, exit 2, "not yet implemented" ]
```

After this slice:

```
$ novetest replay <run_id_of_flaky> --reruns=5
[ JSON envelope: classification=inconsistent, reruns_total=5,
  reruns_failed=2, replayed_run_reference=<new ulid> ]

$ novetest replay <run_id_of_pytest_basic>
[ JSON envelope: classification=reproducible, reruns_total=1,
  reruns_failed=0 ]

$ novetest replay <stale_run_id>
[ JSON envelope: classification=unable_to_replay, reason=<...> ]
```

The integrated `novetest test` workflow does **not** invoke Replay in
this slice — Replay stays an opt-in CLI verb until a post-MVP design
cycle decides whether to weave it into `novetest test` automatically.
The `flaky_suspected` recommendation category is **structurally ready**
(the trigger is implemented in `categories.py::match_flaky_suspected`)
but only fires when something has populated `FactBundle.replay_result`;
the integrated workflow keeps passing `replay_result=None`. To
**verify** the category end-to-end you add a small integration test that
constructs a `FactBundle` with a real `ReplayResult` produced by this
slice's engine and asserts the recommendation surface — see §7.

## Pre-flight reading (mandatory)

1. `CLAUDE.md`
2. `.claude/agents/novetest-replay-team.md` (your charter)
3. `agent-comms/decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md`
4. `design/interace-contract/replay.md` (5 internal APIs)
5. `design/workflows/replay.md` (workflow sequences)
6. `design/requirements-analysis/requirements-specification/groups/replay.md` (4 REQ + 2 NFR)
7. `design/interace-contract/run.md` — read **only** `execute_with_engine_context` (you reuse it; do NOT modify Run engine code)
8. `design/interace-contract/memory.md` — read `store_run_evidence` / `retrieve_run_evidence` / `find_runs_for_target` (you consume them)
9. `src/novetest/orchestration/recommendation/fact_bundle.py` lines 159-189 — the transient `ReplayResult` placeholder you are replacing
10. `src/novetest/orchestration/recommendation/categories.py` lines 355-384 — `match_flaky_suspected` (already implemented; your job is to make it fire for real)
11. `src/novetest/orchestration/workflows/test.py` line 223 (`replay_result=None,`) — the integrated workflow's Replay handoff point; **NOT modified in this slice** (Replay stays out of integrated workflow per §"Out of scope")
12. `src/novetest/orchestration/workflows/status.py` line 131 — the `replay_available=False` default that this slice flips to a real cache-only probe
13. `src/novetest/orchestration/workflows/inspect.py` line 95 — the `"replay": "unavailable"` marker that this slice flips
14. `src/novetest/run/engine.py` lines 66-103 — `execute_with_engine_context` (your reuse target)
15. `src/novetest/cli/app.py` lines 1100-1162 (the `test_cmd` handler as the model for `replay_cmd`) and line 1182 (the existing `replay` stub registration you replace)
16. `tests/unit/orchestration/recommendation/test_categories.py::TestFlakySuspected` (lines 554+) — the mock-based unit pattern; this slice **keeps** those mock tests and **adds** integration tests using a real `ReplayResult` end-to-end

---

## 1. Binding contracts (frozen — verbatim wire shape)

### 1.1 ReplayResult model — promoted to `src/novetest/models/replay_result.py`

The fact_bundle.py transient placeholder is replaced by a canonical model.
**Binding minimum shape** (Phase 6 entry pinned these as the synthesizer's
expected fields):

| Field | Type | Required | Source |
|---|---|---|---|
| `run_reference` | `RunReference` | yes | original Run's reference |
| `classification` | `Literal["reproducible","inconsistent","unable_to_replay"]` | yes | closed enum frozen by REQ-REP-003 |
| `reruns_total` | `int` (>= 0) | yes | total reruns performed in this replay session |
| `reruns_failed` | `int` (>= 0, <= reruns_total) | yes | reruns whose outcome differed from the original |
| `test_id` | `str \| None` | optional | nodeid of the focal test when classification is `inconsistent` and a single test caused it; `None` otherwise |

**You MAY add fields** beyond this minimum (recommended additions below);
**you MUST NOT remove or rename** any of the five above without bumping
the synthesizer's `categories.py::match_flaky_suspected` matcher (a
synchronized change, requiring a PM decision). Adding fields is free:
the synthesizer ignores unknown fields, and `fact_bundle.py` will just
import-and-re-export the new shape.

**Strongly recommended additions** (your judgment — handoff records why):

- `replayed_run_reference: RunReference | None` — the ULID of the replay-execution Run Record (`None` when classification is `unable_to_replay` and no replay run was produced; REQ-REP-004 requires this slot when a replay run was created).
- `per_rerun_outcomes: tuple[str, ...]` — closed-vocab outcomes per rerun (e.g. `("passed","failed","passed","passed","failed")` for a 5-rerun inconsistent run). Useful for an AI agent to see the pattern.
- `consistency_summary: dict[str, int]` — `{"original_passed": N, "replay_passed": M, ...}` counts powering classification — REQ-REP-003 mentions "consistency summary".
- `attempted_at: int` — epoch-millisecond timestamp of the replay attempt.
- `reason: str | None` — when classification is `unable_to_replay`, an enum-string from the closed set you choose (e.g. `"context-reconstruction-failed" / "engine-not-ready" / "target-missing" / "tombstoned-original"`).

The model lives at `src/novetest/models/replay_result.py`, follows the
project's `dataclass(slots=True, frozen=True)` convention with
`schema_version: int = 1` + `to_dict` + `from_dict` (validating
`schema_version` with the same pattern as `RunReference` /
`CoverageFactSet`).

### 1.2 Engine API — 5 internal functions

Implement these in `src/novetest/replay/` (split across files per §3
layout). Signatures match `design/interace-contract/replay.md`:

```
# replay/engine.py
async def replay_run(
    store: ProjectStore,
    original_ref: RunReference,
    *,
    reruns: int = <DEFAULT>,  # your choice; see §6
    timeout: float | None = 600.0,
) -> ReplayResult | ReplayUnavailable:
    """External entry. Reconstruct context, execute N reruns, classify."""

# replay/context.py
def reconstruct_replay_context(
    store: ProjectStore,
    original_ref: RunReference,
) -> ReplayContext | ReplayUnavailable:
    """Resolve test target + native engine context from stored evidence."""

# replay/classifier.py
def classify_replay_consistency(
    original_record: RunRecord,
    replayed_records: list[RunRecord],
) -> ReplayResult:
    """Pure function over Run Records; produces classification."""

# replay/retrieval.py
def get_replay_result(
    store: ProjectStore,
    original_ref: RunReference,
) -> ReplayResult | ReplayUnavailable:
    """Cache-only read; mirrors get_coverage_facts/get_localization_findings."""

def check_replay_availability(
    store: ProjectStore,
    original_ref: RunReference,
) -> bool:
    """Predicate used by status/eligibility; cache-only OR cheap probe (your call)."""
```

Add `ReplayUnavailable` discriminator dataclass mirroring
`CoverageUnavailable` / `LocalizationUnavailable` / `RegressionUnavailable`
(closed `reason` enum, optional `detail`, `run_reference` on it for
traceability). Decide your closed `reason` vocabulary (e.g.
`"original-not-found" / "tombstoned-original" / "context-reconstruction-failed" /
"engine-not-ready" / "target-missing" / "missing-derived-facts"`) — record
your rationale in the handoff.

### 1.3 Workflow sequence — `novetest replay <run_id>`

Per `design/workflows/replay.md`:

```
novetest replay <run_id>
  → replay/replay_run
       → replay/reconstruct_replay_context
            → memory/retrieve_run_evidence         (original RunRecord + NativeEngineContext)
       → run/execute_with_engine_context           (loop N times, --reruns)
       → memory/store_run_evidence                 (loop, one per rerun)
       → replay/classify_replay_consistency        (pure)
       → replay/persistence (your write helper)    (persist ReplayResult)
```

`run/execute_with_engine_context` is the load-bearing reuse — same
native engine path as the original run (REQ-REP-002). **Do NOT modify
`src/novetest/run/`.** If you discover a contract limitation, file a
question against PM (`agent-comms/questions/replay-team-...`); do not
fix the Run engine directly.

### 1.4 Persistence — `replay_result.json` per original run

Mirrors `coverage_facts.json` / `localization_findings.json` /
`regression_facts.json` patterns:

```
.novetest/replay/results/run_<original_ulid>/replay_result.json
```

Write helper in `src/novetest/replay/persistence.py`
(`replay_result_path(store, original_ref)` + `write_replay_result` +
`read_replay_result`). The replayed run records themselves persist via
the existing `memory/store_run_evidence` path — they show up in
`memory list` exactly like any other run (this is by design: replay
runs are first-class Memory Entries citable by Recommendations, per
`design/workflows/replay.md` Notes).

**Do not write any SQLite.** Period.

### 1.5 Envelope shape — `novetest replay <run_id>` command output

```json
{
  "schema": "novetest/v1",
  "command": "replay",
  "ok": true,
  "data": {
    "original_run_reference": { "schema_version": 1, "run_id": "...", "created_at": ... },
    "replay_outcome": {
      "kind": "replay-result",
      "classification": "inconsistent",
      "reruns_total": 5,
      "reruns_failed": 2,
      "test_id": "tests/test_x.py::test_y",
      "replayed_run_reference": { ... },
      "per_rerun_outcomes": ["passed","failed","passed","passed","failed"],
      "consistency_summary": { "original_passed": 1, "replay_passed": 3, "replay_failed": 2 },
      "attempted_at": 1748800000000,
      "reason": null
    }
  },
  "errors": [],
  "warnings": []
}
```

Unavailable variant (mirrors `coverage_outcome` / `localization_outcome`
patterns):

```json
{
  "schema": "novetest/v1",
  "command": "replay",
  "ok": true,
  "data": {
    "original_run_reference": { ... },
    "replay_outcome": {
      "kind": "unavailable",
      "run_reference": { ... },
      "reason": "tombstoned-original",
      "detail": "..."
    }
  },
  "...": "..."
}
```

Engine-not-ready / target-missing surface as exit code 4 (mirrors
`EXIT_ENGINE_MISSING` in `run_cmd` / `test_cmd`). Original-not-found
(stale `run_id`) surfaces as exit code 2 + `errors[].code=not-found`
(mirrors `inspect_cmd`'s not-found path). `unable_to_replay` is
**still a successful structured outcome** (`ok: true`, exit 0) — REQ-REP-003
specifically classifies `unable_to_replay` as a valid classification,
not an error.

### 1.6 Recommendation surface — `flaky_suspected` activates for real

The trigger in `categories.py::match_flaky_suspected` is **already
implemented** (Phase 6 entry slice). After this slice ships, an
integration test (§7) constructs a `FactBundle` carrying a real
`ReplayResult` produced by your engine and asserts the synthesizer
emits a `flaky_suspected` recommendation. **You do not modify
`categories.py` / `templates.py` / `citations.py` / `synthesizer.py`.**

The recommendation's `evidence_citations` will carry a
`kind: "replay_result"` citation (already specified by
`design/implementation-plan/recommendation-synthesis.md` §3 + Phase 6 entry's
`citations.py`). Sanity-check that the citation resolves back to your
`get_replay_result(store, original_ref)` (this is the NFR-ORCH-002
round-trip; existing test
`test_recommendation_round_trip.py::test_investigate_location_citations_round_trip`
covers `investigate_location`, your §7 integration test adds the
`flaky_suspected` analog).

---

## 2. `ReplayResult` model migration — fact_bundle.py placeholder removal

This is a **load-bearing surgical edit** that any future code reading
`bundle.replay_result` continues to work byte-identically. Steps:

1. Create `src/novetest/models/replay_result.py` with the canonical
   `ReplayResult` dataclass per §1.1 + `REPLAY_CLASSIFICATIONS` constant
   (move from `fact_bundle.py` lines 164-166).
2. Add the export to `src/novetest/models/__init__.py` mirroring
   `LocalizationFinding` / `CoverageFactSet`.
3. In `src/novetest/orchestration/recommendation/fact_bundle.py`:
   - **Delete** lines 159-189 (the `# Replay placeholder` section + the
     `REPLAY_CLASSIFICATIONS` constant + the placeholder `ReplayResult`
     class + its `__post_init__`).
   - **Replace** with a single `from novetest.models.replay_result import ReplayResult` near the top of the file (after the other model imports).
   - **Update** the module docstring "Replay placeholder" section
     (lines 20-31) to a one-paragraph note: "The canonical `ReplayResult`
     model lives at `models/replay_result.py` and was promoted by the
     Phase 5 entry slice; this module re-imports it so existing callers
     of `from ...fact_bundle import ReplayResult` continue to work." (Add the re-export `__all__` entry.)
4. The wire shape stays byte-identical: the 5 minimum fields are
   preserved, added fields are additive, the validation contract
   (`classification` in `REPLAY_CLASSIFICATIONS`) is preserved.
5. Verify nothing else imports the placeholder directly:
   `grep -rn "from .*fact_bundle import .*ReplayResult\|from novetest.orchestration.recommendation.fact_bundle import" src/ tests/`
   should show only test files (which keep working via the re-export)
   and `categories.py` (which imports through the same path).

This migration is **mechanical** — no behavior change, no API surface
change. The existing `TestFlakySuspected` mock tests under
`tests/unit/orchestration/recommendation/test_categories.py` continue
passing without modification.

---

## 3. Module layout

### `src/novetest/replay/`

```
__init__.py             # public exports: replay_run, get_replay_result,
                        # check_replay_availability, ReplayUnavailable
engine.py               # replay_run + helpers + N-rerun loop
context.py              # reconstruct_replay_context + ReplayContext dataclass
classifier.py           # classify_replay_consistency (pure)
retrieval.py            # get_replay_result + check_replay_availability
persistence.py          # replay_result_path + write_replay_result + read_replay_result
errors.py               # ReplayUnavailable + closed `reason` enum (your choice)
```

`__init__.py` exports mirror `coverage/__init__.py` /
`localization/__init__.py` patterns (the engines' public surface).

### `src/novetest/models/`

```
replay_result.py        # NEW — canonical ReplayResult dataclass + schema_version + to_dict/from_dict
__init__.py             # add ReplayResult export
```

### `src/novetest/cli/`

Two paths — your judgment. Per the working policy recorded in
`history/2026-06-02-phase1-and-phase6-complete-recommendation-synthesis-lands.md`
§Q3 ("inline by default, extract when ≥80 lines or ≥3 envelope outcomes"):

- **Recommended (inline)**: add `replay_cmd` to `cli/app.py` mirroring `inspect_cmd` / `localization_run`. The handler is ~3 outcomes (replay-result / unavailable / not-found), borderline. Inline is fine. If your handler grows past ~80 lines, migrate to `cli/handlers/replay.py` mid-cycle and adopt the `build_replay_envelope(outcome) -> (Envelope, exit_code)` pattern that `cli/handlers/test.py` introduced.
- **Drop the stub registration** at `cli/app.py:1182` (the `for _name in ("replay",): _register_flat_stub(_name)` loop). Replace `("replay",)` with `()` or delete the loop entirely if it's the only stub left.

### Touchpoints in already-shipped files

| File | Change |
|---|---|
| `src/novetest/cli/app.py` | Add `replay_cmd`; drop the stub registration |
| `src/novetest/orchestration/recommendation/fact_bundle.py` | Replace placeholder with `from novetest.models.replay_result import ReplayResult` re-export (per §2) |
| `src/novetest/orchestration/workflows/status.py` | Replace `replay_available=False` default with `replay_available=isinstance(get_replay_result(store, latest_ref), ReplayResult)` (cache-only); update the line 131 docstring comment from "Replay stays False" to a one-liner describing the new probe |
| `src/novetest/orchestration/workflows/inspect.py` | Add `replay_outcome` field to `InspectView` (mirroring `coverage_outcome` etc.); call `get_replay_result(store, ref)` in `build_inspect_view`; project via new `_replay_outcome_section` helper (the wire shape from §1.5); update `sub_reports.replay` to flip on `isinstance(..., ReplayResult)` instead of hard-coded `"unavailable"` |
| `src/novetest/models/__init__.py` | Add `ReplayResult` export |

**Do NOT touch**:
- `src/novetest/run/` (Replay reuses `execute_with_engine_context` unchanged)
- `src/novetest/memory/` (Replay consumes `store_run_evidence` / `retrieve_run_evidence` / `find_runs_for_target` unchanged)
- `src/novetest/coverage/`, `src/novetest/regression/`, `src/novetest/localization/` (no overlap)
- `src/novetest/orchestration/recommendation/{categories,templates,citations,synthesizer}.py` (the closed taxonomy is frozen; you do not bump it)
- `src/novetest/orchestration/workflows/test.py` (integrated `novetest test` stays Replay-free for this slice per §"Out of scope")

---

## 4. Fixture — `flaky-python/`

Add a deliberately non-deterministic test project under
`tests/fixtures/projects/flaky-python/`. Follow the existing pattern of
`pytest-basic/`, `pytest-failing/`, `localization-branch/`:

```
flaky-python/
  pyproject.toml          (minimal; project name "flaky_python")
  src/flaky_python/
    __init__.py
    flaky_module.py       (the source under test)
  tests/
    test_flaky_behavior.py
```

**Binding fixture rules**:
- The flaky test MUST be deterministic across the **process boundary** but non-deterministic across **subprocess invocations**. I.e. a single subprocess invocation produces a fixed outcome (so the original run is reproducible byte-identically for storage), but successive subprocess invocations of the *same test* produce divergent outcomes.
- The non-determinism source is **your design choice** (`--reruns` decision §6 may inform this). Record in handoff. Options worth considering:
  - Counter file on disk (each invocation reads the count, increments, decides outcome based on parity).
  - Environment variable read at test time (`NOVETEST_FLAKY_SEED=...` if set; otherwise time-based fallback).
  - `os.getpid() % 2` (cheap; non-deterministic across reruns; deterministic within a single subprocess).
  - `random.random()` with no seed (most realistic; AI agents see this in real codebases).
- **Reproducibility for `pytest-basic`** in the same slice is the regression-pin against accidentally making *all* runs look flaky — use the existing `pytest-basic/` fixture unchanged. A reused `pytest-basic` replay run should classify `reproducible` byte-identically over 5 reruns.

The fixture's test count should be small (1-3 tests) — it's a behavior fixture, not a coverage fixture.

**One additional fixture to consider** (your judgment — handoff records why):
`flaky-stale-target/` — a project state that breaks **after** the original run was captured (e.g. delete the test file before replay; the original ULID-path stored evidence remains valid, but the workspace can no longer resolve the test target). This is the `unable_to_replay` DoD bullet's fixture. Alternative: produce the `unable_to_replay` via the existing `empty-no-engine/` fixture for one of the `unable_to_replay` reasons. Document your fixture choice in the handoff so PM can map DoD bullet #3 evidence.

---

## 5. CLI — `novetest replay <run_id>` verb

### 5.1 Command signature

```
novetest replay <run_id> [--reruns N] [--timeout SECONDS] [--output text|json]
```

- `<run_id>` is the **original** run's `run_id` (a ULID string). The CLI handler resolves it via `memory/list_run_history` + `next(...)` (same pattern as `inspect_cmd`).
- `--reruns N` is the number of replay reruns. Default value: **your choice — see §6**.
- `--timeout` mirrors `run` / `test` (`--timeout 600` default per `run_cmd`).

### 5.2 Handler shape — mirror `test_cmd` (cli/app.py:1100-1162)

```
@app.command(name="replay")
def replay_cmd(run_id: str, *, reruns: int = <DEFAULT>, timeout: float = 600.0) -> None:
    # docstring per the convention used in test_cmd / inspect_cmd
    store = _require_store("replay")
    # Resolve original run_reference from run_id (mirror inspect_cmd's path).
    # On not-found: emit structured 'not-found' envelope (exit 2).
    # On engine-not-ready: emit EXIT_ENGINE_MISSING envelope (exit 4).
    outcome = asyncio.run(replay_run(store, original_ref, reruns=reruns, timeout=timeout))
    envelope, exit_code = _build_replay_envelope(original_ref, outcome)
    _emit_and_exit(envelope, exit_code)
```

### 5.3 Exit code map

| Outcome | Exit code |
|---|---|
| `ReplayResult` (any classification including `unable_to_replay`) | 0 |
| `ReplayUnavailable` (engine-not-ready / target-missing) | 4 |
| `ReplayUnavailable` (original-not-found) | 2 |
| `ReplayUnavailable` (tombstoned-original / context-reconstruction-failed) | 0 with `kind: unavailable` block; structured outcome, not error |
| Unhandled internal exception | 1 |

The split between "structured-unavailable at exit 0" vs "exit 2/4 with
error" is your judgment based on whether the situation is a **classify-able
outcome** (REQ-REP-003: `unable_to_replay` is a valid classification) or a
**user error** (bad run_id, missing engine). Document the split in the
handoff.

### 5.4 Default verb alias compatibility

The default-verb alias (Phase 6 entry slice) treats `novetest <token>`
as `novetest test <token>` only when `<token>` is NOT in the reserved
verb set. **`replay` is already in that reserved set**
(`cli/app.py::_inject_default_verb_alias` — check the verb list and add
`replay` if it's not there yet; the Phase 6 slice may have included it
preemptively). Verify with: `novetest replay /tmp/some_nonsense_path`
should route to the `replay` verb handler, NOT to `test`. Unit
test in `tests/unit/cli/test_default_verb_alias.py` should pin this.

---

## 6. Replay team's three policy decisions (delegated)

Per PM's Q3 default disposition, the following are **Replay team's
construction judgment** — decide based on practical engineering signal,
**record the decision + rationale + alternatives considered in the
handoff**. None of these is a frozen contract; all are v2-bumpable in a
future cycle.

### 6.1 `--reruns` default value

The delivery-phasing.md Phase 5 plan illustrates `--reruns=5` as an
example, not a binding default. Considerations:
- High N catches more flake patterns but multiplies wall-time cost (each rerun is a full native subprocess).
- N=1 is the cheapest single-replay default (matches `replay` Phase 5 plan example `novetest replay <run_id_of_basic>` which has no `--reruns` flag → implies default is 1 unless overridden).
- N=5 (the example value) lets the `inconsistent` classification have statistical signal (5 reruns ≥ 1 different = inconsistent; rate is meaningful).

PM's leaning (not binding): **`--reruns=1` as the default** for cheap
default cost + explicit `--reruns=5` when the user is investigating
flake. But if you find that N=5 default has a better UX argument
(e.g. "users running `novetest replay` likely want to investigate
flake, otherwise they would have run `novetest run` again"), make
that call and record the reasoning.

### 6.2 `classify_replay_consistency` threshold

For a multi-rerun replay session, classification thresholds:
- **Strict**: any non-matching rerun → `inconsistent`. (Highest sensitivity; even 1/5 different counts as flaky.)
- **Majority**: > 50% match original → `reproducible`; else `inconsistent`.
- **Per-test**: classify each test individually; the overall classification is the worst-case across tests.
- **All-or-nothing**: only 0/N differ → `reproducible`; any other partial → `inconsistent`.

PM's leaning (not binding): **strict** (any divergence triggers
`inconsistent`) because the user's mental model is "I want to know if
this run is reproducible; one flake is enough for the answer to be
no". But strict can be noisy if `--reruns` default is high — your call.
Record reasoning + the closed thresholding policy in the
`classify_replay_consistency` docstring AND the handoff.

### 6.3 `flaky-python/` fixture non-determinism source

See §4 options. **Your construction judgment.** Document.

---

## 7. Testing scope

### 7.1 Unit tests under `tests/unit/replay/`

Mirror `tests/unit/localization/` / `tests/unit/regression/` structure:

```
tests/unit/replay/
  __init__.py
  test_engine.py            # replay_run + N-rerun loop happy paths
  test_context.py           # reconstruct_replay_context: success + 4-5 unavailable reasons
  test_classifier.py        # classify_replay_consistency: all 3 classifications + edge cases (0 reruns, partial divergence)
  test_persistence.py       # path / write / read round-trip; cache-only retrieval semantics
  test_retrieval.py         # get_replay_result + check_replay_availability discriminator behavior
  test_errors.py            # ReplayUnavailable validation + closed-reason enum
```

`classify_replay_consistency` is a **pure** function — exhaustive table
tests are cheap and valuable; pin the threshold policy (§6.2) in the
test bodies so future v2 changes are explicit.

### 7.2 Integration test under `tests/integration/replay/`

```
tests/integration/replay/
  __init__.py
  test_replay_e2e.py        # canonical 3-DoD-bullet integration
  test_flaky_suspected_synthesis.py  # NEW: end-to-end check that flaky_suspected
                                     # fires via the synthesizer when a real
                                     # ReplayResult is built from this engine
```

**`test_replay_e2e.py` covers the 3 DoD bullets**:

1. `test_flaky_python_with_reruns_5_yields_inconsistent` — materializes `flaky-python/`; runs `novetest run --coverage tests/`; then `novetest replay <run_id> --reruns=5`; asserts `classification == "inconsistent"`, `reruns_total == 5`, `reruns_failed >= 1`, replayed Run Records exist in Memory, citation round-trip resolves.
2. `test_pytest_basic_yields_reproducible` — materializes `pytest-basic/` (existing fixture); runs once; then `novetest replay <run_id>` (use a `--reruns=3` or per-§6.1 default that's > 1 — the contract is "no divergence in any rerun"); asserts `classification == "reproducible"`.
3. `test_replay_with_missing_target_yields_unable_to_replay` — materializes a fixture (your §4 choice — `flaky-stale-target/` or equivalent); runs once; then mutates workspace (delete the test file / corrupt the engine); then `novetest replay <run_id>`; asserts `classification == "unable_to_replay"`, `reason` is one of your closed-reason enum, exit code 0 (structured outcome).

**`test_flaky_suspected_synthesis.py` activates the category for real**:

```
def test_flaky_suspected_fires_when_replay_result_inconsistent(tmp_path) -> None:
    # End-to-end NFR-ORCH-002 evidence: flaky_suspected category fires
    # when a real ReplayResult (produced by the Replay engine) is included
    # in a FactBundle and synthesized.
    #
    # 1. Run pipeline: pytest-failing or flaky-python fixture → novetest run → novetest replay
    # 2. Build FactBundle manually (mirroring workflows/test.py's pattern) with the
    #    real ReplayResult instance from this slice's engine.
    # 3. Call synthesize_recommendation(bundle).
    # 4. Assert: at least one recommendation has category == "flaky_suspected".
    # 5. Assert: that recommendation's evidence_citations carries kind="replay_result".
    # 6. Assert: the citation's selector resolves via get_replay_result(store, original_ref)
    #    to the same ReplayResult byte-identically (round-trip per NFR-ORCH-002).
    ...
```

This is the **load-bearing slice deliverable** — it proves the
`flaky_suspected` category is no longer mock-only.

### 7.3 Snapshot tests via `syrupy`

Pin one envelope per classification under
`tests/integration/cli/__snapshots__/test_replay_envelope.ambr`:
- `inconsistent` against `flaky-python`
- `reproducible` against `pytest-basic`
- `unable_to_replay` against your stale-target fixture

Match the convention from `tests/integration/orchestration/__snapshots__/test_test_workflow.ambr`.

### 7.4 Cross-test updates

- `tests/unit/orchestration/recommendation/test_categories.py::TestFlakySuspected` — **no change required**; the mock-based unit tests continue passing (they import `ReplayResult` via the re-export from `fact_bundle.py`).
- `tests/unit/orchestration/workflows/test_status.py` — add a case that seeds a `replay_result.json` and asserts `status.sub_reports.replay == "available"` (mirrors Defect-6 close pattern).
- `tests/unit/orchestration/workflows/test_inspect.py` — add a case asserting the new `replay_outcome` block surfaces with `kind: replay-result` when on disk.
- `tests/integration/cli/test_subcommand_stubs.py` — drop `replay` from the pinned-stubs list (mirror what Phase 6 entry did for `test`).
- `tests/unit/cli/test_default_verb_alias.py` — add a case asserting `novetest replay <run_id>` routes to the `replay` verb, NOT `test` (reserved-verb disambiguation).

---

## 8. NFR-REP-001 + NFR-REP-002 verification

**NFR-REP-001** (Replay-result traceability): Every persisted
`replay_result.json` carries `original_run_reference` AND (when
applicable) `replayed_run_reference`. The Memory entry for the replay
run carries this back-link via the standard `RunRecord.run_reference`
mechanism. Verified by `test_persistence.py` round-trip.

**NFR-REP-002** (≤ 3 s classification AFTER replay execution Run
Record becomes available): The "after replay execution Run Record
becomes available" wording matters — the 3 s budget covers `read
replayed RunRecord from disk + classify_replay_consistency + persist
ReplayResult`. It does NOT cover the rerun subprocess execution itself
(which is dominated by native test cold start). Add a perf-style
assertion (not a perf suite — just an in-process timer in the e2e
integration test):

```
import time
t0 = time.perf_counter()
result = classify_replay_consistency(original_record, replayed_records)
write_replay_result(store, original_ref, result)
elapsed = time.perf_counter() - t0
assert elapsed < 3.0, f"NFR-REP-002 violated: {elapsed:.3f}s"
```

This is a smoke pin, not a perf benchmark. If you find classifier
performance is dominated by something expensive (large per-test-result
arrays?), pin a real perf test under `tests/perf/replay/` mirroring
`tests/perf/localization/`. PM's expectation: classifier is dominated
by JSON write + record parsing, both O(< 100 ms) — perf test is
defensive.

---

## 9. Out of scope (do not do)

- **SQLite anything.** No `import sqlite3`. No `.novetest/memory/index.db`. No `memory/migrations/`. Period. See `decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md`.
- **`novetest reindex` verb.** Not in this slice. Reopens when SQLite ships in a future cycle.
- **Integrated `novetest test` Replay invocation.** Phase 6 entry's `workflows/test.py` keeps `replay_result=None`. A future cycle decides whether `novetest test` auto-runs Replay (it's a separate UX question — extra cost vs extra value).
- **Cross-run flakiness rate** ("nodeid X across last N runs"). That's the post-MVP verb that reopens the SQLite decision.
- **`recommendation_schema_version` v2 changes.** Closed taxonomy is frozen at v1; the `flaky_suspected` category is structurally part of v1 already (Phase 6 entry).
- **MCP transport.** Phase 7 territory.
- **Coverlet / JUnit adapters.** Open-Q-gated; separate cycles.
- **`failure_proximity` warning loop polish.** Defect 7 deferred.
- **Memory `delete` polish.** Long-standing carry-forward.

---

## 10. File map (estimate)

**New files (~10-12)**:
- `src/novetest/models/replay_result.py` (~120 lines)
- `src/novetest/replay/__init__.py` (~30 lines exports)
- `src/novetest/replay/engine.py` (~180 lines)
- `src/novetest/replay/context.py` (~120 lines)
- `src/novetest/replay/classifier.py` (~150 lines pure logic + thresholds)
- `src/novetest/replay/retrieval.py` (~80 lines)
- `src/novetest/replay/persistence.py` (~100 lines)
- `src/novetest/replay/errors.py` (~60 lines: ReplayUnavailable + closed reason enum)
- `tests/fixtures/projects/flaky-python/` (project layout)
- `tests/fixtures/projects/flaky-stale-target/` if you choose that path
- 6 unit test files under `tests/unit/replay/`
- 2 integration test files under `tests/integration/replay/`
- 1 snapshot file `tests/integration/cli/__snapshots__/test_replay_envelope.ambr`

**Modified files (~6-7)**:
- `src/novetest/cli/app.py` — `replay_cmd` handler + stub removal
- `src/novetest/orchestration/recommendation/fact_bundle.py` — placeholder removal + re-export
- `src/novetest/orchestration/workflows/status.py` — `replay_available` real probe
- `src/novetest/orchestration/workflows/inspect.py` — `replay_outcome` section
- `src/novetest/models/__init__.py` — `ReplayResult` export
- `tests/integration/cli/test_subcommand_stubs.py` — drop `replay` from stubs
- `tests/unit/cli/test_default_verb_alias.py` — add `replay` reserved-verb case

**Estimated source-file count delta**: +8-10 (current 80 → ~88-90).

**Estimated test count delta**: +50-70 net new tests.

---

## 11. Definition of Done

1. **5 Replay internal APIs implemented + unit-pinned** per §1.2 — engine.py / context.py / classifier.py / retrieval.py / persistence.py.
2. **`ReplayResult` model promoted** to `src/novetest/models/replay_result.py` per §1.1 + `fact_bundle.py` placeholder removed cleanly per §2.
3. **`novetest replay <run_id>` CLI verb** implemented per §5; stub removed from `cli/app.py:1182`; exit code map per §5.3.
4. **DoD bullet 1** (`delivery-phasing.md:221`): `novetest replay <run_id_of_flaky> --reruns=5` produces `inconsistent` — pinned by `test_replay_e2e.py::test_flaky_python_with_reruns_5_yields_inconsistent`.
5. **DoD bullet 2** (`delivery-phasing.md:222`): `novetest replay <run_id_of_basic>` produces `reproducible` — pinned by `test_replay_e2e.py::test_pytest_basic_yields_reproducible`.
6. **DoD bullet 3** (`delivery-phasing.md:223`): missing-target run produces `unable_to_replay` — pinned by `test_replay_e2e.py::test_replay_with_missing_target_yields_unable_to_replay`.
7. **`flaky_suspected` category fires for real** — pinned by `test_flaky_suspected_synthesis.py`.
8. **Status / Inspect activate Replay surface** — `status.sub_reports.replay` flips on cache hit; `inspect.replay_outcome` carries the discriminated block.
9. **NFR-REP-001 + NFR-REP-002 verified** — round-trip pin + ≤ 3 s classifier smoke per §8.
10. **Default suite green**: `uv run pytest -q tests/unit tests/integration` passes.
11. **mypy strict clean**: `uv run mypy --strict src` passes.
12. **No SQLite anywhere** — `grep -rn "sqlite3\|index.db" src/novetest/replay/ src/novetest/models/replay_result.py` returns empty.
13. **PM ticks `delivery-phasing.md:221-223` at cycle close** + writes the cycle history entry.

---

## 12. Handoff format

Write `agent-comms/handoffs/replay-team-2026-06-02-phase5-entry-replay-engine.md` with:

- Worktree path, commit count, files added/modified summary.
- `uv run pytest -q tests/unit tests/integration` baseline + post-slice counts (skipped delta acknowledged).
- `uv run mypy --strict src` source-file count delta.
- **Three §6 policy decisions** captured verbatim: `--reruns` default, `classify_replay_consistency` threshold, `flaky-python/` non-determinism source — each with rationale + alternatives considered + v2-bumpable note.
- **§5.3 exit-code split rationale** (which `ReplayUnavailable.reason` values exit 0 vs 2 vs 4).
- **Closed `ReplayUnavailable.reason` enum** as shipped (the final list of strings).
- **§1.1 ReplayResult fields shipped** (the 5 binding + which optional fields you chose to include).
- **Per-fixture envelope pins** (verbatim captures):
  - `flaky-python` after `novetest replay <id> --reruns=5` → classification, reruns_total, reruns_failed, per_rerun_outcomes, consistency_summary, citation kinds.
  - `pytest-basic` reproducible.
  - `unable_to_replay` envelope.
- **NFR-REP-002 measured time** (median of 5 runs of `classify_replay_consistency` + persist).
- **DoD bullets believed closed** explicit list: `delivery-phasing.md:221-223` (3 bullets) — PM verifies + ticks at cycle close.
- **`fact_bundle.py` placeholder removal** confirmed via grep:
  `grep -rn "REPLAY_CLASSIFICATIONS\|class ReplayResult" src/` should show only `src/novetest/models/replay_result.py` definitions (no placeholder remains).
- **Citation round-trip** confirmed: the `flaky_suspected` recommendation's `replay_result` citation resolves via `get_replay_result(store, original_ref)` to the same `ReplayResult` byte-identically (NFR-ORCH-002 evidence).
- **5 Gotchas worth pinning** for the cycle history (mirror Phase 6 entry handoff format — surprises, non-obvious traps, recurring patterns).
- **Open questions / parking lot** — any v2-bumpable thoughts you encountered (e.g. "the strict threshold causes high false-positive rate on the `pytest-basic` fixture when the user's system has noisy concurrency; consider majority-threshold in v2"). These go to PM for forward-looking decisions; NOT in scope for this slice.

---

## 13. Cycle close (PM responsibility — informational)

After Main Branch FF-merges your worktree + Manual Test verifies + PM
ticks DoD:

- `delivery-phasing.md:221-223` flipped from `[ ]` to `[x]` with cycle history reference.
- `agent-comms/history/2026-06-02-phase5-complete-replay-engine.md` written.
- Phase progress map updated: **Phase 5 → 100% complete.**
- MVP scope reduces to: Phase 3 JUnit (Open Q #5) + Phase 3 .NET (Open Q #4) + Phase 7 MCP (post-MVP).
- v1 recommendation surface complete — all 7 categories of the closed taxonomy can fire against real data.

After this cycle, the project's binding question becomes: **MVP release?**
With Phase 5 done, the remaining gates are the two Open-Q-blocked
adapters (which require CEO investigation on Coverlet config + JUnit
Console Launcher vendoring policy) — that's a CEO decision, not a brief
scoping question.

---

## End of brief
