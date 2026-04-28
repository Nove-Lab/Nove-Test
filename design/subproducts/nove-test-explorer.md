# Nove Test Explorer

**Context:** [Product family architecture](../architecture.md) · **Sub-product 6.**

## Purpose

**Coverage-guided exploration:** expands seed tests or inputs into deeper candidates using **budgets** and **lineage**, scheduling **child sessions only through Run** (directly or via **Nove Test Orchestrator**), using **Trace** and **Oracle** feedback to prioritize interesting cases and grow a corpus over time.

## Role

- Feeds expanded corpora and handles back into **Memory** for continuity on later invocations.
- Never bypasses **Run** for governed execution.

## Expectations

- **Agent-first:** exploration jobs, partial results, stop reasons, and budget telemetry in structured form.
- Depends on **Run**, **Oracle**, and **Trace**; **Memory** strengthens seeds and promotion loops when available.
- MVP scope should stay **narrow enough** to ship; depth grows after the Run→Memory→Oracle→Trace spine is stable.
