# Nove Test Run

**Context:** [Product architecture](../overall-architecture.md) - Active sub-product.

## Purpose

**Run** executes tests by wrapping the dominant native test engines that teams already use, such as **pytest** and **JUnit**, and produces a standardized execution result that the rest of Nove Test can store, structure, compare, and replay.

Run is not a replacement test framework. It preserves the ecosystem runner as the source of truth for discovery, execution, assertions, and native reporting.

## Role

- Accepts a test target from top-level Nove Test or direct CLI use.
- Invokes the appropriate underlying native test engine.
- Emits a stable run reference and normalized execution summary.
- Captures primitive execution facts such as pass/fail counts, failed tests, status, and bounded output.
- Records which native engine produced the result so downstream facts stay traceable.

## CLI

```bash
novetest run [target]
```

`novetest test [target]` normally invokes Run internally as the first step in the integrated workflow.

## Output

Run output is factual and should include:

- Run identity.
- Target under test.
- Execution status.
- Test result summary.
- Failed test references where available.
- Captured output or output handles.
- Execution metadata needed by Memory and Replay.

## Boundaries

- Run does not produce recommendations.
- Run does not decide whether a coverage gap or regression matters.
- Run is the execution source for governed Nove Test workflows.
- Run does not reinvent native runner semantics.
