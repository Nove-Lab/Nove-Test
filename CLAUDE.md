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
