## Source Structure

```
src/
├── orchestration/              # Top-level orchestration layer
│   ├── workflows/              # Workflow coordination
│   └── recommendation/         # Recommendation synthesis
├── run/                        # Run engine
│   └── adapters/               # Native test engine adapters
├── memory/                     # Memory engin
├── coverage/                   # Coverage engine
├── regression/                 # Regression engine
├── localization/               # Localization engine
│   └── sbfl/                   # SBFL algorithms
├── replay/                     # Replay engin
├── models/                     # Shared domain model entitiy definitions
└── utils/                      # Shared low-level utilities
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
