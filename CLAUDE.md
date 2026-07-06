# Nove Test

Polyglot test orchestration tool. AI-friendly CLI emitting structured JSON envelopes for
AI-agent consumption. Single import root, one PyPI distribution: `novetest`.

## Structure

```
src/novetest/                   # Single import root
├── cli/                        # CLI transport (Cyclopts, JSON envelope, exit codes)
├── orchestration/              # Top-level workflows + recommendation synthesis
│   ├── workflows/
│   └── recommendation/
├── run/                        # Run engine
│   └── adapters/               # Native test engine adapters
├── memory/                     # Memory engine
├── coverage/                   # Coverage engine
├── regression/                 # Regression engine
├── localization/               # Localization engine
│   └── sbfl/                   # SBFL algorithms
├── replay/                     # Replay engine
├── models/                     # Shared domain entity definitions
├── utils/                      # Shared low-level utilities
└── mcp/                        # MCP transport (post-MVP)

tests/
├── unit/                       # Mirrors src/ tree; one test module per source module
├── integration/                # Cross-component / subprocess-boundary tests
├── fixtures/projects/          # Controlled SuT projects (deterministic, isolated, no novetest imports)
└── manual-test-workspace/      # Human-facing demo scratch space; contents ephemeral (see its README)
```

## Development

- **Test gate** (both must be green before any commit touching `src/` or `tests/`):
  `env -u PYTHONPATH uv run pytest -q tests/unit tests/integration` and
  `env -u PYTHONPATH uv run mypy`.
- **User documentation** lives in [`docs/`](./docs/) — parallel human and AI-agent sets.
- **Native-engine toolchain setup** for the full integration matrix:
  [`scripts/dev-host-setup.md`](./scripts/dev-host-setup.md).
- **Contributing**: see [`CONTRIBUTING.md`](./CONTRIBUTING.md) (Apache-2.0 + CLA).
