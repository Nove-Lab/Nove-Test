# Nove Test Memory

**Context:** [Product architecture](../overall-architecture.md) - Active sub-product.

## Purpose

**Memory** stores raw execution results and provides historical reference across runs. It turns one-off native-engine execution into reusable evidence that Nove Test can inspect, compare, replay, and cite.

## Role

- Stores Run outputs by run reference, including the native engine context.
- Provides list, show, and delete operations for stored runs.
- Preserves enough history for Coverage, Regression, Localization, Replay, and top-level recommendation synthesis.
- Acts as the shared source of stored testing evidence.

## CLI

```bash
novetest memory list
novetest memory show <run_id>
novetest memory delete <run_id>
```

## Output

Memory output is factual and should include:

- Stored run references.
- Raw execution summaries.
- Historical ordering.
- Availability of related artifacts or derived facts.

## Boundaries

- Memory does not reinterpret failures as product recommendations.
- Memory does not own coverage, regression, localization, or replay analysis.
- Memory should preserve original native-derived facts so later products can compare against them.
