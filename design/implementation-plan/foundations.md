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

- **Async-first for I/O.** All subprocess invocation, file I/O against the run directory, and SQLite writes go through `asyncio`. Wrap synchronous CLI entrypoints with `asyncio.run(main_async())` at the boundary.
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

**Decision: Hybrid - SQLite (WAL mode) for the index, filesystem tree for record JSON and native artifacts, content-addressed blob store for dedup. Stdlib `sqlite3`. No ORM.**

Walking through the alternatives (this is part of the long-lived rationale):

| Option | Verdict |
| --- | --- |
| Pure filesystem JSON tree | Simple but every list/filter command becomes O(n) directory walk + re-parse. Tombstones become rename-to-`.deleted` with no consistency. **No.** |
| Pure SQLite | Workable but inflates the DB with multi-MB native artifacts (JUnit XML, `.coverage`), bloats backups, and prevents engines from writing directly to a stable path. |
| DuckDB | Tempting for analytics over historical SBFL, but our hot paths are point lookups and small range scans - SQLite's wheelhouse. Load DuckDB on demand for ad-hoc analytics if/when needed. |
| lmdb | Fast but you reinvent every secondary index. **No.** |
| Hybrid (chosen) | SQLite holds queryable metadata; engines write native artifacts to a stable filesystem path under the run directory. |

### Layout

```
$NOVETEST_HOME/                                 # default ~/.novetest
  index.db                                      # SQLite, WAL
  runs/
    2026/05/11/
      run_01HXYZ.../                            # ULID-named, sortable, unique
        record.json                             # canonical Run Record (also indexed)
        native/
          junit.xml
          pytest-report.json
          coverage.sqlite
          stdout.log
          stderr.log
        coverage_facts.json
        regression_facts.json
        localization_findings.json
        replay_result.json
  blobs/
    sha256/ab/cd/abcd...                        # dedup'd large artifacts
  schema_migrations.lock
```

`$NOVETEST_HOME` overridable via env var; tests use `tmp_path`.

### SQLite schema sketch (illustrative; finalize during Phase 1)

```sql
CREATE TABLE run (
  run_id          TEXT PRIMARY KEY,             -- ULID
  created_at      INTEGER NOT NULL,             -- epoch ms
  target          TEXT NOT NULL,                -- normalized target expression
  engine          TEXT NOT NULL,                -- pytest|jest|junit|gotest|cargo|dotnet
  status          TEXT NOT NULL,                -- passed|failed|errored|tombstoned
  schema_version  INTEGER NOT NULL,
  record_path     TEXT NOT NULL,                -- relative path to record.json
  tombstoned_at   INTEGER
);
CREATE INDEX run_created_idx ON run(created_at DESC);
CREATE INDEX run_target_idx  ON run(target, created_at DESC);
CREATE INDEX run_engine_idx  ON run(engine, created_at DESC);

CREATE TABLE test_outcome (
  run_id      TEXT NOT NULL REFERENCES run(run_id),
  nodeid      TEXT NOT NULL,
  outcome     TEXT NOT NULL,
  duration_ms INTEGER,
  PRIMARY KEY (run_id, nodeid)
);
CREATE INDEX test_outcome_nodeid_idx ON test_outcome(nodeid, run_id);

CREATE TABLE schema_migration (
  version    INTEGER PRIMARY KEY,
  applied_at INTEGER NOT NULL
);
```

Coverage / regression / localization fact tables get added in their respective phases. The pattern: small queryable rows in SQLite, full fact bundle in JSON next to `record.json`.

### SQLite settings

```python
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA synchronous = NORMAL")
conn.execute("PRAGMA busy_timeout = 5000")
conn.execute("PRAGMA foreign_keys = ON")
```

Use `BEGIN IMMEDIATE` for write transactions to fail fast instead of deadlocking concurrent writers.

### Why no ORM

- ~10 tables. SQLAlchemy is overkill, hides the SQL, and slows CLI startup.
- Hand-rolled per-entity repository module under `memory/`. Each repository's job is to map between domain dataclasses and SQL rows.

### Schema versioning

- `schema_version: int` stamped on every `record.json` and every SQLite row.
- Forward-only migrations under `memory/migrations/0001_init.sql`, `0002_*.sql`, ...
- Tracked in `schema_migration` table.
- **Never edit a migration after release.** Always add a new one.
- Domain-model migrations on read: `models/migrations.py::upgrade_run_record(d, from_v) -> dict` chains. Old records remain readable forever.

### Tombstones

`memory delete <run_id>` does not delete the record. It sets `status = 'tombstoned'`, sets `tombstoned_at`, and (optionally, configurable) moves the run directory to `runs/_tombstoned/`. Evidence Citations elsewhere in the system remain resolvable; the tombstone is the contract that lets us promise this without leaking storage forever (a future `vacuum` command can hard-delete tombstones older than N days).

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
      app.py                          # Cyclopts root app + subapp wiring
      output.py                       # JSON envelope, NDJSON streamer, exit codes
      target.py                       # --target resolution / project-root walk
    orchestration/
      __init__.py
      workflows/
        integrated_test.py            # novetest test [target]
        inspect.py
        compare.py
        status.py
      recommendation/
        synthesizer.py                # rule-based; see recommendation-synthesis.md
        citations.py
      eligibility.py                  # evaluate_stage_eligibility
    run/
      __init__.py
      engine.py                       # execute / execute_with_engine_context
      target_resolver.py              # resolve_test_target
      engine_selector.py              # select_native_engine + list_supported_engine_pairs
      normalizer.py                   # normalize_native_result
      adapters/
        __init__.py                   # registry, decorator-based
        base.py                       # NativeAdapter Protocol
        pytest_.py                    # trailing underscore: avoid stdlib name clash
        jest.py
        junit.py
        gotest.py
        cargo.py
        dotnet.py
    memory/
      __init__.py
      store.py                        # SQLite + filesystem facade
      run_repository.py
      tombstone.py
      migrations/
        0001_init.sql
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
2. **`NOVETEST_HOME` is `tmp_path`-scoped per test.** Never let tests touch the user's real home.
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
curl -fsSL https://get.novetest.dev/install.sh | sh
```

What the script does:
1. Detects OS + arch (`uname -s` / `uname -m`).
2. Downloads the matching PyApp binary from the latest GitHub Release.
3. Verifies SHA-256 against the sidecar checksum file.
4. Installs to `~/.local/bin/novetest` (sudo-free, XDG-standard, on `PATH` for modern Linux/macOS).
5. Prints a one-line `PATH`-add hint if `~/.local/bin` is not already on `PATH`.

Re-running upgrades. Idempotent.

Target platforms (Phase 0 scope): `linux-x86_64`, `linux-aarch64`, `macos-arm64`, `macos-x86_64`. Windows is a follow-up via a parallel `install.ps1`; it is not a Phase 0 blocker.

This is the only path the README headlines and the only path AI agents in onboarding flows are expected to suggest. It is also the path AI coding tools (Cursor, Claude Code, Cline, etc.) can run as a single tool call when a user asks them to set up Nove Test.

### What ships behind the script - PyApp single binaries

[PyApp](https://ofek.dev/pyapp/) (by Ofek Lev, Hatch maintainer) wraps a Python wheel into a Rust-built single binary. On first run, it downloads a pinned CPython distribution from `python-build-standalone` into the user's data dir and installs the bundled wheel. Subsequent runs are instant.

Pipeline: GitHub Actions matrix builds wheels with `uv build`, then PyApp wraps the wheel per target. Each release publishes the binaries with sidecar `*.sha256` files via `gh release create`. Total release pipeline ~50 lines of YAML.

Tradeoff: first-run latency (5-15 s while CPython downloads). Acceptable for a CLI installed once. Document in README.

### Tier 2 - Direct binary download

For users who want to inspect the install script before running it, hermetic CI environments that pin by hash, or air-gapped scenarios:

```bash
curl -fsSL https://github.com/nove/novetest/releases/latest/download/novetest-linux-x86_64 -o novetest
curl -fsSL https://github.com/nove/novetest/releases/latest/download/novetest-linux-x86_64.sha256 -o novetest.sha256
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
| **Default for everyone (any language SuT)** | `curl -fsSL https://get.novetest.dev/install.sh \| sh` |
| Inspect-first users / hermetic CI | Direct binary download + SHA-256 verify (Tier 2 above) |
| macOS / Linux Homebrew users | `brew install nove/tap/novetest` (once the tap is published) |
| Python developers | `uv tool install novetest` or `pipx install novetest` |

---

## Cross-References

- Adapter implementations are detailed in [`engine-adapters.md`](./engine-adapters.md).
- The recommendation synthesizer that lives under `orchestration/recommendation/` is detailed in [`recommendation-synthesis.md`](./recommendation-synthesis.md).
- The SBFL implementations under `localization/sbfl/` are detailed in [`localization-strategy.md`](./localization-strategy.md).
- Phasing of the work above is in [`delivery-phasing.md`](./delivery-phasing.md).
