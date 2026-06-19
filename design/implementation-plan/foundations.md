# Implementation Plan - Foundations

**Scope:** Cross-cutting implementation decisions that all sub-products inherit. Language choice, CLI framework, subprocess management, persistence, project structure, self-testing, and distribution.

**Upstream**
- Index: [`index.md`](./index.md)
- Architecture: [`design/product-plans/overall-architecture.md`](../product-plans/overall-architecture.md)
- Interface contracts: [`design/interace-contract/`](../interace-contract/)
- Project structure hint: [`CLAUDE.md`](../../CLAUDE.md)

---

## 1. Language and Runtime

**Decision: Python 3.11 as the floor; CI matrix runs 3.11 / 3.12 / 3.13.**

Why Python and not Rust / Go / Node / Java:
- The dominant native engine in our primary first-class ecosystem is `pytest`. Its machine outputs (`pytest-json-report`, `coverage.py` SQLite, JUnit XML) all have first-class Python parsers. In Rust / Go / Node we would re-implement parsers.
- The primary user is an AI agent. JSON-first ergonomics matter more than peak runtime speed. Python's `json` + `dataclasses` is one-line to serialize; serde-style boilerplate in Rust or Go is a tax paid forever.
- SBFL is matrix work over a (tests x lines) coverage matrix. `numpy` exists; rolling our own in Go is wasted effort.
- The repo's snake_case `src/` layout in [`CLAUDE.md`](../../CLAUDE.md) already commits to Python idioms.

Why not earlier than 3.11:
- `tomllib` is in the stdlib at 3.11+ (no `tomli` runtime dep).
- `ExceptionGroup` and `except*` make fan-out subprocess error handling tractable.
- `StrEnum`, `Self` typing, and faster startup compared to 3.10.
- 3.10 buys nothing extra against 3.11.

Why not 3.13 as the floor:
- 3.13 is fine but not yet ubiquitous in CI base images and corp environments. 3.11 is the sweet spot - new enough for the features we want, old enough that any LTS distro / corp Python has it.

**`python_requires = ">=3.11"` in `pyproject.toml`. Test on 3.11/3.12/3.13.**

### Runtime style

- **Async-first for I/O.** Subprocess invocation and concurrent file I/O against the run directory go through `asyncio`. Wrap synchronous CLI entrypoints with `asyncio.run(main_async())` at the boundary. (The derived SQLite index forward-noted below is deferred until a cross-run aggregation verb lands; when introduced, it can remain synchronous behind the `memory` façade — that's a decision for that day.)
- **Type hints everywhere.** `mypy --strict` in CI. Domain entities are dataclasses with full annotations.
- **Avoid metaclasses, multiple inheritance, dynamic dispatch tricks.** AI agents read this code; clarity beats cleverness.

---

## 2. CLI Framework and Output Contract

**Decision: Cyclopts. Click is the conservative fallback if Cyclopts proves immature for a use case we hit.**

| Option | Verdict |
| --- | --- |
| `argparse` | stdlib, no dep, but ~15 subcommands across 6 sub-products + JSON envelope wrapping = too much hand-rolled boilerplate. Skip. |
| Click | Boring, correct, mature, decorator-based, excellent test runner (`click.testing.CliRunner`), great Windows support. The safe default. |
| Typer | Type-annotation veneer over Click. Long-standing rough edges with `Annotated`, `--no-flag` semantics, and Pydantic v2. Spotty release cadence. **Avoid.** |
| Cyclopts | Newer, 3.10+ native, designed around `Annotated` + modern hints, first-class union/literal/dataclass parameter binding, clean nested command groups. **Best ergonomics for our shape.** |

Cyclopts maps cleanly to our command tree (`novetest <subproduct> <verb>`):

```python
from cyclopts import App
app = App(name="novetest")
memory_app = App(name="memory")
app.command(memory_app)

@memory_app.command
def list(filter: MemoryFilter | None = None) -> None: ...

@memory_app.command
def show(run_id: RunReference) -> None: ...
```

If Cyclopts ever blocks us, swapping to Click is a contained migration: keep the command tree shape, replace decorators, re-route output.

### Onboarding commands

Three commands sit above the sub-product tree and bind to [`design/interace-contract/orchestration.md`](../interace-contract/orchestration.md) §1. They must remain callable without an initialized Project Store - the CLI must dispatch them before any `locate_project_store` lookup runs.

| Command | Bound interface | Notes |
| --- | --- | --- |
| `novetest -v` / `novetest --version` | `orchestration/report_cli_identity` | Returns CLI Installation identity (version, command name, build/platform). Snapshot-tested for envelope stability from Phase 0. |
| `novetest -h` / `novetest --help` | `orchestration/describe_command_surface` | Returns the full command surface for onboarding + operating commands. Cyclopts's default help is post-processed into our JSON envelope when `--output json` is selected. |
| `novetest init` | `orchestration/initialize_project_workspace` | Composes `memory/create_project_store` (idempotent) + `run/assess_engine_readiness` (informational). Engine-missing or engine-misconfigured outcomes do **not** roll back the created store; the envelope carries the readiness state so the caller (agent or human) can act on it. |

### Output contract (binding for every command)

Every subcommand emits one of two shapes; never both, never mixed.

**Single envelope (default):**

```json
{
  "schema": "novetest/v1",
  "command": "memory.show",
  "ok": true,
  "data": { ... },
  "errors": [],
  "warnings": []
}
```

**NDJSON stream** (used by `novetest run --stream`, the integrated `novetest test --stream`, and any future long-running agent-facing command). One JSON object per line, no trailing comma, with the same envelope schema applied to each event.

### Mode selection

- Global flag `--output {text,json,ndjson}`.
- Default is `text` on a TTY, `json` otherwise (`not sys.stdout.isatty()`).
- Override via `NOVETEST_OUTPUT=json` env var. AI agents will set this; humans get pretty output by default.

### Logging vs output

- **stdout is reserved for the structured envelope or NDJSON stream.** Nothing else, ever.
- Logs go to stderr via `logging` with a stderr handler.
- Cyclopts/Click error/help messages also go to stderr (verify this when picking the framework).
- ANSI: when `--output json/ndjson` is selected, set `NO_COLOR=1` and `force_color=False` before any third-party formatter runs.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Generic Nove Test failure |
| 2 | Usage error (bad flags, unknown command) |
| 3 | The user's tests failed - **not a Nove Test failure**. Distinguish from 1. |
| 4 | Native engine missing or misconfigured (e.g. `pytest` not found, `pytest-json-report` not installed) |
| 5 | Storage corruption / migration failure |

These codes are part of the contract; AI agents will branch on them.

---

## 3. Subprocess Management

**Decision: `asyncio.create_subprocess_exec` with concurrent stdout/stderr drains and layered timeout handling. Do not use threads-around-`subprocess.Popen`.**

The naive `subprocess.Popen(...).communicate()` model deadlocks on Windows when one of the pipes fills before the other is read. Threads around `Popen` paper over it but introduce their own coordination bugs. Async drains both streams concurrently and is the right primitive.

### Canonical invocation

```python
proc = await asyncio.create_subprocess_exec(
    *argv,
    stdin=asyncio.subprocess.DEVNULL,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=str(target_cwd),
    env=sanitized_env,
    creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    start_new_session=(os.name != "nt"),
)

stdout_task = asyncio.create_task(_drain(proc.stdout, on_stdout_line))
stderr_task = asyncio.create_task(_drain(proc.stderr, on_stderr_line))
try:
    rc = await asyncio.wait_for(proc.wait(), timeout=timeout_s)
finally:
    await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
```

Both pipes drain concurrently; full-buffer deadlock is structurally impossible.

### Encoding

Force UTF-8 in the child to defeat platform default encoding drift (cp1252 mojibake on Windows JUnit XML is a common bug):

```python
sanitized_env["PYTHONUTF8"] = "1"
sanitized_env["PYTHONIOENCODING"] = "utf-8"
sanitized_env["DOTNET_CONSOLE_ENCODING"] = "utf-8"
```

Read with `errors="replace"` so corrupt bytes never crash a parse.

### Timeouts

Layered:

1. **Soft** - SIGTERM (POSIX) or `CTRL_BREAK_EVENT` (Windows), then wait N seconds for the engine to flush its native report.
2. **Hard** - SIGKILL / `TerminateProcess` plus `os.killpg` / `taskkill /T /F` to clean up workers (pytest-xdist workers, jest workers, `cargo test` forks).

A hard kill that orphans worker descendants leaves file locks on the run directory; clean up the whole tree.

### Signal propagation

- Parent installs handlers for SIGINT/SIGTERM (Windows: SIGBREAK / console control event handler).
- On signal, propagate to the child group, drain pipes, then re-raise so the parent exits with the conventional 128+signum code.

### Working directory and environment

- `cwd` is **always** the target project root, never the CLI's own CWD. Resolve from explicit `--target` or auto-detect by walking up looking for `pyproject.toml` / `package.json` / `go.mod` / `Cargo.toml` / `pom.xml` / `*.csproj` / `*.sln`.
- **Sanitize env on an allow-add model.** Start from `os.environ.copy()`, then unset known-poisonous variables (`PYTHONDONTWRITEBYTECODE`, conflicting `VIRTUAL_ENV`, `PYTEST_ADDOPTS` unless explicitly preserved), and set deterministic ones (`PYTHONHASHSEED=0`, `CI=1`, `FORCE_COLOR=0`).
- **Respect virtualenvs.** If `target/.venv/bin/pytest` (or `Scripts\pytest.exe` on Windows) exists, use it. Otherwise fall back to `python -m pytest`. Never call bare `pytest` - PATH leakage is a recurring bug source.

### Library policy

Do not pull in `sh`, `plumbum`, or `delegator`. They paper over the platform issues we specifically need to handle ourselves. `psutil` is acceptable for the "find and kill orphan worker descendants" path, which is genuinely hard portably.

---

## 4. Persistence

**Decision: Project-scoped Project Store at `<project_root>/.novetest/`. File-only persistence for every MVP phase (Phase 0-6): `record.json` files under a ULID-encoded directory layout that provides O(1) point lookups and naturally sorted Run History without an index database. A derived SQLite index is **deferred until a cross-run aggregation verb lands** (no such verb in MVP scope; per [`decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md`](../../agent-comms/decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md)); when introduced, that index is a cache, not a source of truth, and can be rebuilt from `record.json` files at any time. One subdirectory per sub-product so each engine owns its own artifacts.**

The per-project store is the only durable state Nove Test owns. There is no shared user-level database; every run, fact, and recommendation lives next to the project it was produced for, matching the UX goal in [`design/product-plans/ux-goal.md`](../product-plans/ux-goal.md) §3.

### Why file-only first (and SQLite only when warranted)

Memory must serve exactly these query patterns through Phase 4:

1. Point lookup by `run_id` (Memory `retrieve_run_evidence`, every sub-product's read path).
2. Latest N runs by `created_at` (Memory `list_run_history`, Status, Localization latest).
3. Filter by Test Target + latest (Regression `find_runs_for_target` baseline resolution).
4. Filter by analyzability + latest (Localization `find_latest_analyzable_run`).
5. Tombstone state transition (`delete_run_evidence`).

ULID-as-`run_id` already encodes a millisecond timestamp in its first 10 characters. That single fact resolves queries 1-2 without an index:

- `run_id` → `runs/YYYY/MM/DD/run_<ulid>/record.json` is **computable**. Point lookup is one `open(2)`.
- Listing latest N is a reverse-chronological walk of `runs/YYYY/MM/DD/`; ULID lexicographic order within a day is creation order.

Queries 3-4 require reading `record.json` to inspect target/availability. At Phase 1-3 scale (dozens to a few thousand runs per project) this is acceptable. When it stops being acceptable, a small marker-file index (`runs/by_target/<hash>/<ulid>`, materialized on write) closes the gap in ~30 LOC without introducing SQL. Tombstoning is a POSIX-atomic `rename(2)` from `memory/runs/...` to `memory/tombstones/...` — no consistency primitive beyond the filesystem is required.

The one query pattern this layout cannot serve cheaply is **per-test cross-run history**: "for nodeid X, what was its outcome in the last 50 runs?" No verb currently shipped or scheduled in the MVP surfaces this query (Regression compare is pair-compare; Replay classify is pair-compare + in-session N-rerun; Coverage/Localization read per-run). That query would first surface if and when a cross-run aggregation verb is added (e.g. a hypothetical `novetest memory flakiness <nodeid>` post-MVP). At that point — and only at that point — we introduce SQLite as a derived index built from existing `record.json` files; the DB is rebuildable, the schema is designed against the actual query set rather than speculation, and `record.json` remains the source of truth. See [`decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md`](../../agent-comms/decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md) for the original Phase 5 forecast and why it was deferred.

Walking through the alternatives (this is part of the long-lived rationale):

| Option | Verdict |
| --- | --- |
| Pure filesystem JSON tree with naive layout | Every list/filter becomes O(n) directory walk + re-parse; tombstones via rename-to-`.deleted` lack discoverability. **Skip.** |
| Pure SQLite from day one | Inflates DB with multi-MB native artifacts (JUnit XML, `.coverage`), bloats backups, prevents engines from writing directly to a stable path. **Skip.** |
| **ULID-encoded directory layout (chosen for Phase 1-4)** | ULID encodes a ms timestamp, so `run_id` → date path is computable. Point lookup O(1); latest-N is reverse-chronological walk; filter by target/engine uses lazy marker files under `runs/by_target/...` when filter cost becomes noticeable. Tombstone via `rename(2)` is POSIX-atomic. No schema lock-in. |
| **SQLite as derived cache index (deferred until a cross-run aggregation verb lands)** | Introduced when per-test cross-run queries actually surface in a CLI verb. Built from `record.json` files; rebuildable; schema designed against actual usage. No such verb is in the MVP roadmap. |
| DuckDB | Tempting for SBFL analytics, but hot paths are point lookups; the layout above serves them better. Defer indefinitely. |
| lmdb | Reinvents secondary indexes. **No.** |
| Per-user `~/.novetest/` shared store | Contradicts UX goal: all artifacts under `.novetest/` at project root. **No.** |

### Project Store discovery

- `novetest init` creates `.novetest/` in the current working directory and registers it as the active Project Store for that workspace (Memory `create_project_store`, see [`design/interace-contract/memory.md`](../interace-contract/memory.md) §1).
- For every subsequent command, `memory/locate_project_store` walks upward from the current working directory looking for `.novetest/`. The first match becomes the active store. Behavior is git-style: a project is "in" Nove Test as soon as an ancestor directory has `.novetest/`.
- If no Project Store is found, operating commands return a structured `uninitialized` envelope pointing the user at `novetest init`. Onboarding commands (`novetest -v`, `novetest -h`, `novetest init` itself) do not require a Project Store.
- `$NOVETEST_HOME` is **not** the default location; it is a test/CI override only. Setting it pins the active store to that directory regardless of CWD, which keeps `tmp_path`-scoped unit tests hermetic.

### Layout

```
<project_root>/.novetest/                       # the Project Store; one per project workspace
  store.json                                    # store metadata: schema_version, initializedAt, storeState
  blobs/sha256/ab/cd/abcd...                    # shared content-addressed dedup store
  memory/                                       # Memory owns Run Records + tombstones (no index DB in Phase 1-4)
    runs/
      2026/05/11/run_01HXYZ.../                 # ULID-named run directory; canonical Run Record lives here
        record.json                             # source of truth for the run; ULID encodes created_at
    tombstones/
      run_01HXYZ.../                            # tombstoned Memory Entries; Run Reference still resolvable
    by_target/                                  # (Phase 3+, lazy) marker files for target filter acceleration
    by_engine/                                  # (Phase 3+, lazy) marker files for engine filter acceleration
    # index.db                                  # (deferred) derived SQLite cache; introduced only when a cross-run aggregation verb lands
  run/                                          # Run engine artifacts: raw native outputs and readiness probes
    artifacts/
      run_01HXYZ.../
        native/
          junit.xml
          pytest-report.json
          coverage.sqlite                       # raw native coverage payload (kept here, not under coverage/)
          stdout.log
          stderr.log
    readiness/
      latest.json                               # most recent assess_engine_readiness result (cached)
  coverage/                                     # Coverage Facts derived from native coverage payloads
    facts/
      run_01HXYZ.../
        coverage_facts.json
  regression/                                   # Regression Facts produced from run pairs
    pairs/
      run_01HXYZ__run_01HABC/
        regression_facts.json
  localization/                                 # Localization Findings per analyzable run
    findings/
      run_01HXYZ.../
        localization_findings.json
  replay/                                       # Replay Results per original run
    results/
      run_01HXYZ.../
        replay_result.json
  orchestration/                                # top-level outputs: recommendations, status snapshots
    recommendations/
      run_01HXYZ.../
        recommendation.json                     # cited Recommendation set for the run
    status/
      latest.json                               # most recent computed Status view (cache)
```

Each engine owns its subdirectory exclusively; cross-engine read access goes through Memory's interfaces, not by reaching into a peer engine's directory. This mirrors the contract boundaries in `design/interace-contract/`.

### Record format and schema versioning

- Every `record.json` (and every fact bundle written by Coverage / Regression / Localization / Replay) carries a `schema_version: int`. v1 is the Phase 1 freeze.
- Domain-model migrations are applied on read: `models/migrations.py::upgrade_run_record(d, from_v) -> dict` chains forward. Old records remain readable forever; we never rewrite written `record.json` to a newer schema.
- The `run_id` is a ULID; its first 10 characters encode `created_at` as a Crockford-base32 millisecond timestamp. This is how date-bucketed directory paths are derived without a separate index.

### Tombstones

`memory delete <run_id>` does not delete the record. It moves the run directory from `memory/runs/YYYY/MM/DD/run_<id>/` to `memory/tombstones/run_<id>/` via `rename(2)`, which is POSIX-atomic on the same filesystem. `record.json` inside is updated in place to set `status: tombstoned` and `tombstoned_at`. Evidence Citations elsewhere in the system remain resolvable through Memory's `retrieve_run_evidence`, which checks both `runs/` and `tombstones/`. A future `vacuum` command can hard-delete tombstones older than N days.

### Project Store creation (`novetest init`)

`memory/create_project_store(project_workspace)`:

1. Resolves `<project_root>/.novetest/`; refuses to write above the requested workspace path.
2. If the directory already exists with a recognized `store.json`, returns the existing handle (idempotent per REQ-MEM-006). Durable state is never overwritten.
3. Otherwise creates the directory skeleton above (top-level `blobs/`, plus an empty subdirectory per engine — including an empty `memory/runs/` and `memory/tombstones/`), and writes `store.json` with `schema_version`, `initializedAt`, and `storeState: ready`. No index database is created in Phase 1-4.
4. Returns the Project Store handle. The orchestration layer's `initialize_project_workspace` then invokes `run/assess_engine_readiness` against the workspace; that result is informational and never rolls back the store (see [`design/workflows/orchestration.md`](../workflows/orchestration.md)).

### Derived SQLite cache (forward note; deferred)

If and when a cross-run aggregation verb is added — e.g. a flakiness-rate verb that asks "for nodeid X, outcomes in the last N runs?" — a derived SQLite index materializes at `memory/index.db`. It caches `run` and `test_outcome` rows derived from `record.json` files; schema is designed against the actual query set of that verb, stamped with its own `index_schema_version` (independent of `record.json` `schema_version`), and rebuildable from scratch via `novetest reindex`. The DB is never authoritative; deleting it must always be safe. Settings: WAL journal mode, `synchronous=NORMAL`, `busy_timeout=5000`, `foreign_keys=ON`, `BEGIN IMMEDIATE` for writes. No ORM — stdlib `sqlite3` with hand-rolled repository functions, because the table count remains small. Detailed schema and migration mechanics are deferred to the design slice that introduces the cross-run verb. The original Phase 5 forecast and its deferral are recorded in [`decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md`](../../agent-comms/decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md).

---

## 5. Project Structure

**Decision: One PyPI distribution `novetest`, single import root `novetest`, sub-product submodules. Native engine adapters via decorator-based registry behind a `NativeAdapter` Protocol. `dataclasses(slots=True, frozen=True)` for internal models; `pydantic` v2 only at I/O edges.**

The structure aligns with [`CLAUDE.md`](../../CLAUDE.md):

```
src/
  novetest/
    __init__.py                       # __version__, public re-exports
    __main__.py                       # python -m novetest
    cli/
      __init__.py
      app.py                          # Cyclopts root app + subapp wiring; dispatches -v / -h / init before Project Store lookup
      output.py                       # JSON envelope, NDJSON streamer, exit codes
      target.py                       # --target resolution / project-root walk
      identity.py                     # backs `novetest -v`: composes orchestration/report_cli_identity output
    orchestration/
      __init__.py
      workflows/
        init.py                       # novetest init - calls memory/project_store.create + run/readiness.assess
        integrated_test.py            # novetest test [target]
        inspect.py
        compare.py
        status.py
      onboarding/
        identity.py                   # report_cli_identity
        command_surface.py            # describe_command_surface
      recommendation/
        synthesizer.py                # rule-based; see recommendation-synthesis.md
        citations.py
      eligibility.py                  # evaluate_stage_eligibility
    run/
      __init__.py
      engine.py                       # execute / execute_with_engine_context (calls readiness.assess at head)
      target_resolver.py              # resolve_test_target
      engine_selector.py              # select_native_engine + list_supported_engine_pairs
      normalizer.py                   # normalize_native_result
      readiness.py                    # assess_engine_readiness + detect_engine_candidates (NEVER installs)
      adapters/
        __init__.py                   # registry, decorator-based
        base.py                       # NativeAdapter Protocol (includes .detect for readiness)
        pytest_.py                    # trailing underscore: avoid stdlib name clash
        jest.py
        junit.py
        gotest.py
        cargo.py
        dotnet.py
    memory/
      __init__.py
      store.py                        # filesystem facade against the active Project Store (record.json read/write, path helpers)
      project_store.py                # create_project_store / locate_project_store / get_project_store_state
      run_repository.py               # ULID-derived path lookup, latest-N walks, tombstone rename
      tombstone.py
      # migrations/ and index.db are deferred (no MVP verb requires them); see §4 forward note
    coverage/
      __init__.py
      derive.py
      compare.py
      parsers/                        # one parser per native coverage format
        cobertura.py
        lcov.py
        jacoco_xml.py
        coverage_py_json.py
        istanbul_json.py
        gocover.py
        llvm_cov_json.py
    regression/
      __init__.py
      compare.py
      latest_baseline.py
    localization/
      __init__.py
      derive.py
      sbfl/
        ochiai.py
        op2.py
        dstar.py
        tarantula.py
        spectra.py                    # build (tests x lines) matrix from coverage facts
      modes.py                        # sbfl_per_test | sbfl_aggregate | failure_proximity
    replay/
      __init__.py
      replay.py
      reconstruct_context.py
      classify.py
    models/
      __init__.py
      run_reference.py
      run_record.py
      test_result.py
      memory_entry.py
      coverage_fact.py
      regression_fact.py
      localization_finding.py
      replay_result.py
      recommendation.py
      evidence_citation.py
      migrations.py                   # forward-only upgrade chain on read
    utils/
      __init__.py
      ulid.py
      paths.py
      logging.py
      asyncio_subprocess.py           # canonical invocation helper from section 3
    mcp/                              # Phase 6 / future
      __init__.py
      server.py
tests/
  unit/                               # mocked at NativeAdapter boundary
    ...
  integration/                        # real engines, skip when missing
    ...
  fixtures/
    projects/
      pytest-basic/
      pytest-coverage/
      flaky-python/
      junit-basic/
      jest-basic/
      gotest-basic/
      cargo-basic/
      dotnet-basic/
      localization-branch/
```

### Why one package, not seven

- Sub-products tightly share the domain model. Splitting forces a `novetest-models` base and version-coordination headaches.
- One pip install for the user. One binary for the agent.
- If a sub-product ever genuinely needs to ship independently, `pyproject.toml` entry-points + namespace packages let you split later. Don't pre-pay that cost.

### Adapter registry

```python
# run/adapters/base.py
from typing import Protocol, runtime_checkable
@runtime_checkable
class NativeAdapter(Protocol):
    name: str                                      # "pytest"
    ecosystem: str                                 # "python"
    def detect(self, target: Path) -> bool: ...
    def build_argv(self, spec: RunSpec) -> list[str]: ...
    async def parse_artifacts(self, run_dir: Path) -> NormalizedResult: ...
    def coverage_artifact_paths(self, run_dir: Path) -> list[Path]: ...

# run/adapters/__init__.py
_REGISTRY: dict[str, type[NativeAdapter]] = {}
def register(cls: type[NativeAdapter]) -> type[NativeAdapter]:
    _REGISTRY[cls.name] = cls
    return cls
def get(name: str) -> NativeAdapter: return _REGISTRY[name]()
def detect(target: Path) -> NativeAdapter | None:
    for cls in _REGISTRY.values():
        a = cls()
        if a.detect(target): return a
    return None
```

Each engine file decorates its class with `@register`; `run/engine.py` is engine-agnostic. Adding a seventh ecosystem is one PR, one file.

### Domain models

- **Internal: `dataclasses(slots=True, frozen=True)`** - cheap at import time, free hashability, immutable by default. Hand-rolled `to_dict()`/`from_dict()` per model for now; adopt `cattrs` only if it gets unwieldy past ~15 models.
- **CLI/JSON ingress: `pydantic` v2** - one boundary layer per command in `cli/`. Validate the user's flags / piped JSON, then convert to the internal dataclass. Pydantic's import time is non-trivial - keep it at the edge.

### MCP transport (Phase 6 / future)

Placed at `novetest/mcp/server.py` with its own console script:

```toml
[project.scripts]
novetest     = "novetest.cli.app:main"
novetest-mcp = "novetest.mcp.server:main"
```

The MCP server imports the same orchestration / memory / etc. modules the CLI uses; it is just a different transport. Build to this boundary from day one (no business logic in `cli/`) even though MCP transport ships later.

---

## 6. Self-Testing

**Decision: pytest, with rigid isolation between our own pytest and the fixture projects' pytest invocations.**

### Isolation rules

1. **Child invocations get a clean environment.** When `tests/test_pytest_adapter.py` invokes our `pytest` adapter against `tests/fixtures/projects/pytest-basic/`, the child pytest must run with `cwd=fixtures/pytest-basic/` and **not** inherit our dev venv's plugins. Set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` in the child unless the fixture explicitly requires a plugin.
2. **`NOVETEST_HOME` pins the active Project Store to `tmp_path` per test.** In production, the Project Store is resolved by walking up from CWD to find `.novetest/`. In tests, set `NOVETEST_HOME=<tmp_path>` so the store resolves there and the test never touches the user's real home or escapes the fixture project. `novetest init` exercises (Phase 1 onward) should call into `memory/project_store.create_project_store` directly against a `tmp_path` fixture and assert the engine-subdirectory skeleton from §4 is created.
3. **Mark subprocess tests.** Either `@pytest.mark.subprocess` or split: `tests/unit/` (no subprocess; mock at the `NativeAdapter` boundary) and `tests/integration/` (real engines; skip if not installed via `shutil.which("go") or pytest.skip(...)`).
4. **Snapshot tests for JSON envelopes** with `syrupy`. Schema stability is part of the contract with AI agents; snapshots make break-changes loud.
5. **`pytest-asyncio` in `mode=auto`.** Subprocess tests are `async def`. `anyio` is fine if abstracting the event loop matters later; not yet.
6. **Don't unit-test `asyncio.subprocess` code with `subprocess`.** They behave differently around Windows pipes. Test what we ship.

### CI matrix

- OS: Linux (ubuntu-latest), macOS (macos-latest), Windows (windows-latest)
- Python: 3.11, 3.12, 3.13
- Engine availability lanes: `minimal` (only pytest), `full` (pytest + node + java + go + rust + dotnet)

The Windows lane will catch ~80% of subprocess bugs. Do not skip it.

### Coverage-of-self

We are a coverage tool that should report its own coverage. Phase 1 sets up `coverage.py` against our own test suite as a smoke for the Coverage engine - eating dogfood early.

---

## 7. Distribution

**Decision: a one-line install script (`curl -fsSL ... | sh`) that fetches the right PyApp single binary is the Tier-1 user path. Direct binary download and language-specific package managers (`uv tool install`, `pipx install`, Homebrew) are secondary.**

**Binding philosophy:** the easiest possible immediate install plus immediate usability. A user - or an AI agent acting on their behalf - must be able to install and run Nove Test in one command, with no language-toolchain prerequisites. Specific distribution mechanics may evolve over time; this constraint does not.

User reality: a Go developer (or any non-Python SuT developer) running Nove Test must not need a Python toolchain. PyApp solves the runtime side; the install script solves the onboarding side.

### Tier 1 - One-line install script

```bash
curl -fsSL https://ailovestesting.com/novetest/install.sh | sh
```

The canonical URL and the brand namespace principle are fixed in
`agent-comms/decisions/2026-05-14-install-script-hosting-url.md`.

What the script does:
1. Detects OS + arch (`uname -s` / `uname -m`).
2. Downloads the matching PyApp binary from the latest GitHub Release.
3. Verifies SHA-256 against the sidecar checksum file.
4. Installs to `~/.local/bin/novetest` (sudo-free, XDG-standard, on `PATH` for modern Linux/macOS).
5. Prints a one-line `PATH`-add hint if `~/.local/bin` is not already on `PATH`.

Re-running upgrades. Idempotent.

Target platforms (Tier 1): `linux-x86_64`, `linux-aarch64`, `macos-universal2` (lipo-fused arm64 + x86_64), `windows-x86_64`. Windows was added on 2026-06-18 (closes Open Q #16; canonical install URL `https://ailovestesting.com/novetest/install.ps1` per the `decisions/2026-05-14-install-script-hosting-url.md` brand-namespace principle, interim raw GitHub URL per Amendment 2026-06-10; `windows-arm64` remains unsupported pending python-build-standalone — see §54).

This is the only path the README headlines and the only path AI agents in onboarding flows are expected to suggest. It is also the path AI coding tools (Cursor, Claude Code, Cline, etc.) can run as a single tool call when a user asks them to set up Nove Test.

### What ships behind the script - PyApp single binaries

[PyApp](https://ofek.dev/pyapp/) (by Ofek Lev, Hatch maintainer) wraps a Python wheel into a Rust-built single binary. On first run, it downloads a pinned CPython distribution from `python-build-standalone` into the user's data dir and installs the bundled wheel. Subsequent runs are instant.

Pipeline: GitHub Actions matrix builds wheels with `uv build`, then PyApp wraps the wheel per target. Each release publishes the binaries with sidecar `*.sha256` files via `gh release create`. Total release pipeline ~50 lines of YAML. As of 2026-06-18 the matrix covers `linux-x86_64`, `linux-aarch64`, `macos-universal2`, and `windows-x86_64`.

Tradeoff: first-run latency (5-15 s while CPython downloads). Acceptable for a CLI installed once. Document in README. Empirically pinned by the `first-run-latency-bench` job in `release-test.yml` on every release-test run since 2026-06-19; current measured cold-first-run wall: ~`<X>` s on `ubuntu-latest` GHA runners (CI log: run `<run_id>`). The bench asserts cold ≤ 25 s; sustained breach is a regression signal, not bench-tuning noise.

### Tier 2 - Direct binary download

For users who want to inspect the install script before running it, hermetic CI environments that pin by hash, or air-gapped scenarios:

```bash
curl -fsSL https://github.com/Nove-Lab/Nove-Test/releases/latest/download/novetest-linux-x86_64 -o novetest
curl -fsSL https://github.com/Nove-Lab/Nove-Test/releases/latest/download/novetest-linux-x86_64.sha256 -o novetest.sha256
sha256sum -c novetest.sha256
chmod +x novetest && mv novetest ~/.local/bin/
```

Same artifact as Tier 1; this just unwraps the install script's steps manually.

### Tier 3 - Language-specific package managers

For users who already live inside Homebrew or Python tooling:

```
brew install nove/tap/novetest        # macOS / Linux Homebrew (after tap is published)
uv tool install novetest              # Python developers with uv
pipx install novetest                 # pipx users
```

These are convenience paths for users already inside those ecosystems. They are not the recommended default and do not appear at the top of the README. They exist so that "I already have Homebrew / Python; let me use my normal manager" works without friction.

### Why not other paths

| Tool | Reason to skip as a default |
| --- | --- |
| PyInstaller | 50-80 MB artifacts, slow startup, frequent Windows AV false positives, awkward with our dynamic adapter registry. |
| Nuitka | Long build times, cross-platform debugging is hard. Keep as a fallback; not primary. |
| Docker | Adds a Docker daemon dependency; bind-mounting the target project root with uid mapping is a usability disaster on Linux. |
| `npm install -g novetest` | Requires Node toolchain on the user's machine; defeats the cross-language premise (a Go-only developer should not need Node). |

### Self-update

Ship `novetest self update` as a thin command that pulls the latest GitHub release for the user's platform, verifies signature/hash, and atomically replaces the binary. AI agents tend to keep using whatever is installed; a self-update path keeps the schema-version dance honest.

`uv` (Astral) is still used for everything development-side: lockfile (`uv.lock`), dependency resolution, virtualenv management, publishing (`uv publish`). End users do not see `uv`.

### Install matrix in README

| Audience | Command |
| --- | --- |
| **Default for everyone (any language SuT, Linux/macOS)** | `curl -fsSL https://ailovestesting.com/novetest/install.sh \| sh` |
| **Default for everyone — Windows** | `irm https://ailovestesting.com/novetest/install.ps1 \| iex` |
| Inspect-first users / hermetic CI | Direct binary download + SHA-256 verify (Tier 2 above) |
| macOS / Linux Homebrew users | `brew install nove/tap/novetest` (once the tap is published) |
| Python developers | `uv tool install novetest` or `pipx install novetest` |

### License

Nove Test ships under the **Apache License 2.0** with a Contributor License Agreement requirement for external contributions. The binding decision is `agent-comms/decisions/2026-06-10-license-apache-2.0-with-cla.md`. The Apache 2.0 surface allows immediate adoption by AI tool builders, consultancies, and BigCo internal CI environments without procurement friction; the CLA preserves Nove Lab's right to relicense future versions if strategically necessary. Commercial license inquiries route to `admin.nove@gmail.com`.

The repo-root `LICENSE`, `CLA.md`, `CCLA.md`, `CONTRIBUTING.md`, and `NOTICES.md` files carry the operative legal text. Third-party attribution for `cyclopts` (Apache-2.0), `numpy` (BSD-3-Clause), the vendored JUnit Platform Console Standalone jar (EPL-2.0, per decision `2026-06-03-junit-console-launcher-vendor.md`), PyApp (Apache-2.0 OR MIT), and python-build-standalone (PSF + permissive) is aggregated in `NOTICES.md`.

---

## Cross-References

- Adapter implementations are detailed in [`engine-adapters.md`](./engine-adapters.md).
- The recommendation synthesizer that lives under `orchestration/recommendation/` is detailed in [`recommendation-synthesis.md`](./recommendation-synthesis.md).
- The SBFL implementations under `localization/sbfl/` are detailed in [`localization-strategy.md`](./localization-strategy.md).
- Phasing of the work above is in [`delivery-phasing.md`](./delivery-phasing.md).
