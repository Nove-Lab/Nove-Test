# Workflow - Run

**Scope:** Workflow sequences for every interface defined in [`design/interace-contract/run.md`](../interace-contract/run.md), covering both Run's own interfaces (Section 1) and the native engine CLI interfaces it invokes (Section 2).

**Conventions**
- Interfaces are referenced as `module/interface_name` to make their origin traceable across documents.
- `->` denotes sequential calls inside a workflow.
- `{ A | B | ... }` denotes alternative branches at one step.
- `[optional: ...]` denotes a step that is conditional on configuration (e.g. coverage requested, target verification).
- `-` means the workflow ends inside the engine itself (no further interface call).

### Native CLI shorthand legend

The following shorthand identifiers are used in workflow sequences to keep the cells compact. Each maps one-to-one to an entry in [`design/interace-contract/run.md`](../interace-contract/run.md) Section 2.

| Shorthand | Maps to |
| --- | --- |
| `run/pytest:json-report` | `pytest <target> --json-report --json-report-file=<path>` |
| `run/pytest:junit-xml` | `pytest <target> --junitxml=<path>` |
| `run/pytest:collect` | `pytest --collect-only <target>` |
| `run/pytest:cov` | `pytest <target> --cov=<scope> --cov-report=xml:<path>` |
| `run/jest:json` | `jest <target> --json --outputFile=<path>` |
| `run/jest:list` | `jest --listTests <target>` |
| `run/jest:cov` | `jest <target> --coverage --coverageReporters=lcov --coverageReporters=json-summary` |
| `run/junit:mvn` | `mvn -q test -Dtest=<filter>` |
| `run/junit:gradle` | `gradle test --tests <filter>` |
| `run/junit:jacoco` | `mvn -q jacoco:report` / `gradle jacocoTestReport` |
| `run/go-test:json` | `go test -json <package_pattern>` |
| `run/go-test:list` | `go test -list <regex> <package_pattern>` |
| `run/go-test:cov` | `go test -coverprofile=<path> -covermode=atomic <package_pattern>` |
| `run/cargo-test:json` | `cargo test <filter> -- --format=json -Z unstable-options` |
| `run/cargo-test:list` | `cargo test -- --list` |
| `run/cargo-test:cov` | `cargo llvm-cov --json --output-path=<path>` |
| `run/dotnet-test:trx` | `dotnet test <project> --filter <expr> --logger "trx;LogFileName=<path>"` |
| `run/dotnet-test:list` | `dotnet test <project> --list-tests` |
| `run/dotnet-test:cov` | `dotnet test <project> --collect:"XPlat Code Coverage"` |

---

## 1. Run Interface Workflows

| Interface | Workflow Sequence |
| --- | --- |
| `novetest run [target]` | `run/execute` -> `memory/store_run_evidence` |
| `execute(test_target, engine?)` | `run/resolve_test_target` -> `{ pinned engine supplied: run/probe_engine \| auto-detect (legacy, until Orchestration wires pins): run/assess_engine_readiness -> run/select_native_engine }` -> `[optional discovery: { run/pytest:collect \| run/jest:list \| run/go-test:list \| run/cargo-test:list \| run/dotnet-test:list }]` -> `[test invocation: { run/pytest:json-report \| run/pytest:junit-xml \| run/pytest:cov \| run/jest:json \| run/jest:cov \| run/junit:mvn \| run/junit:gradle \| run/go-test:json \| run/go-test:cov \| run/cargo-test:json \| run/cargo-test:cov \| run/dotnet-test:trx \| run/dotnet-test:cov }]` -> `[optional separate coverage emission: run/junit:jacoco]` -> `run/normalize_native_result` -> `run/assign_run_reference` |
| `execute_with_engine_context(test_target, native_engine_context)` | `run/resolve_test_target` -> `run/assess_engine_readiness` -> `[test invocation: { run/pytest:json-report \| run/pytest:junit-xml \| run/pytest:cov \| run/jest:json \| run/jest:cov \| run/junit:mvn \| run/junit:gradle \| run/go-test:json \| run/go-test:cov \| run/cargo-test:json \| run/cargo-test:cov \| run/dotnet-test:trx \| run/dotnet-test:cov } selected per supplied native_engine_context]` -> `[optional separate coverage emission: run/junit:jacoco]` -> `run/normalize_native_result` -> `run/assign_run_reference` |
| `resolve_test_target(target_expression, workspace_context)` | - |
| `select_native_engine(test_target)` | `run/detect_engine_candidates` |
| `normalize_native_result(native_result, native_engine_context)` | - |
| `assign_run_reference(run_record)` | - |
| `list_supported_engine_pairs()` | - |
| `assess_engine_readiness(project_workspace)` | `run/detect_engine_candidates` (first candidate in canonical order is probed) |
| `probe_engine(project_workspace, ecosystem, engine_name)` | `run/detect_engine_candidates` (evidence for the named pair only; no priority fallback) |
| `detect_engine_candidates(project_workspace)` | - |

---

## 2. Native Engine CLI Workflows

Each native engine CLI is invoked by Run as a subprocess and produces a Native Result that Run normalizes. The workflow ends at the native engine boundary (Nove Test does not orchestrate further interfaces from inside the native process).

| Interface | Workflow Sequence |
| --- | --- |
| `pytest <target> --json-report --json-report-file=<path>` | - |
| `pytest <target> --junitxml=<path>` | - |
| `pytest --collect-only <target>` | - |
| `pytest <target> --cov=<scope> --cov-report=xml:<path>` | - |
| `jest <target> --json --outputFile=<path>` | - |
| `jest --listTests <target>` | - |
| `jest <target> --coverage --coverageReporters=lcov --coverageReporters=json-summary` | - |
| `mvn -q test -Dtest=<filter>` | - |
| `gradle test --tests <filter>` | - |
| `mvn -q jacoco:report` / `gradle jacocoTestReport` | - |
| `go test -json <package_pattern>` | - |
| `go test -list <regex> <package_pattern>` | - |
| `go test -coverprofile=<path> -covermode=atomic <package_pattern>` | - |
| `cargo test <filter> -- --format=json -Z unstable-options` | - |
| `cargo test -- --list` | - |
| `cargo llvm-cov --json --output-path=<path>` | - |
| `dotnet test <project> --filter <expr> --logger "trx;LogFileName=<path>"` | - |
| `dotnet test <project> --list-tests` | - |
| `dotnet test <project> --collect:"XPlat Code Coverage"` | - |

---

## Notes

- `run/execute` enumerates every Section 2 entry as either a discovery, test-invocation, or coverage-emission alternate, ensuring every native CLI is referenced in at least one upstream workflow.
- `run/execute_with_engine_context` skips `run/select_native_engine` because the native engine context is supplied (Replay path), but it still routes through the same Section 2 alternates.
- `run/normalize_native_result` and `run/assign_run_reference` are pure transformations that close every execution flow.
- `run/assess_engine_readiness` is invoked twice in the product lifetime: once by orchestration during `novetest init` (`orchestration/initialize_project_workspace`), and again at the head of every governed execution path (`run/execute`, `run/execute_with_engine_context`) so an `engine-missing` or `engine-misconfigured` outcome is surfaced as a machine-distinguishable result before any native CLI invocation. Readiness assessment never installs or configures a native engine.
