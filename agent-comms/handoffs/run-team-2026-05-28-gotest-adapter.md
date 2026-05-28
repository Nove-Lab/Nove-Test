---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-05-28
slug: gotest-adapter
related:
  - agent-comms/tasks/run-team-2026-05-28-gotest-adapter.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/decisions/2026-05-28-regression-outcome-envelope-shape.md
  - design/implementation-plan/engine-adapters.md
---

# Handoff: `go test` Native Engine adapter — Phase 3 adapter backlog #1

## Worktree

- Path: `/home/yjshin/dev/aispace/novetest-gotest-adapter`
- Branch: `run-team/gotest-adapter`
- Base commit: `4be6c7c` (the parallel-cycle dispatch commit on `main`)
- Push status: **local only — not pushed**. Main Branch team picks up locally.

## Files written / modified

### New src/ files (1)

- `src/novetest/run/adapters/gotest_adapter.py` (~280 lines)
  - `async def run_gotest(test_target, *, artifact_dir, timeout=600.0, collect_coverage=False) -> NativeResult`
  - Resolves `go` via `shutil.which` up-front (typed `missing-binary` on absence)
  - argv: `[go, test, -json, -count=1, -timeout=<N>s, ...optional cover flags..., <target_or_./...>]`
  - Stream-parses NDJSON line-by-line (defensive parsing per decision 2026-05-25)
  - Writes `<artifact_dir>/native/events.jsonl`, `stdout.log`, `stderr.log`
  - Per-failing-test failure log → `<artifact_dir>/native/failures/<safe>.log`
  - Build-failure detection: no `run` action + non-zero exit → `unparseable-output`
  - Coverage: registers `cover.out` under artifact key `coverage_profile` (NOT `coverage_json` — Coverage team will dispatch on `engine_name == "go-test"` to parse cover-profile format)
  - Best-effort `go version` parse → `engine_version`
  - Child env: `GOFLAGS=-mod=readonly` + `GOTOOLCHAIN=local` + `NO_COLOR=1`

### Modified src/ files (4)

- `src/novetest/run/engine_selector.py`: `_IMPLEMENTED_ECOSYSTEM_TO_ENGINE` gains `"go": "go-test"`; docstring updated to note adapter backlog 3/6.
- `src/novetest/run/engine.py`: imports `run_gotest`; `_invoke_adapter` gains `engine_name == "go-test"` branch.
- `src/novetest/run/readiness.py`: adds `_assess_gotest_readiness` (no-go-on-PATH → `engine-missing`, broken `go version` → `engine-misconfigured`, otherwise `ready` with parsed version) and routes Go candidates to it; adds `_parse_go_version` helper.
- `src/novetest/run/normalizer.py`: adds `_normalize_gotest_payload(payload, *, returncode)` + `_aggregate_gotest_status` + `_GOTEST_ACTION_TO_OUTCOME` table; `normalize_native_result` dispatcher gains `engine_name == "go-test"` branch.

### New fixture trees (2)

- `tests/fixtures/projects/gotest-basic/` — `go.mod`, `math.go`, `math_test.go`, `README.md`. One passing test (`TestAdd`), one intentionally failing test (`TestSubtract`), one parent with two passing subtests (`TestAddSubtests`/`zero_left`, `commutative`) — 5 terminal `(Package, Test)` events total.
- `tests/fixtures/projects/gotest-basic-coverage/` — `go.mod`, `classifier.go`, `arithmetic.go`, `arithmetic_test.go`, `README.md`. 4 passing tests; `Classify`'s negative branch intentionally uncovered so `cover.out` has at least one `count=0` region.

### New / modified test files (6)

- New `tests/unit/run/adapters/test_gotest_adapter.py` — 16 cases (~520 lines).
- New `tests/integration/run/test_gotest_basic.py` — 1 case (skips when `go` absent).
- New `tests/integration/run/test_gotest_coverage.py` — 1 case (skips when `go` absent).
- Extended `tests/unit/run/test_normalizer.py` — 7 new Go cases appended.
- Extended `tests/unit/run/test_readiness.py` — 3 new Go cases appended.
- Extended `tests/unit/run/test_engine_selector.py` — 1 new case + docstring touch.
- Extended `tests/unit/run/test_engine.py` — 1 new dispatch test for go-test.
- Extended `tests/unit/run/conftest.py` — 2 new fixtures (`gotest_basic_workspace`, `gotest_basic_coverage_workspace`).

### Other

- `WORKLOG.md` — new top entry `## 2026-05-28 — phase3 / gotest-adapter`.
- `agent-comms/handoffs/run-team-2026-05-28-gotest-adapter.md` — this file.
- `agent-comms/INDEX.md` — regenerated.

## Verification

- `uv run pytest -q tests/unit tests/integration` → **501 passed, 3 skipped**
  - Baseline at base commit `4be6c7c`: 471 passed, 3 skipped (verified before any changes were made).
  - Delta: **+30 new tests, 0 regressions**.
  - The 3 skipped are the pre-existing Node-dependent jest integration tests.
  - The local box has `go1.18.1` installed, so the two new Go integration tests RUN locally and pass; on a Go-less CI cell they skip cleanly via `_require_go()`.
- `uv run mypy` → clean (`--strict`, 58 source files; +1 source file `gotest_adapter.py` over the 57-file baseline).
- Smoke test of full `execute()` against `gotest-basic`: status `failed`, summary `{passed: 4, failed: 1, skipped: 0, total: 5}`, `engine_version: 1.18.1`, failure log present + contains the expected multi-line `--- FAIL` text. Coverage smoke against `gotest-basic-coverage`: `cover.out` first line `mode: atomic`, regions for both source files, `coverage_profile` artifact registered.

## Phase progress

**Phase 3 adapter backlog: 2/6 → 3/6** (pytest + jest + go-test landed; junit / cargo-test / xunit remain).

No `delivery-phasing.md` `- [ ]` bullets are claimed by this slice — Phase 3 line 150 is a narrative goal, not a checkbox. PM ticks nothing.

## DoD bullets believed closed

(none — this is the adapter-backlog narrative.)

## Supported-engine-matrix proposal (per decision 2026-05-25)

For PM to weave into the next matrix-update commit / decision amendment:

| Dependency | Floor | Tested ceiling | Notes |
|---|---|---|---|
| Go | 1.21 | (locally verified 1.18) | The `go test -json` schema + `-cover -coverprofile -covermode -coverpkg` flag set is stable 1.10+; 1.21 is a sensible floor (current widely-shipping toolchain, matches the `go.mod` directive in the fixtures). Tested-ceiling needs a real CI cell — Release-team follow-up. |

## Open items

1. **`"go"` vs `"go-test"` enum drift** in `decisions/2026-05-28-regression-outcome-envelope-shape.md` §"Shape". The decision text lists `"baseline_engine_name": "pytest" | "jest" | "go" | ...` using `"go"`. The code (`engine_selector._SUPPORTED_PAIRS`) uses `"go-test"`, and this adapter ships with `engine_name="go-test"`. A Go-workspace regression run will emit `baseline_engine_name: "go-test"`, NOT the decision text's `"go"`. PM should write a small bookkeeping amendment — either extend the enum to `"go" | "go-test"` (additive) or replace `"go"` with `"go-test"` (corrective). I did NOT modify the decision file (PM territory).
2. **Coverage engine follow-on**. The Coverage team needs to extend `coverage/derive_coverage_facts` to dispatch on `engine_name == "go-test"` and parse the cover-profile format (`mode: atomic` header + per-region `file:startLine.startCol,endLine.endCol numStmts count` lines). Until that lands, `novetest run --coverage` against a Go workspace produces a Run Record with `coverage_profile` artifact but `has_coverage_facts` stays False. This is the natural next slice for the Coverage team.
3. **CI matrix has no Go cell yet**. The 2 new integration tests skip cleanly when `go` is absent — Release-team follow-up to add a Go cell to `.github/workflows/ci.yml` so the integration tests become real gates.

## Surprises / native-engine quirks

- **Parent + subtests both produce TestResult rows**. Go's runner emits a terminal `pass` action for the parent (e.g. `TestAddSubtests`) AND for each subtest (e.g. `TestAddSubtests/zero_left`). The normalizer treats each as a separate TestResult — that's faithful to the engine's event stream. Downstream consumers can filter on `/` in `node_id` to get only leaves. (Documented in the normalizer docstring + `test_gotest_subtests_produce_parent_and_child_test_results`.)
- **Build failures emit NOTHING on stdout** — they go straight to stderr. The task's "output event with `Test: ""` before any `run`" heuristic doesn't trigger in practice. The reliable signal is "no `run` action ever fired + non-zero exit"; verified empirically with a malformed `package broken` test workspace.
- **`failure_reference` for Go is a relative path string**, unlike pytest (longrepr text) or jest (joined `failureMessages` text). The adapter writes the file (it has `artifact_dir`); the normalizer just plumbs the path through. The adapter's `failure_logs` map keys (e.g. `"example.com/foo::TestSub"`) match the normalizer's `node_id` format exactly — coupling documented in both files.
- **`GOTOOLCHAIN=local` is an addition I made over the §4 advisory**. Without it, `go test` will auto-fetch a newer toolchain when the workspace's `go.mod` declares a higher `go` directive than the installed binary, which (a) re-triggers network access on a `-mod=readonly` run and (b) surfaces a confusing error instead of a clean "this needs Go X.Y" message.
- **Local Go is 1.18.1, not 1.21+**. The fixtures' `go.mod` declares `go 1.21` but the local toolchain is 1.18.1 — Go's compatibility model lets you run a higher-`go.mod` workspace on a lower toolchain unless the workspace uses 1.21+ syntax. My fixtures don't use any 1.21-specific syntax, so the tests pass on 1.18.1. PM should pin the matrix floor at the spec point (1.21) regardless of what the local box happens to ship.

## Worklog entry text (paste)

```
## 2026-05-28 — phase3 / gotest-adapter

- Landed: Phase 3 adapter backlog #1 — the `go test` Native Engine adapter, the third native engine to ship (after pytest + jest). [...full bullet pasted in WORKLOG.md...]
- Verified: `uv run pytest -q tests/unit tests/integration` → **501 passed, 3 skipped** (baseline 471+3 at worktree base `4be6c7c`; +30 net new; the 3 skipped are the pre-existing Node-dependent jest integration tests). `uv run mypy` → clean (`--strict`, 58 source files, +1 source file `gotest_adapter.py`). Local Go is `go1.18.1` so the two new integration tests RUN locally and pass; on a Go-less CI box they skip cleanly.
- Left open: Coverage engine follow-up — `cover.out` parser dispatched on `engine_name == "go-test"`. Supported-engine-matrix amendment for Go (floor `1.21`). Regression-outcome decision drift (`"go"` vs `"go-test"`).
- Gotcha: parent + subtests both produce TestResult rows (Go really emits both); `failure_reference` for Go is a relative path string (not text like pytest/jest); build-failure detection uses "no `run` action + non-zero exit" not the task's "output without matching run" heuristic; `GOTOOLCHAIN=local` added over the §4 advisory.
- Next: Main Branch merges → Manual Test fields → PM amends matrix + decision drift → Coverage team picks up the follow-on slice. Phase 3 adapter backlog 2/6 → 3/6.
```

(Full bullet body in `WORKLOG.md`.)
