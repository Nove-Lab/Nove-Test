---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-28
slug: gotest-adapter
related:
  - design/implementation-plan/engine-adapters.md
  - design/implementation-plan/delivery-phasing.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - src/novetest/run/adapters/pytest_adapter.py
  - src/novetest/run/adapters/jest_adapter.py
---

# Task: Go test Native Engine adapter (Phase 3 adapter backlog #1)

## Mission

Ship the third Native Engine adapter — `go test` for the Go ecosystem.
Establishes the pattern for compiled-language adapters (no interpreter,
no plugin autoload semantics, native streaming JSON output). Closes one
of four missing adapters required by `delivery-phasing.md` Phase 3
("all six landed by end of Phase 3"). Single-team, single-slice; runs in
parallel with the Localization Phase 4 entry slice (territory disjoint).

Out of scope today: JUnit / cargo / dotnet adapters (separate slices),
extending the Coverage engine to parse Go's cover-profile format (see
§"Coverage scope split" below), CLI surface changes.

## Pre-flight reading (mandatory, in this order)

1. `CLAUDE.md`
2. `.claude/agents/novetest-run-team.md` (your charter)
3. `agent-comms/INDEX.md`
4. `agent-comms/decisions/2026-05-25-supported-engine-matrix.md` —
   especially the supported-version-matrix table and the maintenance
   discipline section ("New engine added → PM extends the matrix with
   floor + ceiling in the engine's onboarding decision doc"). Your
   handoff MUST propose a Go floor + tested ceiling.
5. `design/implementation-plan/engine-adapters.md` §4 (Go + `go test`)
   — this is the cited contract for adapter behavior.
6. `design/interace-contract/run.md` — the surface you are extending.
7. `design/workflows/run.md` — the sequence the adapter sits in.
8. `src/novetest/run/adapters/pytest_adapter.py` — the reference adapter
   pattern for an interpreted language.
9. `src/novetest/run/adapters/jest_adapter.py` — the reference adapter
   pattern for an "external launcher" (npx) case. The `_npx_launcher` /
   Windows-shim pattern there is the precedent for `go` binary
   resolution.
10. `src/novetest/run/engine.py` and
    `src/novetest/run/engine_selector.py` — registration points.
11. `src/novetest/run/readiness.py` — readiness probe pattern.

## Pre-slice baseline (verified 2026-05-28)

- `git status`: clean, synced to `origin/main` HEAD `194637b`.
- `uv run pytest -q`: **471 passed, 3 skipped**.
- `src/novetest/run/adapters/` contains only `pytest_adapter.py` and
  `jest_adapter.py` (+ `__init__.py`).
- `tests/fixtures/projects/` contains only Python + JS fixtures; no Go
  fixture yet.

When you start, run `uv run pytest -q` at your worktree base commit and
record the count in your handoff. The slice is GREEN when the new total
≥ baseline + your new tests, mypy stays clean, and no existing test
regresses.

## Scope

Six things to ship, in this order:

### 1. Fixture projects

- `tests/fixtures/projects/gotest-basic/` — minimal Go module with one
  passing test and one failing test (mirrors `pytest-basic/` +
  `pytest-failing/` consolidated; engine-adapters.md §4 advises
  failure-detail capture is the meaningful surface). Self-contained
  module (`go.mod` with module name like `example.com/gotest-basic`),
  no external deps. The test file should use `t.Errorf` for the
  failing case and at least one subtest (`t.Run("subtest", ...)`) to
  exercise the `Parent/Child` parsing path. Add a `README.md` so future
  maintainers know it's deterministic and isolated.
- `tests/fixtures/projects/gotest-basic-coverage/` — same shape as
  `gotest-basic/` but with one additional source file under test so
  `cover.out` has interesting block structure. Required for the
  `collect_coverage=True` adapter test path (the unit test stubs the
  subprocess, but the integration test exercises the real
  `go test -coverprofile`).

Both fixtures must NEVER import `novetest`. The Run charter says
fixtures are "deterministic, small, isolated, self-contained, and
never import `novetest`."

### 2. `src/novetest/run/adapters/gotest_adapter.py`

Follow the `run_pytest` / `run_jest` shape verbatim. Surface:

```python
async def run_gotest(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,
) -> NativeResult:
    ...
```

Key behaviors (from `engine-adapters.md` §4):

- Resolve `go` binary up front via `shutil.which("go")`; raise
  `AdapterInvocationError(kind="missing-binary",
  install_hint="install Go 1.21+ from https://go.dev/dl/")` if absent.
  This mirrors the jest adapter's `npx`-resolution-first pattern.
- argv core:
  `[go, "test", "-json", "-count=1", "-timeout=<...>", target_or_./...]`
  where `<...>` is a Go-formatted duration (e.g. `"10m"` for a
  600-second timeout — use `f"{int(timeout)}s"` if you want seconds
  precision). `-count=1` disables Go's test cache (per §4 edge cases).
- When `target_expression` is empty or `./...`, pass `./...`. When the
  user passes a package path (`./subpkg`) or a `-run` filter, plumb
  it through faithfully; do NOT reinterpret nodeids.
- When `collect_coverage=True`, add
  `["-cover", f"-coverprofile={cover_out_path}", "-covermode=atomic",
  "-coverpkg=./..."]`. Note the `-coverpkg=./...` per §4 edge cases:
  without it, only the test's own package is measured.
- **Stream-parse stdout** — do NOT buffer the full output. `go test
  -json` emits NDJSON; one event per line. Implement with a line-by-line
  loop over `result.stdout.decode().splitlines()` (you receive it as
  bytes from `run_subprocess`; this is fine for stream-parse semantics
  even though we read after the process exits — Go output is small per
  event and the buffer is bounded by the process's natural output
  cadence). If profile work later requires true streaming, that's a
  follow-up; this slice's contract is: never *parse* the buffer as a
  single JSON document.
- Persist full raw stdout to `stdout.log` and stderr to `stderr.log`
  exactly like the pytest/jest adapters.
- Event shape (per `go doc cmd/test2json`):
  `{Time, Action, Package, Test, Output, Elapsed}` where `Action` is
  one of `run | pause | cont | pass | bench | fail | output | skip`.
  Reassemble per-test by buffering `Output` events keyed on
  `(Package, Test)` until the terminal action (`pass | fail | skip`)
  arrives. Subtests have `Test: "Parent/Child"` — track the `/`-split.
- Build failures: surfaced as `Action: output` events with `Test: ""`
  before any `run` action. Detect by checking if any `output`-with-empty-
  `Test` event arrives without a matching `run`, and surface as
  `AdapterInvocationError(kind="unparseable-output",
  detail=...stderr_tail)` — same precedent as the pytest adapter's
  "no JSON report" path. Build failures are not test failures.
- The `NativeResult.payload` field is the engine's "raw structured
  payload" — for pytest it's the parsed JSON-report dict; for jest it's
  the parsed JSON dict from `--outputFile`. For Go, store a dict of
  shape `{"events": [<list of event dicts>], "packages": <list of
  package names seen>}` — a deliberately minimal but structurally
  sufficient payload. Run team owns this shape; downstream (normalizer
  + Coverage engine for later coverage parsing) is the only consumer.
- `artifact_paths` keys:
  - `gotest_events_jsonl` → path to a written-out NDJSON file
    (`artifact_dir / "native" / "events.jsonl"`) — Memory rewrites to
    project-store-relative.
  - `stdout` → `stdout.log` (raw concatenated NDJSON for debugging).
  - `stderr` → `stderr.log`.
  - **When `collect_coverage=True`** add
    `coverage_profile` → `cover.out`. Use the key `coverage_profile`
    (NOT `coverage_json` — that key is for Istanbul/coverage.py JSON
    and would mislead the Coverage engine). The Coverage engine will
    later dispatch on `engine_name == "go-test"` to parse `cover.out`
    in a separate slice (see §"Coverage scope split").
- Engine version: best-effort `go version` parse (`shutil.which("go")`
  + `go version` subprocess returning `go version go1.23.4 linux/amd64`
  → extract `"1.23.4"`). Return `None` silently on any failure (mirrors
  `_read_jest_version`). Version is informational metadata only.
- `engine_name` value: **`"go-test"`** (matches `_SUPPORTED_PAIRS` in
  `engine_selector.py`). See "Known inconsistency" below if you notice
  drift from the regression-outcome decision.
- Windows: Go ships a real `go.exe` (PE binary, not a .cmd shim), so
  Windows handling is simpler than jest's `cmd /c npx` workaround.
  `shutil.which("go")` returns `go.exe` directly and
  `asyncio.create_subprocess_exec` can launch it natively. No launcher
  layer needed. `GOFLAGS=-mod=readonly` (per §4 edge cases) avoids
  vendored-dir walking on Windows; set in `_build_child_env()`.

### 3. `src/novetest/run/engine_selector.py` — wire-up

- Already lists `("go", "go-test")` in `_SUPPORTED_PAIRS` ✓.
- Already detects ecosystem via `go.mod` marker ✓.
- Add `"go": "go-test"` to `_IMPLEMENTED_ECOSYSTEM_TO_ENGINE` — this is
  the one-line change that unblocks `select_native_engine` for Go.

### 4. `src/novetest/run/engine.py` — dispatch

- Import `run_gotest`.
- Add a third branch in `_invoke_adapter`:
  ```python
  if engine_name == "go-test":
      return await run_gotest(...)
  ```

### 5. `src/novetest/run/readiness.py` — Go probe

Add `_assess_gotest_readiness(workspace_path, candidate)` mirroring
`_assess_pytest_readiness` / `_assess_jest_readiness`. Readiness states:

- `engine-missing` — `go` not on PATH.
- `engine-misconfigured` — `go` on PATH but `go version` fails or no
  `go.mod` in workspace (the ecosystem-detection already found `go.mod`
  if we got here, but defend against TOCTOU).
- `ready` — `go` resolves and `go version` succeeds; report parsed
  `engine_version`.

Wire the new probe into `assess_engine_readiness`'s ecosystem dispatch
table near the existing pytest/jest branches.

### 6. `src/novetest/run/normalizer.py` — Go normalization

The normalizer turns `NativeResult` into a `RunRecord` with normalized
`TestResult` rows. The Go-specific concern is: outcome string mapping.

- pass → `"passed"`
- fail → `"failed"`
- skip → `"skipped"`
- Any other terminal action (none expected today, but the decision
  `2026-05-25-supported-engine-matrix.md` §C requires defensive
  parsing) → `"unknown"` rather than raising. Visible-not-silent.

`TestResult.node_id` for Go should be `<Package>::<Test>` (e.g.
`example.com/gotest-basic::TestAdd`). Subtests: `<Package>::<Parent>/<Child>`.
Pick this convention deliberately — it mirrors pytest's `path::func`
style and is unambiguous for downstream consumers.

`TestResult.duration_ms`: from the terminal event's `Elapsed` (seconds
as float) → int milliseconds.

`TestResult.failure_reference`: when a test fails, write its buffered
`Output` events (joined) to
`<artifact_dir>/native/failures/<safe_node_id>.log` and store the
relative path in `failure_reference`. Filename safety: `/` in subtest
names needs escaping (URL-style or `:` substitution); pick one and
document it in the code. The pytest adapter has prior art for this
pattern; do not invent new conventions.

If you discover normalizer changes that require touching `models/`,
STOP and write `agent-comms/questions/run-team-2026-05-28-*.md` per
your charter. Do NOT modify `src/novetest/models/`.

## Coverage scope split (read carefully)

This slice is a **Run-engine adapter only**. It does NOT teach the
Coverage engine to parse Go's `cover.out` format. The scope split:

- **Today (this slice, Run team):** when `collect_coverage=True`,
  invoke `go test -coverprofile=cover.out -covermode=atomic
  -coverpkg=./...` and register `coverage_profile` in
  `artifact_paths`. Verify the file lands.
- **Future slice (Coverage team):** extend
  `coverage/derive_coverage_facts` to dispatch on
  `engine_name == "go-test"` and parse the cover-profile format
  (`mode: atomic` header + per-region `file:startLine.startCol,endLine.endCol numStmts count`
  lines). Until that lands, `novetest run --coverage` against a Go
  workspace produces a Run Record with `coverage_profile` artifact but
  `has_coverage_facts` stays False.

Document this in your handoff so the next cycle's PM dispatch knows
this is the natural follow-on.

## Known inconsistency to flag (not yours to fix)

The freeze decision `decisions/2026-05-28-regression-outcome-envelope-shape.md`
§"Shape" lists `"baseline_engine_name": "pytest" | "jest" | "go" | ...`
— using `"go"` rather than `"go-test"`. This drifts from
`_SUPPORTED_PAIRS` (which uses `"go-test"`). **You ship with
`engine_name="go-test"`** (the code is source-of-truth; the decision
text needs a PM-side amendment).

Do NOT modify `agent-comms/decisions/*.md` yourself — that is PM
territory. Note this drift in your handoff under "Open items" and PM
will queue a small bookkeeping commit (additive: extend the enum to
`"go" | "go-test"` until all adapters land, or just replace `"go"`
with `"go-test"`; PM judgment).

## Test surface

### Unit tests (subprocess stubbed) — `tests/unit/run/adapters/test_gotest_adapter.py`

Mirror the jest adapter test pattern:

- Stub `shutil.which` autouse fixture so a Go-less CI box doesn't fail
  the `missing-binary` resolution. Override in the missing-binary test.
- Stub `novetest.run.adapters.gotest_adapter.run_subprocess` to return
  a fixed `SubprocessResult` with deterministic NDJSON bytes in
  `stdout`.
- Coverage of the NDJSON event reassembly is the meaty path. Test:
  - Single passing test → one `TestResult` row, outcome `"passed"`.
  - Single failing test with multi-line `Output` events → failure log
    written, `failure_reference` path stored.
  - Subtest `Parent/Child` → node_id format `<pkg>::Parent/Child`.
  - Build-failure shape (`output` event with `Test: ""` and no `run`)
    → raises `AdapterInvocationError(kind="unparseable-output")`.
  - `Action: skip` → outcome `"skipped"`.
  - Unknown terminal action → outcome `"unknown"` (defensive parsing
    audit row).
  - `collect_coverage=True` → argv includes `-cover -coverprofile=
    <path> -covermode=atomic -coverpkg=./...`; when stubbed
    subprocess writes a fake `cover.out`, `artifact_paths` contains
    `coverage_profile` pointing to it.
  - Missing `go` binary → `shutil.which` returns None → raises
    `AdapterInvocationError(kind="missing-binary")` BEFORE any stub
    is hit.
  - Timeout → `result.timed_out` True → raises
    `AdapterInvocationError(kind="timed-out")`.

Aim for ~12-15 unit tests.

### Integration tests — `tests/integration/run/test_gotest_basic.py` + `test_gotest_coverage.py`

Mirror `test_jest_basic.py`'s `pytest.importorskip` / `shutil.which`
guard pattern: skip when `go` is not on PATH. When Go IS present:

- `test_gotest_basic.py`: invoke `run_gotest` against
  `tests/fixtures/projects/gotest-basic/` (no coverage); assert the
  passing + failing tests show up with the right outcomes and the
  failure log was written.
- `test_gotest_coverage.py`: invoke `run_gotest` against
  `tests/fixtures/projects/gotest-basic-coverage/` with
  `collect_coverage=True`; assert `coverage_profile` artifact landed
  and the file's first line is `mode: atomic`.

Both integration tests should skip cleanly when `go` is absent (CI
matrix may not have Go installed everywhere yet — that's a Release-team
follow-up, not yours).

### Readiness tests — extend `tests/unit/run/test_readiness.py`

Add cases for `_assess_gotest_readiness`:
- Go workspace + `go` on PATH + valid `go version` → `ready` with
  `engine_version` populated.
- Go workspace + `go` not on PATH → `engine-missing`.
- Go workspace + `go` on PATH + `go version` returns non-zero →
  `engine-misconfigured`.

### Engine selector tests — extend `tests/unit/run/test_engine_selector.py`

- Add a case: `go.mod` workspace → `select_native_engine` returns
  `NativeEngineContext(ecosystem="go", engine_name="go-test")`.

### Aim

~25-30 new tests across unit + integration. Final pytest count should
be roughly **496-501 passed + 3 skipped + N skipped** (where N is the
integration tests that skip on a Go-less box).

## Out-of-scope (DO NOT do in this slice)

- Coverage engine integration (parsing `cover.out`) — separate slice
  (Coverage team).
- JUnit / cargo / dotnet adapters — separate slices.
- Race detector (`-race`) flag exposure — separate Run-team slice
  post-MVP per `engine-adapters.md` §4 ("expose as a separate Nove
  Test mode, not the default").
- Per-test coverage for Go — Go's `-coverprofile` is aggregate-only;
  the per-test slow path (`engine-adapters.md` §4 "Test-to-code
  mapping") is explicitly opt-in and OUT for this slice.
- `cargo nextest libtest-json` — Open Question #3 territory, not yours.
- Modifications to `src/novetest/models/` — write a question if
  needed.
- Modifications to `agent-comms/decisions/*.md` — PM territory.
- Modifications to `design/*.md` — PM territory (you own
  `design/interace-contract/run.md` and `design/workflows/run.md`,
  but neither needs editing for this slice unless you discover a real
  contract drift).

## DoD bullets advanced (not closed)

This slice does NOT directly close a `delivery-phasing.md` `- [ ]`
bullet (Phase 3's adapter line 150 is a narrative goal, not a
checkbox). It advances "all six landed by end of Phase 3" from 2/6 to
3/6. PM will not tick anything; report in your handoff under "Phase
progress" rather than "DoD bullets believed closed".

## Handoff requirements

Standard handoff (`agent-comms/handoffs/run-team-2026-05-28-gotest-adapter.md`)
with the usual sections, plus:

- **Worktree** path / branch / base commit / push status.
- **Files written/modified**: enumerate.
- **Tests**: `uv run pytest -q` final count + comparison to baseline
  (471+3); `uv run mypy --strict` clean.
- **WORKLOG.md entry text**: paste here.
- **Phase progress**: "Phase 3 adapter backlog: 2/6 → 3/6 (pytest +
  jest + go-test)".
- **Supported-engine-matrix proposal** (per decision
  `2026-05-25-supported-engine-matrix.md`): propose floor + tested
  ceiling for Go. Suggestion: floor `1.21` (current LTS-ish), tested
  ceiling `1.23` or `1.24` whichever you exercised. PM will weave this
  into a follow-up matrix-update commit.
- **Open items** including the `"go"` vs `"go-test"` enum drift in the
  regression-outcome decision (mention it; do NOT fix it).
- **Coverage follow-on note**: explicitly call out that the Coverage
  engine needs a `cover.out` parser as the next step before
  `has_coverage_facts` flips True for Go runs.

Run `python3 tools/regen_comms_index.py` before committing the handoff.

## Reporting back

After your handoff is committed, Main Branch will pick it up: merge,
write verification, push. Manual Test then field-tests the new adapter
(may run a real Go test if their box has Go installed; otherwise
exercises the unit-test path). Standard cadence — same pattern as the
jest adapter and the three Regression slices.
