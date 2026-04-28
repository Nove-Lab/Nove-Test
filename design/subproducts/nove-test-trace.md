# Nove Test Trace

**Context:** [Product family architecture](../architecture.md) · **Sub-product 4.**

## Purpose

**Coverage and execution insight** attached to the **same `run_id`** as Run: coverage snapshots, failure-time snapshots, and (when Memory provides baselines) **deltas**—always preferring **handles** over inlined large blobs in agent-facing output.

## Role

- Subscribes to a **Run** session (same instrumentation pass where possible).
- Supplies feedback signals to **Explorer** and enrichment to **Memory** / **Replay** context.

## Expectations

- **Agent-first:** summaries and handles suitable for tiered payloads; optional “fetch by handle” for heavy artifacts.
- **Within-stack** coverage semantics; cross-language **semantic** unification of coverage is explicitly not a short-term promise—only handles, totals, and deltas at a portable layer.
- Depends on **Run**; uses **Memory** when baseline-relative deltas are requested.
