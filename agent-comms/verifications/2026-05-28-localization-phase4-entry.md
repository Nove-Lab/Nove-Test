---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-05-28
slug: localization-phase4-entry
related:
  - agent-comms/handoffs/localization-team-2026-05-28-phase4-entry.md
  - agent-comms/tasks/localization-team-2026-05-28-phase4-entry.md
  - design/implementation-plan/localization-strategy.md
  - design/interace-contract/localization.md
---

# Verification: Phase 4 entry — Localization engine (per-test SBFL path)

## Merge

- **Merged commits (linear history, rebased onto `adf7bac`):**
  - `bbb0356 feat(localization): SBFL engine surface + per-test path (Phase 4 entry)`
  - `bb6cc29 comms: handoff for Phase 4 entry Localization engine slice`
- **Branch (now deleted):** `localization-team/phase4-entry`.
- **Source handoff:** `agent-comms/handoffs/localization-team-2026-05-28-phase4-entry.md`.
- **Conflicts resolved:** `WORKLOG.md` only — both sibling slices added a 2026-05-28 top entry. Resolved by keeping both: Localization entry on top (newest), gotest below it, no `---` separator between them (the file uses `---` only at the meta-header and at archive boundaries). No code-level conflicts.

## Gate (run on merged tip `bb6cc29`)

- `uv run pytest -q tests/unit tests/integration` → **588 passed, 3 skipped, 1 snapshot** (the 3 skipped are the pre-existing Node-dependent jest integration tests). Localization contributed +87 tests.
- `uv run mypy` → **clean, 69 source files** (`--strict`). Localization contributed +11 source files.

## What landed

- **11 new src files** under `src/novetest/localization/` + 1 model (`src/novetest/models/localization_finding.py`) + 1 model-index re-export + `numpy>=1.26` runtime dependency (`pyproject.toml`).
- Public surface: `derive_localization_findings`, `get_localization_findings`, `check_localization_availability`, `LocalizationUnavailable`, the 4 `REASON_*` constants + `KNOWN_REASONS`, and the dataclass tree (`CodeLocation` / `EvidenceCitation` / `LocalizationEntry` / `LocalizationFinding`).
- **No CLI surface yet** — engine-only slice (mirrors the Regression engine's pre-CLI pattern). Manual Test fields via Python REPL.
- Phase 4 DoD bullets `[186-189]` do NOT close from this slice; they require the CLI + the two degraded modes.

## Wire shape pinned on merged tip (real `derive_localization_findings` on the new `localization-branch` fixture)

Probed against the new fixture (`tests/fixtures/projects/localization-branch/`) via `novetest init && novetest run --coverage tests/` + `derive_localization_findings(store, ref)`. The fixture's `divide()` has a deliberate one-line bug; one test fails; per-test attribution makes `divide` the unique top-rank under Ochiai.

### `LocalizationFinding.to_dict()` top-level keys (12, ordered)

```
schema_version, run_reference, engine_name, ecosystem, mode, confidence,
formula, alternate_scores_available, top_n, entries, derived_at, metadata
```

Observed values:
```
schema_version              = 1
run_reference               = {schema_version, run_id, created_at}  (RunReference.to_dict)
engine_name                 = "pytest"
ecosystem                   = "python"
mode                        = "sbfl_per_test"
confidence                  = "high"
formula                     = "ochiai"             ← default presentation formula
alternate_scores_available  = ["dstar2", "op2", "tarantula"]   ← LIST OF STRINGS, NOT a bool
top_n                       = 10
entries                     = [LocalizationEntry.to_dict(), ...]  (length ≤ top_n)
derived_at                  = <epoch_millis_int>
metadata                    = {} or {<engine-specific keys>}
```

**Pin: `alternate_scores_available` is `list[str]` enumerating the other formulas computed.** The handoff doc described this as a bool — the doc was wrong; the actual field type is `tuple[str, ...]` and `to_dict()` emits it as a JSON array. (Source: `src/novetest/models/localization_finding.py:309`, validated by `__post_init__:332`.)

### `LocalizationEntry.to_dict()` keys (9, ordered)

```
rank, tied_with, code_location, score_raw, score_normalized, formula,
alternate_scores, related_failed_tests, evidence_citations
```

Observed top entry from the fixture (rank 1, the buggy `divide`):
```json
{
  "rank": 1,
  "tied_with": ["entry_index_1"],
  "code_location": {
    "kind": "symbol",
    "file": "localization_branch/calculator.py",
    "symbol": "divide",
    "line_range": [31, 34],
    "primary_line": 34,
    "evidence_lines": [34]
  },
  "score_raw": 1.0,
  "score_normalized": 1.0,
  "formula": "ochiai",
  "alternate_scores": {"op2": 1.0, "dstar2": 0.0, "tarantula": 1.0},
  "related_failed_tests": ["tests/test_calculator.py::test_divide_yields_quotient"],
  "evidence_citations": [
    {"kind": "test_result", "run_reference": {...}, "selector": {"test_id": "...", "outcome": "failed"}},
    {"kind": "coverage_fact", "run_reference": {...}, "selector": {"file": "...", "lines": [34]}}
  ]
}
```

### `CodeLocation.to_dict()` keys (6, ordered)

```
kind, file, symbol, line_range, primary_line, evidence_lines
```

- `kind ∈ {"symbol", "file", "line", "branch"}` — closed enum (`CODE_LOCATION_KINDS`). Only `symbol` and `file` are produced today; `line` and `branch` are reserved.
- `symbol`, `line_range`: `null` when `kind == "file"`. `line_range` is `[start, end]` (1-based, inclusive) when present.
- `evidence_lines`: array of ints (capped at 10 entries — `_EVIDENCE_LINE_CAP=10` in `derive.py`).

### `EvidenceCitation.to_dict()` keys (3, ordered)

```
kind, run_reference, selector
```

- `kind ∈ {"test_result", "coverage_fact"}` — closed enum (`EVIDENCE_KINDS`).
- `selector` is discriminated:
  - `test_result` → `{"test_id": <node_id>, "outcome": "failed"}`
  - `coverage_fact` → `{"file": <relative_path>, "lines": [<int>, ...]}`

### `LocalizationUnavailable` — **NO `to_dict()`**

Unlike `RegressionUnavailable`, `LocalizationUnavailable` does NOT have a `to_dict()` method. The dataclass fields (Python-only surface):

```
run_reference: RunReference | None
reason: str           ← one of KNOWN_REASONS
detail: str | None
```

`KNOWN_REASONS` (verbatim, sorted, 4 entries):
```
{"no_coverage", "no_failed_tests", "no_run_evidence", "run_not_analyzable"}
```

The reason constants are exposed as module attributes:
```
REASON_NO_FAILED_TESTS    = "no_failed_tests"
REASON_NO_COVERAGE        = "no_coverage"
REASON_NO_RUN_EVIDENCE    = "no_run_evidence"
REASON_RUN_NOT_ANALYZABLE = "run_not_analyzable"
```

### Persistence path (load-bearing per `src/novetest/memory/store.py:_availability_flags`)

```
<store>/localization/findings/run_<run_id>/localization_findings.json
```

Confirmed observed: `.novetest/localization/findings/run_01KSPGG5HTBMQZWRCDH7VDXPRJ/localization_findings.json`.

### Closed enums (sorted) — from `src/novetest/models/localization_finding.py`

```
FORMULAS                 = {"dstar2", "ochiai", "op2", "tarantula"}     ← "dstar2", NOT "dstar"
LOCALIZATION_MODES       = {"failure_proximity", "sbfl_aggregate", "sbfl_per_test"}
LOCALIZATION_CONFIDENCES = {"high", "low", "medium"}
CODE_LOCATION_KINDS      = {"branch", "file", "line", "symbol"}
EVIDENCE_KINDS           = {"coverage_fact", "test_result"}
```

## Verification steps for Manual Test

### Setup — one-time helper

```bash
WS=$(mktemp -d)
cp -r tests/fixtures/projects/localization-branch/* "$WS"/
(cd "$WS" && uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init >/dev/null)
(cd "$WS" && uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run --coverage tests/) > "$WS"/run.json
echo "Workspace: $WS"
```

### 1. Happy-path derive (per-test SBFL, Ochiai)

```bash
uv run --project /home/yjshin/dev/aispace/Nove-Test python3 - <<PY
import json
from pathlib import Path
from novetest.memory.project_store import get_project_store_state
from novetest.localization.derive import derive_localization_findings
from novetest.models.run_reference import RunReference

ws = Path("$WS")
store = get_project_store_state(ws / ".novetest")
rr = json.loads((ws / "run.json").read_text())["data"]["memory_entry"]["run_record"]["run_reference"]
ref = RunReference(run_id=rr["run_id"], created_at=rr["created_at"])

finding = derive_localization_findings(store, ref)
d = finding.to_dict()
print("type:", type(finding).__name__)
print("top-level keys:", list(d.keys()))
print("mode:", d["mode"], "confidence:", d["confidence"], "formula:", d["formula"])
print("alternate_scores_available:", d["alternate_scores_available"])
print("top_n:", d["top_n"], "entries:", len(d["entries"]))
print("rank-1 symbol:", d["entries"][0]["code_location"]["symbol"], "score_raw:", d["entries"][0]["score_raw"])
PY
```

Expected:
- `type == LocalizationFinding`
- `top-level keys` exactly matches the 12-key list above.
- `mode == "sbfl_per_test"`, `confidence == "high"`, `formula == "ochiai"`.
- `alternate_scores_available == ["dstar2", "op2", "tarantula"]` (list of strings, NOT bool).
- `entries[0].code_location.symbol == "divide"` with `score_raw == 1.0`.

### 2. On-disk JSON round-trip

```bash
RUN_ID=$(jq -r '.data.memory_entry.run_record.run_reference.run_id' "$WS"/run.json)
ls -la "$WS"/.novetest/localization/findings/run_"$RUN_ID"/
jq '. | {keys: keys, mode, confidence, formula, alternate_scores_available, entries_count: (.entries | length)}' \
  "$WS"/.novetest/localization/findings/run_"$RUN_ID"/localization_findings.json
```

Expected: directory exists with exactly one file `localization_findings.json`; JSON content matches step 1's `d` exactly.

### 3. Cache-hit preserves `derived_at`

```bash
uv run --project /home/yjshin/dev/aispace/Nove-Test python3 - <<PY
import json
from pathlib import Path
from novetest.memory.project_store import get_project_store_state
from novetest.localization.retrieval import get_localization_findings
from novetest.localization.derive import derive_localization_findings
from novetest.models.run_reference import RunReference

ws = Path("$WS")
store = get_project_store_state(ws / ".novetest")
rr = json.loads((ws / "run.json").read_text())["data"]["memory_entry"]["run_record"]["run_reference"]
ref = RunReference(run_id=rr["run_id"], created_at=rr["created_at"])

a = derive_localization_findings(store, ref)           # fresh derive
b = get_localization_findings(store, ref)              # cache read
c = derive_localization_findings(store, ref)           # second derive (cache hit short-circuit)
print("get derived_at == derive derived_at:", b.derived_at == a.derived_at)
print("re-derive derived_at == original  :", c.derived_at == a.derived_at)
PY
```

Expected: both `True`. The cache short-circuit must not re-time the derivation.

### 4. Memory `has_localization_findings` flag flip

```bash
uv run --project /home/yjshin/dev/aispace/Nove-Test python3 - <<PY
import json
from pathlib import Path
from novetest.memory.project_store import get_project_store_state
from novetest.memory.store import retrieve_run_evidence
from novetest.models.run_reference import RunReference

ws = Path("$WS")
store = get_project_store_state(ws / ".novetest")
rr = json.loads((ws / "run.json").read_text())["data"]["memory_entry"]["run_record"]["run_reference"]
ref = RunReference(run_id=rr["run_id"], created_at=rr["created_at"])

entry = retrieve_run_evidence(store, ref)
print("has_localization_findings:", entry.has_localization_findings)
PY
```

Expected: `True` (after step 1 has run). The Memory `_availability_flags` probe substring-matches `run_<rid>/localization_findings.json` on disk.

### 5. Exercise each `LocalizationUnavailable` reason

**`no_failed_tests`** — derive against a Run with all-passing tests (synthesize via REPL; or use a workspace where `test_divide_yields_quotient` is xfailed; or seed via `store_run_evidence` with only passing TestResults).

**`no_coverage`** — re-run the fixture WITHOUT `--coverage` and call derive:
```bash
WS2=$(mktemp -d) && cp -r tests/fixtures/projects/localization-branch/* "$WS2"/
(cd "$WS2" && uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init >/dev/null)
(cd "$WS2" && uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run tests/) > "$WS2"/run.json   # no --coverage
uv run --project /home/yjshin/dev/aispace/Nove-Test python3 - <<PY
import json
from pathlib import Path
from novetest.memory.project_store import get_project_store_state
from novetest.localization.derive import derive_localization_findings
from novetest.localization.results import LocalizationUnavailable
from novetest.models.run_reference import RunReference

ws = Path("$WS2")
store = get_project_store_state(ws / ".novetest")
rr = json.loads((ws / "run.json").read_text())["data"]["memory_entry"]["run_record"]["run_reference"]
ref = RunReference(run_id=rr["run_id"], created_at=rr["created_at"])
result = derive_localization_findings(store, ref)
assert isinstance(result, LocalizationUnavailable)
print("reason:", result.reason)
print("detail:", result.detail)
PY
```

Expected (observed on merge box): `reason == "no_coverage"`, `detail == "coverage facts unavailable; failure_proximity mode is not yet implemented (Phase 4 follow-up)"`.

**`no_run_evidence`** — derive against a fake `RunReference`:
```bash
uv run --project /home/yjshin/dev/aispace/Nove-Test python3 - <<PY
from pathlib import Path
from novetest.memory.project_store import get_project_store_state
from novetest.localization.derive import derive_localization_findings
from novetest.localization.results import LocalizationUnavailable
from novetest.models.run_reference import RunReference

store = get_project_store_state(Path("$WS") / ".novetest")
fake = RunReference(run_id="01FAKEFAKEFAKEFAKEFAKEFAKE", created_at=1700000000_000)
result = derive_localization_findings(store, fake)
print("type:", type(result).__name__, "reason:", result.reason)
PY
```

Expected: `LocalizationUnavailable` with `reason == "no_run_evidence"`.

**`run_not_analyzable`** — tombstone the Run Record and re-derive (Manual Test should know the tombstone-write helper from prior Regression cycles). Alternatively, call `get_localization_findings` BEFORE deriving — the cache-absence path overloads `run_not_analyzable` with `detail == "findings not yet derived"`:
```bash
WS3=$(mktemp -d) && cp -r tests/fixtures/projects/localization-branch/* "$WS3"/
(cd "$WS3" && uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init >/dev/null)
(cd "$WS3" && uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run --coverage tests/) > "$WS3"/run.json
uv run --project /home/yjshin/dev/aispace/Nove-Test python3 - <<PY
import json
from pathlib import Path
from novetest.memory.project_store import get_project_store_state
from novetest.localization.retrieval import get_localization_findings
from novetest.localization.results import LocalizationUnavailable
from novetest.models.run_reference import RunReference

ws = Path("$WS3")
store = get_project_store_state(ws / ".novetest")
rr = json.loads((ws / "run.json").read_text())["data"]["memory_entry"]["run_record"]["run_reference"]
ref = RunReference(run_id=rr["run_id"], created_at=rr["created_at"])
# Call get_localization_findings WITHOUT first calling derive — cache empty:
r = get_localization_findings(store, ref)
print("type:", type(r).__name__, "reason:", r.reason, "detail:", r.detail)
PY
```

Expected: `LocalizationUnavailable`, `reason == "run_not_analyzable"`, `detail == "findings not yet derived"` (the deliberate overload documented in `retrieval.py:51`).

### 6. `check_localization_availability` cheap probe

```bash
uv run --project /home/yjshin/dev/aispace/Nove-Test python3 - <<PY
import json
from pathlib import Path
from novetest.memory.project_store import get_project_store_state
from novetest.localization.retrieval import check_localization_availability
from novetest.models.run_reference import RunReference

ws = Path("$WS")
store = get_project_store_state(ws / ".novetest")
rr = json.loads((ws / "run.json").read_text())["data"]["memory_entry"]["run_record"]["run_reference"]
ref = RunReference(run_id=rr["run_id"], created_at=rr["created_at"])
print("check_localization_availability ($WS, with-coverage):", check_localization_availability(store, ref))
PY
```

Expected: `True` (fixture has 1 failed test + per-test coverage). Try the same against `$WS2` (no `--coverage`): expect `False`.

## Critical edge cases worth probing (per handoff §"Observed behaviors")

- **`tied_with` references INSIDE top_n only** — synthesize a >10-way tie and confirm a tie that straddles the top_n=10 boundary loses references to dropped half. The current behavior is intentional (per design) but PM may want a richer handle when freezing. Manual Test: report a concrete count of dropped references on a contrived fixture if possible.
- **`primary_line` tiebreak**: when multiple lines in a symbol share max Ochiai score, `primary_line` is the LOWEST-numbered line. Tiebreak rule = `(-score, line)` ascending. Hard to probe without crafting a multi-failure fixture; report if you do.
- **`evidence_lines` capped at 10**: a 200-line function with 50 suspicious lines reports the top 10. Not surfaced in the wire schema; flag if this surprises an AI consumer.
- **File-level fallback** (`kind == "file"`): module-level code OR non-Python files yield `CodeLocation(kind="file")` with `symbol=null, line_range=null` but populated `primary_line` and `evidence_lines`. Today the symbol-level path dominates for Python fixtures; the file-level path is rare.
- **`score_normalized` is min-max over the FULL ranking** — NOT over the truncated top_n. So top-1's `score_normalized` may be `< 1.0` if a higher-score candidate exists outside top_n (extremely rare in practice; report if you trip it).
- **The integration test fixture's rank-1 symbol is `divide`** with `score_raw == 1.0` AND a tie (`tied_with == ["entry_index_1"]`). Confirm the tied entry at index 1 is `localization_branch.calculator.divide` or another suspect — and report what the tied entry actually is, so PM can document the expected fixture behavior.

## Schema decisions PM should freeze in a follow-up `decisions/` entry

Per the handoff §"Schema decisions PM should freeze": after Manual Test fields these, PM should freeze a `decisions/2026-05-XX-localization-finding-shape.md` entry pinning:

1. The 12-key `LocalizationFinding.to_dict()` shape above.
2. The 9-key `LocalizationEntry.to_dict()` shape above.
3. The 6-key `CodeLocation.to_dict()` shape + 4-element `CODE_LOCATION_KINDS` enum.
4. The 3-key `EvidenceCitation.to_dict()` shape + discriminated selector + 2-element `EVIDENCE_KINDS` enum.
5. `LocalizationUnavailable` fields + 4-reason closed enum (`KNOWN_REASONS`). **Decide whether to keep the `run_not_analyzable` overload for the cache-not-populated path** or add a dedicated `REASON_MISSING_DERIVED_FACTS` (mirrors Coverage / Regression).
6. The `tied_with` convention (`entry_index_<i>` strings, 0-based into truncated top_n).
7. The persistence path `<store>/localization/findings/run_<run_id>/localization_findings.json` (already implicit in Memory's `_availability_flags` probe).

## Phase progress

- Phase 4 entry: Localization engine surface (per-test SBFL path only).
- **No `delivery-phasing.md` `- [ ]` bullets close from this slice** — Phase 4 bullets `[186-189]` all require the CLI surface + the two degraded modes (`sbfl_aggregate`, `failure_proximity`); this slice is the engine foundation only.
- Next slices: aggregate-mode, proximity-mode, `resolve_latest_analyzable_run` + `derive_latest_localization`, then the Orchestration CLI (`novetest localization <run_id>` / `novetest localization latest` / `inspect` section).
