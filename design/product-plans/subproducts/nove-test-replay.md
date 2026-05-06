# Nove Test Replay

**Context:** [Product architecture](../overall-architecture.md) - Active sub-product.

## Purpose

**Replay** re-executes a specific run through Run and the relevant native test engine under reconstructed conditions to validate reproducibility. It helps Nove Test distinguish stable failures from inconsistent or non-reproducible behavior.

## Role

- Reads stored run context from Memory.
- Requests re-execution through Run so replay uses the same native engine path as the original run where practical.
- Compares replay outcome against the original run.
- Reports reproducibility facts for top-level recommendation synthesis.

## CLI

```bash
novetest replay <run_id>
```

## Output

Replay output is facts only:

- Re-execution result.
- Consistency versus the original run.
- Replay status such as reproducible, inconsistent, or unable to replay.
- References to the original and replayed run records.

## Boundaries

- Replay does not classify the best fix.
- Replay does not replace Regression or Localization.
- Replay does not implement an independent test runner.
- Top-level Nove Test uses Replay facts to adjust recommendation confidence.
