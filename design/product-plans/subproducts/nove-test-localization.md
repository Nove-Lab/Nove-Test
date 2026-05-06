# Nove Test Localization

**Context:** [Product architecture](../overall-architecture.md) - Active sub-product.

## Purpose

**Localization** analyzes failed tests, native failure output, and coverage data to estimate suspicious code locations likely responsible for faults.

## Role

- Consumes failed-test context from Run and Memory, including native engine failure details.
- Uses Coverage facts to connect failing behavior to executed code.
- Uses Regression facts when available to focus on changed behavior.
- Produces ranked suspicious locations for top-level Nove Test to cite.

## CLI

```bash
novetest localization <run_id>
novetest localization latest
```

## Output

Localization output is facts only:

- Ranked suspicious code locations.
- Suspicion scores or equivalent ranking evidence.
- Related failed tests.
- Supporting coverage or regression references.

## Boundaries

- Localization does not guarantee root cause.
- Localization does not produce final repair instructions.
- Localization does not redefine native assertion or failure semantics.
- Top-level Nove Test decides how localization evidence becomes a recommendation.
