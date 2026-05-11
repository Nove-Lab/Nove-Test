## Source Structure

All code lives under a single import root `novetest`. Transports (`cli/`, `mcp/`) are peers to the engines: they own user-facing concerns (argument binding, JSON envelope, exit codes) and contain no business logic.

```
src/novetest/                   # Single import root (one PyPI distribution: novetest)
├── cli/                        # CLI transport (Cyclopts root, JSON envelope, exit codes)
├── orchestration/              # Top-level orchestration layer
│   ├── workflows/              # Workflow coordination
│   └── recommendation/         # Recommendation synthesis
├── run/                        # Run engine
│   └── adapters/               # Native test engine adapters
├── memory/                     # Memory engine
├── coverage/                   # Coverage engine
├── regression/                 # Regression engine
├── localization/               # Localization engine
│   └── sbfl/                   # SBFL algorithms
├── replay/                     # Replay engine
├── models/                     # Shared domain model entity definitions
├── utils/                      # Shared low-level utilities
└── mcp/                        # MCP transport (Phase 6 / future)
```

---

## Testing Rules

### Unit Tests

- Core implementation logic must always be accompanied by unit tests.
- Unit tests must be placed under the top-level `tests/` directory.
- The test directory structure should mirror the corresponding `src/` structure whenever possible.

### Integration Tests

- Workflow-level behavior should be covered by integration tests under `tests/integration/`.
- Cross-component orchestration behavior should be validated through integration tests when architectural workflows or component interactions are introduced or modified.


### Fixture Projects

Nove Test uses controlled fixture projects to validate behavior across native test ecosystems.

Fixture projects:
- simulate software under test for Nove Test
- validate workflows involving native engine adapters and result normalization
- are deterministic, small, isolated, and self-contained test assets owned by the repository
- should avoid unnecessary real-world complexity

Fixture projects should be placed under:

```plaintext
tests/
└── fixtures/
    └── projects/
```

Example fixture projects:

```plaintext
tests/fixtures/projects/
├── pytest-basic/
├── pytest-coverage/
├── flaky-python/
├── junit-basic/
└── localization-branch/
```

---

## Multi-Agent Worklog Harness

Multiple Claude agents work on this repo across sessions. The rules below keep them in sync without external state.

### Pre-flight (before any code change)

Read these in order; skip what is clearly unrelated to the task.

1. `WORKLOG.md` — top 3 entries. What was just landed, what was left open, what to do next.
2. `design/implementation-plan/delivery-phasing.md` — locate the current phase; unchecked `- [ ]` DoD bullets are the canonical todo.
3. `design/interace-contract/<engine>.md` and `design/workflows/<engine>.md` for each engine the task touches.
4. `design/implementation-plan/foundations.md` for cross-cutting infra concerns.

In-session sub-tasks belong in TaskCreate, not on disk.

### Post-flight (before `git commit` of `src/` or `tests/` changes)

1. Append a new entry to the top of `WORKLOG.md` using the format documented in that file.
2. Tick (`- [x]`) any DoD bullets in `delivery-phasing.md` that this commit fully satisfies. Do not tick partial work.
3. Stage `WORKLOG.md` (and `delivery-phasing.md` if changed) in the same commit as the code.

A `PreToolUse` hook (`.claude/hooks/check-worklog-before-commit.sh`) blocks `git commit` when `src/` or `tests/` are staged but `WORKLOG.md` is not. To bypass intentionally (e.g. pure refactor that does not warrant a log entry), stage `WORKLOG.md` with a single new line — but prefer a real entry.
