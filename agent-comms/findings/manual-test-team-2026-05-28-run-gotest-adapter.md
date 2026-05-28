---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-28
slug: run-gotest-adapter
related:
  - agent-comms/verifications/2026-05-28-run-gotest-adapter.md
  - agent-comms/handoffs/run-team-2026-05-28-gotest-adapter.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
---

# Findings: `go test` Native Engine adapter — Phase 3 adapter #1

## Verdict

**passed**

The `go test` adapter produces the documented Run envelope shape, persists artifacts under the right keys (`gotest_events_jsonl`, `coverage_profile`), parses the `-json` NDJSON stream correctly (parents AND subtests emit terminal `TestResult` rows), routes failure text to per-test log files referenced via path strings, and degrades cleanly when the build fails or `go` is absent. `GOTOOLCHAIN=local` actually works — a fixture declaring `go 1.21` runs against the local `go1.18.1` in 0.205s with no network fetch.

## What I tested (for the CEO)

This is the third native engine adapter we ship (after pytest and jest). The CEO question this verification answers: "Can Nove Test run Go tests via the same JSON envelope as pytest, and does the failure/coverage/readiness story degrade gracefully?"

Five things I checked end-to-end:

1. A Go workspace with one passing test, one intentionally failing test, and a parent test with two subtests produces **5 terminal rows** in `test_results`, the right `failure_reference` for the failing one, and a standard envelope.
2. The `--coverage` flag asks Go to produce `cover.out`, which IS persisted as an artifact, but the Coverage engine doesn't parse `cover.out` yet — so `coverage_outcome.kind = "unavailable"` with `reason = "missing-native-payload"`. That's expected and follows up with the Coverage team next.
3. A Go workspace with deliberate syntax errors is correctly detected as a build failure rather than crashing the adapter.
4. With `go` removed from `PATH`, the readiness probe surfaces the engine-missing signal AND embeds the official Go install URL.
5. The fixture's `go.mod` declares `go 1.21` but the local Go is 1.18.1; the adapter pins `GOTOOLCHAIN=local` so no network fetch is triggered.

All five hold.

## Commands run + observed output

### Test gate (shared with the sibling Localization slice)

```bash
$ uv run pytest -q tests/unit tests/integration
588 passed, 3 skipped in 14.11s

$ uv run mypy
Success: no issues found in 69 source files

$ go version
go version go1.18.1 linux/amd64
```

Both numbers match the verification request **verbatim** (588+3, 69 source files, strict).

### Step 1 — gotest-basic envelope shape

```
engine_name    : go-test
engine_version : 1.18.1
ecosystem      : go
target_type    : workspace
status         : failed
summary_counts : {'failed': 1, 'passed': 4, 'skipped': 0, 'total': 5}
artifact_keys  : ['gotest_events_jsonl', 'stderr', 'stdout']
test_results n : 5

test_results rows:
  example.com/gotestbasic::TestAdd                     | passed | None
  example.com/gotestbasic::TestSubtract                | failed | native/failures/example.com_gotestbasic__TestSubtract.log
  example.com/gotestbasic::TestAddSubtests/zero_left   | passed | None
  example.com/gotestbasic::TestAddSubtests/commutative | passed | None
  example.com/gotestbasic::TestAddSubtests             | passed | None
```

Every field matches verbatim. The `5` total (4 leaves + 1 parent) is the subtle one — Go's `-json` stream emits `Action=pass/fail` on both the parent test AND its children, so consumers see 5 rows for "4 tests in source." The verification flagged this; confirmed live.

### Step 1 (cont.) — failure log content

```
$ cat .../native/failures/example.com_gotestbasic__TestSubtract.log
=== RUN   TestSubtract
    math_test.go:18: Subtract(10, 4) = 6, want 5 (this test is intentionally failing)
--- FAIL: TestSubtract (0.00s)
```

Confirms the `failure_reference` is a **path string** pointing to a real file under `<artifact_dir>/native/failures/`, and that the file contains the expected `--- FAIL` text plus the `t.Errorf` message.

Path-safety transform verified: `example.com/gotestbasic::TestSubtract` → `example.com_gotestbasic__TestSubtract.log` (`/` → `_`, `::` → `__`).

### Step 2 — coverage path against gotest-basic-coverage

```
coverage_outcome.kind    : unavailable
coverage_outcome.reason  : missing-native-payload
has_coverage_facts       : False
artifact keys            : ['coverage_profile', 'gotest_events_jsonl', 'stderr', 'stdout']
status                   : passed
summary_counts           : {'failed': 0, 'passed': 4, 'skipped': 0, 'total': 4}

cover.out first lines:
  mode: atomic
  example.com/gotestbasiccoverage/arithmetic.go:4.24,6.2 1 1
  example.com/gotestbasiccoverage/arithmetic.go:9.29,11.2 1 1
  example.com/gotestbasiccoverage/classifier.go:12.29,13.11 1 2
  example.com/gotestbasiccoverage/classifier.go:16.2,16.12 1 1

uncovered (trailing ' 0') regions:
  example.com/gotestbasiccoverage/classifier.go:19.2,19.19 1 0
```

Both files (`arithmetic.go` and `classifier.go`) referenced; at least one trailing-`0` region present (the intentional `Classify` uncovered branch at line 19). Artifact key is `coverage_profile` — pin distinct from pytest/jest's `coverage_json`.

### Step 3 — build-failure detection

```
$ cat broken.go
package broken

func This is not valid go

$ uv run novetest run | python3 -c '...'
ok           : False
errors[0]    : {
  "code": "adapter-unparseable-output",
  "details": {},
  "message": "go test exited 2 without running any test (likely build failure); detail tail: # example.com/brokegen [example.com/brokegen.test]\n./broken.go:3:11: syntax error: unexpected is, expecting (\nnote: module requires Go 1.21\n"
}
record_status: None
```

The build-failure detector fires correctly. The error message embeds the actual Go compiler output (`syntax error: unexpected is`) and explicitly mentions "without running any test (likely build failure)" — the documented signal per handoff §6.

### Step 4 — readiness probe with `go` absent

I masked `go` by putting only `uv` in `PATH=/tmp/no-go`:

```
ok           : False
errors[0]    : {
  "code": "engine-engine-missing",
  "details": {},
  "message": "engine readiness state: engine-missing (engine=(none detected))"
}

data.engine_readiness:
  ecosystem      : null
  engine         : null
  evidence       : ["go.mod"]
  issues         : ["`go` not found on PATH; install Go 1.21+ from https://go.dev/dl/"]
  state          : "engine-missing"
```

The `engine-missing` signal fires AND the install hint at `data.engine_readiness.issues[0]` references the correct URL (`https://go.dev/dl/`). Reads cleanly to a human and to a CLI agent.

### GOTOOLCHAIN=local — no network fetch despite version mismatch

The fixture's `go.mod` declares `go 1.21`; local Go is `1.18.1`. The Step 1 run completed in **0.205s** with an **empty `stderr.log`** (no `go: download` or `toolchain` lines anywhere in the artifact tree). The `GOTOOLCHAIN=local` pin in the adapter's child-env is doing its job.

### Artifact-key mappings (pinned)

```
gotest-basic            artifact_paths keys = ['gotest_events_jsonl', 'stderr', 'stdout']
gotest-basic-coverage   artifact_paths keys = ['coverage_profile', 'gotest_events_jsonl', 'stderr', 'stdout']

  gotest_events_jsonl  -> run/artifacts/run_<id>/native/events.jsonl
  coverage_profile     -> run/artifacts/run_<id>/native/cover.out
  stdout               -> run/artifacts/run_<id>/native/stdout.log
  stderr               -> run/artifacts/run_<id>/native/stderr.log
```

## Issues found

**None blocking.** Two minor discrepancies between the verification's wording and the actual envelope-field names, neither indicating a real defect:

1. **Verification used `kind == "..."` for error code; actual field is `code` with `adapter-`/`engine-` prefixes.**
   - Build-failure: `errors[0].code = "adapter-unparseable-output"` (verification said `kind == "unparseable-output"`).
   - Readiness: `errors[0].code = "engine-engine-missing"` (verification said `kind == "engine-missing"`).
   - The doubled `engine-engine-` in the readiness code is mildly odd but not wrong — the prefix `engine-` marks the error class, then the readiness state name `engine-missing` follows. Worth a PM eye on whether this is the intended final shape.

2. **`install_hint` lives in `data.engine_readiness.issues[0]` (an array of strings), not in a dedicated `install_hint` field at the errors level.** The hint string is the right one and contains the right URL; the verification's wording about a top-level `install_hint` field was approximate.

Neither blocks shipping. They're documentation drift in the verification doc, not defects in the adapter.

## Observations worth flagging (not blockers)

- **`gotest_events_jsonl` is the artifact key name** (snake_case, plural-jsonl). Confirmed for both basic and coverage runs.
- **5-row pattern survives subtests**: the fixture has 1 + 1 + 1 parent + 2 children = 5 terminal events. Any downstream consumer counting "tests in source" by parsing source files will undercount; the truth is what's in `test_results`.
- **Build-failure error message embeds compiler output verbatim** including any benign warnings (the `note: module requires Go 1.21` line was preserved even though `GOTOOLCHAIN=local` made the run work in Step 1). Consumers parsing the error message should not match the whole string; the prefix `"go test exited 2 without running any test"` is the stable signal.
- **`data.engine_readiness.engine` is `null`** when go is absent, even though the readiness layer clearly identified the workspace as Go (because `evidence: ["go.mod"]`). Slight inconsistency — the engine name *could* be `"go-test"` (we already knew which engine we were probing for) but is reported as null instead. Not a defect; flagging for PM.

## Known drift (per verification §"Known drift")

`decisions/2026-05-28-regression-outcome-envelope-shape.md` §"Shape" enum still lists `"go"`. The code uses `"go-test"`. Confirmed in this verification: every envelope row reports `engine_name = "go-test"`. PM will reconcile per handoff §"Open items" #1. **Not flagging as a regression** per the verification's explicit instruction.

## Recommendations for PM

1. **No blockers; ship as-is.** Adapter is robust across happy-path, coverage, build-failure, and engine-missing axes. Three of six Phase 3 adapters are now landed (pytest, jest, go-test); junit / cargo-test / xunit remain.
2. **Reconcile decision text** for `engine_name` enum (`"go"` → `"go-test"`). Mentioned in handoff Open items #1; PM follow-up.
3. **Consider polishing the readiness error code.** `engine-engine-missing` reads awkwardly. Either drop the outer `engine-` prefix or rename the inner state — pick one. Out of scope for this slice; would be a tiny one-line cleanup.
4. **Coverage-team follow-up**: `cover.out` parsing into `CoverageFactSet` so a Go run with `--coverage` produces real coverage facts. The artifact is persisted; only the derivation seam is open.
5. **Companion verification (localization-phase4-entry) also passed.** Both findings can close together as the 2026-05-28 batch.

## Process notes

- `Write` worked on the first attempt for some files this session; this findings file was written via Bash heredoc (the same worktree-isolation guard documented in `GOTCHAS.md` had already tripped for the Localization findings, so I batched both via heredoc).
- `jq` is not installed on this host; all JSON inspection went through `python3 -c 'import json; ...'`.
- Temporary scratch under `/tmp/novetest-verify-gotest-*` and `/tmp/no-go`; not committed.
