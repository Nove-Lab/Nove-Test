# Nove Test Regression

**Context:** [Product architecture](../overall-architecture.md) - Active sub-product.

## Purpose

**Regression** compares normalized native-engine results across runs to identify behavioral changes and anomalies. It explains what changed between run references without deciding the final response.

## Role

- Compares current and previous run records.
- Detects pass-to-fail and fail-to-pass transitions.
- Highlights native output and result differences.
- Includes coverage changes when Coverage facts are available.

## CLI

```bash
novetest regression compare <run_id1> <run_id2>
novetest regression latest
```

## Output

Regression output is facts only:

- Test outcome transitions.
- New failures.
- Fixed failures.
- Output differences.
- Coverage changes.

## Boundaries

- Regression does not prescribe fixes.
- Regression does not decide root cause.
- Regression does not replace the native engine's test result semantics.
- Top-level Nove Test uses Regression facts to explain risk and generate recommendations.
