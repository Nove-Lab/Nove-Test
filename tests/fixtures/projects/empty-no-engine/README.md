# empty-no-engine

A project workspace with no detectable native test engine. Used to validate the `engine-missing` readiness path.

## What this fixture validates

- `probe_engine(<this dir>, "python", "pytest")` must return state `engine-missing` — the workspace has no *usable* supported `(ecosystem, Native Engine)` pair from `run/list_supported_engine_pairs` (the bare `pyproject.toml` marks a generic Python project but no pytest is configured/importable, so the pytest probe reports `engine-missing`).
  - The bare `pyproject.toml` is a generic Python project marker, **not** a pytest marker: there is no `pytest` dependency, no `[tool.pytest.ini_options]`, no `pytest.ini` / `tox.ini`, no test files, no `conftest.py`.
  - No `package.json` (jest), no `pom.xml` / `build.gradle` (JUnit), no `go.mod` (`go test`), no `Cargo.toml` (`cargo test`), no `*.csproj` (xUnit / `dotnet test`).
- `novetest init` here must produce `storeState: ready` (the Project Store is created — readiness is informational) **plus** `engine_readiness: engine-missing` in the envelope. No native engine is installed or downloaded as a side effect.
- `novetest run` from this directory must return `engine-missing` with exit code 4 **before** any subprocess is spawned (NFR-RUN-004). The envelope must structurally distinguish readiness failure from internal Nove Test failure.

## Layout

```
empty-no-engine/
├── pyproject.toml   # bare [project] metadata only — no test-framework markers
└── README.md
```

This is intentionally the minimum that makes the directory a "project workspace" at all. Adding test files, plugin configs, or test-runner dependencies would defeat the fixture.
