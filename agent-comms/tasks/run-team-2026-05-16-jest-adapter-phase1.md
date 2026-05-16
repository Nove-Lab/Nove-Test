---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-16
slug: jest-adapter-phase1
related:
  - history/2026-05-16-phase0-closure-partial.md
---

# Task: Jest native adapter (Phase 1 equivalent — execution only, no coverage)

## Scope / Mission

Add the **jest** native engine adapter so `novetest run` works against
JavaScript/TypeScript workspaces (with `package.json` + a jest dep).
Scope is **Phase 1 equivalent for jest**: pure test execution +
passed/failed normalization. Coverage emission is **deferred** to a
later slice that also requires the Coverage team to land an Istanbul
JSON → CoverageFactSet parser. Do NOT wire `--coverage` for jest in
this slice; the kwarg can be accepted (default False) and ignored, but
emitting Istanbul output is out of scope.

Phase 2.5 entry under `design/implementation-plan/engine-adapters.md`.
Parallel to Phase 2 work (Coverage show/diff in another team) — no
direct dependency.

This slice does NOT close any DoD bullet directly. It is infrastructure
for Phase 2.5 / Phase 3 cross-engine work. Verifies the adapter pattern
generalizes beyond pytest.

## Pre-flight reading

1. `CLAUDE.md`
2. `agent-comms/INDEX.md`
3. `agent-comms/decisions/` newest first
4. `agent-comms/tasks/run-team-2026-05-16-jest-adapter-phase1.md` (this
   file)
5. `WORKLOG.md` top 3 entries (latest pytest-adapter entries are your
   pattern template)
6. `design/interace-contract/run.md` — read-only; same contract as
   pytest adapter
7. `design/workflows/run.md` — Section 1 (`execute`) is unchanged; you
   plug into the existing flow
8. `design/implementation-plan/engine-adapters.md` Section 2
   (JavaScript / TypeScript + Jest) — the authoritative description of
   the discovery + execution shape
9. `src/novetest/run/adapters/pytest_adapter.py` — your pattern
   reference. Mirror its shape closely (artifact_dir, NativeResult
   return, PYTEST_DISABLE_PLUGIN_AUTOLOAD-equivalent isolation).
10. `src/novetest/run/engine_selector.py` — currently raises
    `EngineNotSupportedError` for jest; you'll extend the
    `select_native_engine` switch
11. `src/novetest/run/readiness.py` — currently detects jest but
    `assess_engine_readiness` only validates the python+pytest path;
    you'll extend it to validate JS workspaces too

## Implementation approach

### 1. Workspace detection (already done)

`detect_engine_candidates` already returns an `EngineCandidate(ecosystem="javascript-typescript", engine_name="jest")` when `package.json` is in the workspace. No change needed here.

### 2. Readiness probe — extend `assess_engine_readiness`

Currently the function gates on `python+pytest` only. For jest:

- Verify `node` is on `PATH` (`shutil.which("node")` or async equivalent).
  If absent → `engine-missing`.
- Verify `package.json` contains jest in its `devDependencies` or
  `dependencies` (or that `node_modules/.bin/jest` exists, indicating
  installed). If absent → `engine-misconfigured`.
- Capture `node --version` and `npx jest --version` for the readiness
  evidence list (parallel to how pytest version is captured today).

Mirror the existing pytest readiness checks' structure (the
`engine_version` field on the returned `EngineReadinessResult` /
`NativeEngineContext` carries the engine's reported version).

### 3. Engine selector — extend `select_native_engine`

Currently raises `EngineNotSupportedError` for any non-python ecosystem.
For jest:

- `_ecosystem_for_workspace` already detects `javascript-typescript`
  via `package.json` (verify this — if not, add it).
- `select_native_engine` returns
  `NativeEngineContext(ecosystem="javascript-typescript", engine_name="jest")`
  for that case.
- Keep raising for all other ecosystems (jest's slice does not unblock
  go/rust/java/dotnet).

### 4. Adapter — `src/novetest/run/adapters/jest_adapter.py` (NEW)

Mirror `pytest_adapter.py`'s shape. Public signature:

```python
async def run_jest(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,   # accepted but no-op this slice
) -> NativeResult:
    ...
```

Invocation pattern (per `engine-adapters.md` §2):

```sh
npx jest <target> \
  --ci \
  --json \
  --testLocationInResults \
  --outputFile=<artifact_dir>/native/jest-results.json \
  --reporters=default
```

- `cwd` is `test_target.workspace_path` (the JS project root).
- Capture stdout/stderr to `<artifact_dir>/native/{stdout,stderr}.log`
  identical to pytest_adapter.
- Set `JEST_DISABLE_PLUGIN_AUTOLOAD=...`? — jest doesn't have an
  equivalent plugin-isolation concept. The risk that the SuT's
  `jest.config.js` loads adapter-side plugins is low (no system-wide
  jest registry). Document this in the adapter docstring.
- Parse `jest-results.json` → `NativeResult`:
  - `numPassedTests`, `numFailedTests`, `numPendingTests` → counts.
  - `testResults[].testResults[]` → per-test outcome list (nodeid =
    `<file>::<describe path>::<it name>`).
  - Top-level `success` field → overall pass/fail.
- `NativeResult.artifact_paths`: `jest_json_report`, `stdout`,
  `stderr` (absolute `Path`s, just like pytest's
  `pytest_json_report` / `stdout` / `stderr`).
- Missing-binary path (no node): `AdapterInvocationError(kind="missing-binary", install_hint="install Node.js >=18 and ensure `node` is on PATH")`.
- Missing-plugin path (jest not installed in workspace):
  `AdapterInvocationError(kind="missing-plugin", install_hint="npm install --save-dev jest")`.
- Missing post-condition (jest exited but no JSON report written):
  `AdapterInvocationError(kind="unparseable-output")`.

### 5. Engine dispatcher — `engine.py`

`execute_with_engine_context` currently only dispatches to
`run_pytest`. Add a branch on `engine_context.engine_name == "jest"`
to call `run_jest(...)`. Pass `collect_coverage` through (no-op for
now but plumbed for future).

### 6. Normalization — `normalizer.py`

`normalize_native_result` is shaped for pytest's JSON. Either:

- **(a)** Generalize via a discriminator (`engine_name` lookup +
  per-engine normalizer functions). Cleanest long-term.
- **(b)** Add a parallel `normalize_jest_native_result` and switch in
  `engine.py` based on `engine_context.engine_name`. Simpler this
  slice.

PM permits either; document the choice in the handoff. If you pick
(a), keep the change scoped to this slice — no speculative
refactoring of the pytest normalizer.

### 7. Fixture — `tests/fixtures/projects/jest-basic/`

Minimum content:

```
jest-basic/
├── package.json        # name, jest in devDependencies, "test": "jest"
├── README.md           # documents the contract
├── src/
│   └── math.js         # 1-2 simple functions
└── __tests__/
    └── math.test.js    # 2-3 passing tests
```

Keep it small. No `node_modules` checked in. Tests will run jest from
the dev venv's path; readiness probe will need to handle the case where
the fixture's `node_modules` isn't installed yet (probably
`engine-misconfigured` until `npm install` runs — document in the
fixture README).

### 8. Tests

- `tests/unit/run/adapters/test_jest_adapter.py` — parallel to
  `test_pytest_adapter.py`. Use a stubbed subprocess (`monkeypatch
  run_subprocess`) so the unit tests do not require `node` on the host.
- `tests/unit/run/test_engine_jest.py` (NEW or append to existing
  `test_engine.py`) — assert `execute` dispatches to `run_jest` for
  jest-engine targets.
- `tests/unit/run/test_readiness_jest.py` (NEW or append to existing
  `test_readiness.py`) — assert jest workspaces get a meaningful
  readiness verdict (test with + without `node` available via
  `monkeypatch shutil.which`).
- `tests/integration/run/test_jest_basic.py` (NEW) — skip with
  `pytest.skip("requires node + npm")` if `shutil.which("node") is None`
  OR `shutil.which("npx") is None` OR jest can't be invoked. When all
  preconditions met, run the adapter against the fixture's
  `tests/fixtures/projects/jest-basic/` and assert passed counts +
  artifact paths. CI behavior: today's CI matrix has no Node — this
  test will skip everywhere in CI. **Document that in the test
  docstring**; the test is for local-dev / future CI matrix.

**Note on CI matrix:** This slice does NOT modify `ci.yml`. The jest
adapter tests' integration cell will skip in current CI. A separate
Release-side slice (out of scope here) can later add Node.js to the
matrix when more JS adapters land. For this slice, local-dev coverage
+ skip-in-CI is sufficient.

## Files to write / modify

- `src/novetest/run/adapters/jest_adapter.py` (NEW)
- `src/novetest/run/engine_selector.py` — extend `_ecosystem_for_workspace`
  if needed; add jest case to `select_native_engine`
- `src/novetest/run/readiness.py` — extend `assess_engine_readiness`
  to validate jest readiness
- `src/novetest/run/engine.py` — dispatch jest in `execute_with_engine_context`
- `src/novetest/run/normalizer.py` — add jest normalization path
  (Option a or b per above)
- `src/novetest/run/types.py` — only if needed for new error subtypes;
  prefer reusing the existing `NativeResult` / `AdapterInvocationError`
  shapes
- `src/novetest/run/__init__.py` — export `run_jest` if a similar
  public surface is wanted (mirror what's exported for `run_pytest`)
- `tests/fixtures/projects/jest-basic/` (NEW) — fixture
- `tests/unit/run/adapters/test_jest_adapter.py` (NEW)
- `tests/unit/run/test_engine.py` / `test_readiness.py` — append jest
  cases
- `tests/integration/run/test_jest_basic.py` (NEW)
- `WORKLOG.md` (entry)
- `agent-comms/handoffs/run-team-2026-05-16-jest-adapter-phase1.md`

## Files NOT to touch

- `src/novetest/cli/**`, `src/novetest/orchestration/**` — Orchestration
  team; the existing `novetest run` handler already dispatches engine-agnostically.
- `src/novetest/coverage/**` — Coverage team; jest coverage emission
  is deferred.
- `src/novetest/memory/**`, `src/novetest/models/**`.
- `pytest_adapter.py` — out of scope unless minimal shared-helper
  extraction (e.g. `_write_native_artifact_log` shared between pytest
  and jest). Prefer mirror-without-refactor; refactor in a follow-up
  if a third adapter motivates it.
- `pyproject.toml` — no Python dep changes (jest is a runtime
  Node-side dep, not Python).
- `.github/workflows/**` — Release team's territory; this slice does
  not modify CI matrix.
- `agent-comms/decisions/**`, `history/**` — PM only.

## Verification commands

```sh
# Unit tests (no node required — uses stubbed subprocess)
uv run pytest -q tests/unit/run

# Full suite (baseline + new — jest integration will skip locally if no node)
uv run pytest -q tests/unit tests/integration

# mypy --strict
uv run mypy

# Manual smoke against the new fixture (requires node + npm locally)
cd /tmp && rm -rf jest-basic-smoke
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/jest-basic jest-basic-smoke
cd jest-basic-smoke
npm install --no-audit --no-fund                                  # one-time
uv run --with /home/yjshin/dev/Nove-Test novetest init
uv run --with /home/yjshin/dev/Nove-Test novetest run __tests__/  # or whatever target syntax jest accepts
```

The smoke confirms:
1. `novetest init` against a JS workspace reports engine_readiness ready
   (jest detected, node available).
2. `novetest run <target>` returns exit 0, `RunRecord.status == "passed"`,
   artifact paths point at the captured `jest-results.json` + logs.

## DoD bullets to claim closed

**None.** This slice is Phase 2.5 entry infrastructure. No
`delivery-phasing.md` bullet closes directly from this slice — DoD
bullets in Phase 2 are pytest-coverage-shaped; Phase 3+ regression/
localization bullets require Coverage Facts from jest (deferred).

Document this honestly in the handoff: "No DoD ticked; this slice
unblocks the Coverage team's future Istanbul-parser slice (which
together close the cross-engine portion of Phase 2.5 / Phase 3)."

## Reporting (handoff)

Write `agent-comms/handoffs/run-team-2026-05-16-jest-adapter-phase1.md`
with standard sections:

- Worktree path + branch + base commit.
- Files written/modified.
- Normalizer choice: Option (a) generalized or (b) parallel function.
  Rationale.
- pytest counts (new total) + mypy result.
- Local manual smoke result (if you have node available) or "skipped
  locally; CI will exercise once Node.js is added to the matrix" if
  not.
- WORKLOG entry text (paste).
- DoD bullets believed closed: **none**.
- Open items / surprises — especially:
  - CI matrix doesn't include Node.js yet; recommend a Release-side
    slice to add it.
  - Coverage emission deferred; once Coverage team adds Istanbul
    parser, jest's `collect_coverage=True` becomes the natural
    follow-up.

Append WORKLOG entry. Run `python3 tools/regen_comms_index.py`.
Stage WORKLOG + handoff + INDEX alongside source.

## Out of scope (do NOT do these in this task)

- jest `--coverage` emission (Istanbul JSON) — needs Coverage team's
  parser slice; this adapter accepts `collect_coverage` kwarg but is a
  no-op when True (or raises `NotImplementedError` — your choice;
  document).
- jest TypeScript (`ts-jest`) configuration — add later if a fixture
  needs it.
- Vitest as alternate adapter — OQ #7, post-MVP.
- Static `it()` enumeration via TS/JS AST parser — OQ #8, post-MVP.
  Discovery in this slice is file-level via `--listTests`-equivalent
  if needed (probably not needed — `--json` output already enumerates
  per-test results).
- Modify CI matrix (`ci.yml`) to add Node.js. Recommend in the handoff;
  Release team's call.
- Other ecosystems (go test, junit, dotnet, cargo) — separate slices.
- Generalize normalizer to a registry of `(engine_name → normalizer_fn)`
  beyond what's needed for two adapters — wait until a third lands.

## Why this task exists

`engine-adapters.md` Section 2 has documented jest as the JS/TS Tier-1
adapter since project inception, but no execution path has existed.
With Phase 2 (pytest coverage) substantively closing, this is the
natural moment to verify the adapter pattern generalizes — before
Phase 3/4/5 try to write cross-engine logic. The Run team's prior
pytest-adapter slices established the shape; this slice exercises that
shape on a structurally different native engine, surfacing any
hardcoded-to-pytest assumptions while they're cheap to fix. Coverage
emission's deferral keeps this slice scoped to a clean
Phase-1-equivalent: a JS user can `novetest init` + `novetest run` and
get a structured pass/fail result, exactly as a Python user has been
able to since Phase 1.
