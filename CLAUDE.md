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

## Testing Rules

- Core implementation logic must always be accompanied by unit tests.
- Unit tests must be placed under the top-level `tests/` directory.
- The test directory structure should mirror the corresponding `src/` structure whenever possible.