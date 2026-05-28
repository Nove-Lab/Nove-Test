---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-05-28
slug: run-gotest-adapter
related:
  - agent-comms/handoffs/run-team-2026-05-28-gotest-adapter.md
  - agent-comms/tasks/run-team-2026-05-28-gotest-adapter.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
---

# Verification: `go test` Native Engine adapter — Phase 3 adapter #1

## Merge

- **Merged commit:** `adf7bac feat(run): add `go test` Native Engine adapter (Phase 3 adapter #1)` (fast-forward from `4be6c7c`).
- **Branch (now deleted):** `run-team/gotest-adapter`.
- **Source handoff:** `agent-comms/handoffs/run-team-2026-05-28-gotest-adapter.md`.
- **Conflicts:** none for this slice (clean fast-forward). The `WORKLOG.md` 2026-05-28 collision happened only when the sibling Localization slice was rebased on top of `adf7bac` — resolved in that slice's verification.

## Gate (run on merged `bb6cc29` tip — the union of gotest + localization)

- `uv run pytest -q tests/unit tests/integration` → **588 passed, 3 skipped, 1 snapshot** (the 3 skipped are the pre-existing Node-dependent jest integration tests).
- `uv run mypy` → **clean, 69 source files** (`--strict`).
- Local Go on the merge box: `go1.18.1` — the two new Go integration tests RAN locally (didn't skip) and passed.

## What landed

- New adapter `src/novetest/run/adapters/gotest_adapter.py` (~395 lines): spawns `go test -json -count=1 -timeout=<N>s [-cover ...] <target>`, stream-parses NDJSON, writes per-test failure logs to `<artifact_dir>/native/failures/<safe>.log`, registers `events.jsonl` AND `cover.out` as artifacts. Child env pins `GOFLAGS=-mod=readonly`, `GOTOOLCHAIN=local`, `NO_COLOR=1`.
- Wire-up: `run/engine.py` dispatches on `engine_name == "go-test"`; `run/engine_selector.py` maps `"go" → "go-test"`; `run/readiness.py` adds `_assess_gotest_readiness`; `run/normalizer.py` adds `_normalize_gotest_payload` + `_aggregate_gotest_status`.
- 2 new fixture trees: `tests/fixtures/projects/gotest-basic/` (one passing + one intentionally failing + parent with two passing subtests = 5 terminal events) and `gotest-basic-coverage/` (4 passing + intentionally uncovered branch in `Classify`).
- 30 net new tests (16 adapter unit + 7 normalizer + 3 readiness + 1 engine-selector + 1 engine dispatch + 2 integration).

## Wire shape pinned on merged tip (`novetest run` against `gotest-basic`)

Probed in a tmp workspace via `cp -r tests/fixtures/projects/gotest-basic/* . && novetest init && novetest run`. Top-level envelope is the standard Run envelope; the Go-specific fields are:

```text
data.memory_entry.run_record.engine_name        = "go-test"      ← NOT "go"
data.memory_entry.run_record.engine_version     = "1.18.1"       ← parsed from `go version`
data.memory_entry.run_record.ecosystem          = "go"
data.memory_entry.run_record.target_type        = "workspace"
data.memory_entry.run_record.status             = "failed"       ← because TestSubtract fails by design
data.memory_entry.run_record.summary_counts     = {"failed": 1, "passed": 4, "skipped": 0, "total": 5}
data.memory_entry.run_record.artifact_paths     keys = ["gotest_events_jsonl", "stderr", "stdout"]
data.memory_entry.run_record.test_results       length = 5  (4 leaves + 1 parent — both emit terminal events)
```

Sample `test_results` rows (verbatim from a real run against `gotest-basic`):

```
node_id = example.com/gotestbasic::TestAdd                          | outcome = passed | failure_reference = null
node_id = example.com/gotestbasic::TestSubtract                     | outcome = failed | failure_reference = "native/failures/example.com_gotestbasic__TestSubtract.log"
node_id = example.com/gotestbasic::TestAddSubtests/zero_left        | outcome = passed | failure_reference = null
node_id = example.com/gotestbasic::TestAddSubtests/commutative      | outcome = passed | failure_reference = null
node_id = example.com/gotestbasic::TestAddSubtests                  | outcome = passed | failure_reference = null
```

**Pinned conventions:**
- `node_id` format: `<package>::<test>` (e.g. `example.com/gotestbasic::TestAdd`); subtests use `<package>::<parent>/<subtest>`. The `::` separator is literal.
- `failure_reference` is a **relative path string** pointing under `<artifact_dir>/native/failures/`. Path-safety: `/` → `_`, `:` → `_` (so `::` → `__`), `\` → `_`. The example above shows `example.com/gotestbasic::TestSubtract` becoming `example.com_gotestbasic__TestSubtract.log`.
- **Parent + subtests both emit TestResult rows.** Go's runner really does that; consumers wanting only leaves can filter on `/` in `node_id`. Confirmed: a fixture that "looks like" 4 tests in source produces 5 terminal rows.
- Coverage artifact key is **`coverage_profile`** (NOT `coverage_json`). Confirmed on a `--coverage` run against `gotest-basic-coverage`: `artifact_paths` keys = `["coverage_profile", "gotest_events_jsonl", "stderr", "stdout"]`.
- With `--coverage` against a Go workspace today, `data.coverage_outcome.kind = "unavailable"`, `reason = "missing-native-payload"` — the Coverage engine doesn't yet parse `cover.out` (Coverage-team follow-up). `data.memory_entry.has_coverage_facts` stays `false`. The `coverage_profile` artifact IS registered; only the derivation is pending.

## Verification steps for Manual Test

### 1. Headless smoke against the basic fixture (requires `go` on PATH)

```bash
WS=$(mktemp -d) && cp -r tests/fixtures/projects/gotest-basic/* "$WS"/
(cd "$WS" && uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init >/dev/null)
(cd "$WS" && uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run) \
  | jq '.data.memory_entry.run_record | {engine_name, engine_version, status, summary_counts, artifact_keys: (.artifact_paths | keys)}'
```

Expected: `engine_name == "go-test"`, `engine_version` starts with `"1."`, `status == "failed"`, `summary_counts == {"failed": 1, "passed": 4, "skipped": 0, "total": 5}`, `artifact_keys == ["gotest_events_jsonl", "stderr", "stdout"]`.

Then dump the failure log:

```bash
# Failure logs live under .novetest/run/artifacts/run_*/native/failures/
ls "$WS"/.novetest/run/artifacts/run_*/native/failures/
cat "$WS"/.novetest/run/artifacts/run_*/native/failures/example.com_gotestbasic__TestSubtract.log
```

Expected: file exists, contains `--- FAIL: TestSubtract` and `Subtract(10, 4) = 6, want 5` text.

### 2. Coverage path

```bash
WS=$(mktemp -d) && cp -r tests/fixtures/projects/gotest-basic-coverage/* "$WS"/
(cd "$WS" && uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init >/dev/null)
(cd "$WS" && uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run --coverage) \
  | jq '{cov_kind: .data.coverage_outcome.kind, cov_reason: .data.coverage_outcome.reason, has_cov: .data.memory_entry.has_coverage_facts, artifact_keys: (.data.memory_entry.run_record.artifact_paths | keys)}'
head -5 "$WS"/.novetest/run/artifacts/run_*/native/cover.out
```

Expected:
- `cov_kind == "unavailable"`, `cov_reason == "missing-native-payload"`, `has_cov == false` (Coverage engine cannot parse cover-profile yet — Coverage-team follow-up).
- `artifact_keys` contains `"coverage_profile"`.
- `cover.out` first line is `mode: atomic`; subsequent lines reference both `arithmetic.go` and `classifier.go`; at least one region has trailing `0` (the intentionally uncovered branch in `Classify`).

### 3. Build-failure detection

Create a Go workspace with a deliberate compile error and confirm the typed error surfaces:

```bash
WS=$(mktemp -d) && cd "$WS"
cat > go.mod <<'EOF'
module example.com/brokegen

go 1.21
EOF
cat > broken.go <<'EOF'
package broken

func This is not valid go
EOF
cat > broken_test.go <<'EOF'
package broken

import "testing"

func TestNothing(t *testing.T) {}
EOF
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest init >/dev/null
uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run \
  | jq '{ok, errors, status: .data.memory_entry.run_record.status}'
```

Expected: `ok == false`, the error envelope carries `kind == "unparseable-output"` (the "no `run` action ever fired AND non-zero exit" detector fires). The handoff §6 documents this as the reliable build-failure signal.

### 4. Readiness probe (Go absent)

If you can mask `go` from PATH (or SSH to a Go-less box):

```bash
PATH=/tmp/no-go uv run --project /home/yjshin/dev/aispace/Nove-Test novetest run | jq '.errors'
```

Expected: error envelope carries `kind == "engine-missing"` with `install_hint` referencing `https://go.dev/dl/`. The unit suite already covers this exhaustively; field-test only if you want to confirm the install-hint string is sensible to a human reader.

## Critical edge cases worth probing (per handoff §"Surprises")

- **Subtest emission**: confirm step 1's `summary_counts.total == 5` (NOT 4) and that `test_results` contains both `TestAddSubtests` AND its two children with `/` in their `node_id`s. The "looks like 4 tests" → "actually 5 rows" gap is intentional.
- **`failure_reference` is a path, not text**: unlike pytest (longrepr text) or jest (joined `failureMessages` text), Go's `failure_reference` is a relative path string. Open the referenced file to see the actual `--- FAIL` text.
- **Cover-profile artifact key**: `coverage_profile`, deliberately distinct from the `coverage_json` used by pytest/jest. Pin this in any cross-engine consumer code.
- **`GOTOOLCHAIN=local` was added over the §4 advisory** — verify that running the fixture (which declares `go 1.21` in `go.mod`) on the local `go1.18.1` does NOT trigger a network fetch (the run should complete in <1s without any "go: download" lines on stderr).

## Known drift (PM bookkeeping; NOT a blocker for Manual Test)

`decisions/2026-05-28-regression-outcome-envelope-shape.md` §"Shape" enum still lists `"baseline_engine_name": "pytest" | "jest" | "go" | ...` using `"go"`. The code uses `"go-test"`. A Go-workspace regression run will emit `baseline_engine_name: "go-test"`, NOT the decision text's `"go"`. PM will reconcile (handoff §"Open items" #1). **Do NOT flag this as a regression — it's a documentation drift, not a code defect.**

## Phase progress

- Phase 3 adapter backlog: **2/6 → 3/6** (pytest + jest + go-test landed; junit / cargo-test / xunit remain).
- No `delivery-phasing.md` `- [ ]` bullets close from this slice (Phase 3 line 150 is a narrative goal, not a checkbox).
