# Nove Test Replay

**Context:** [Product family architecture](../architecture.md) · **Sub-product 5.**

## Purpose

**Reproducible failure artifacts:** from a classified failure (Oracle + Run context), build **replay recipes** and verify them by invoking **Run** again under the same contract; report **reproducibility status** (e.g. stable / flaky / non-reproducible). Input minimization is an **evolution** inside this product once replay is trustworthy.

## Role

- Bridges **Oracle** verdicts and **Run** re-execution.
- Produces handles consumable by **Memory** for promotion into replay suites.

## Expectations

- **Agent-first:** replay handles, recipe metadata, and verification outcomes as structured JSON.
- **Replay-first sequencing:** shipping reliable replay before aggressive reduction.
- Depends on **Run** and **Oracle**; **Trace** improves context quality when present.
