# Nove Test Coverage

**Context:** [Product architecture](../overall-architecture.md) - Active sub-product.

## Purpose

**Coverage** normalizes coverage-related data produced by the native test engine ecosystem and structures relationships between tests and code execution. It helps Nove Test understand what was exercised and what changed between runs.

## Role

- Reads stored Run and Memory context.
- Produces test-to-code mappings where the underlying engine ecosystem exposes them.
- Reports line and branch coverage facts from native or ecosystem-standard coverage outputs.
- Computes coverage deltas between two run references.

## CLI

```bash
novetest coverage show <run_id>
novetest coverage diff <run_id1> <run_id2>
```

## Output

Coverage output is facts only:

- Test-to-code mapping.
- Line coverage.
- Branch coverage.
- Coverage gaps.
- Coverage deltas.

## Boundaries

- Coverage does not decide whether a gap is acceptable.
- Coverage does not rank fault locations by itself.
- Coverage does not replace ecosystem-standard coverage tooling.
- Top-level Nove Test uses Coverage facts when producing recommendations.
