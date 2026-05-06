# Nove Test - Overall Plan

## Summary

**Nove Test** is an AI-first testing orchestration product. It helps an AI agent run tests, preserve evidence, understand what changed, locate likely fault areas, validate reproducibility, and return actionable recommendations for the next coding step.

The top-level product is not a single test runner. It coordinates multiple fact-producing engines and turns their outputs into one recommendation layer.

Nove Test does **not** reinvent core test execution. **Run** wraps the dominant native test engines teams already trust, such as **pytest** and **JUnit**, while the dependent sub-products structure, compare, localize, and replay facts derived from those engines.

Core lifecycle:

```text
Execute -> Store -> Structure -> Compare -> Locate -> Validate -> Recommend
```

## Product Shape

| Layer | Role |
| --- | --- |
| **Nove Test** | Top-level orchestration and recommendation layer. |
| **Run** | Wraps dominant native test engines and emits standardized execution results. |
| **Memory** | Stores raw execution results and native-derived facts for historical reference. |
| **Coverage** | Structures test-to-code relationships and coverage facts from native-engine outputs. |
| **Regression** | Compares normalized run facts to detect behavioral changes and anomalies. |
| **Localization** | Estimates suspicious code locations from native failure, coverage, and regression signals. |
| **Replay** | Re-executes a prior run through Run to validate reproducibility. |

Sub-products produce **facts and primitive signals**. Top-level Nove Test owns **decisions and recommendations**.

## Primary User

The primary user is the **AI agent** that writes or changes code and needs a reliable testing loop before continuing. Developers remain important users, but mostly as supervisors, reviewers, and consumers of the same structured recommendations.

Every active product surface should therefore support:

- CLI use by agents.
- Structured output that can be consumed by agents.
- Human-readable summaries for developers.
- Repeatable references to prior runs.

## Product Principles

1. **AI-first workflow** - The system should be easy for an AI agent to invoke, inspect, compare, and act on without relying on informal text-only interpretation.
2. **Facts before recommendations** - Sub-products stay deterministic and fact-oriented; recommendations are synthesized only at the top level.
3. **Repeatable proof** - A run should become something that can be stored, compared, replayed, and cited later.
4. **Use the ecosystem's test engines** - Run relies on dominant engines such as pytest and JUnit for discovery, execution, assertions, and native reports; Nove Test adds orchestration and intelligence around them.
5. **Separation of concerns** - Run executes, Memory stores, Coverage structures, Regression compares, Localization ranks, Replay validates, and Nove Test recommends.
6. **Implementation neutrality at planning level** - These documents define product intent and responsibilities, not final database, framework, or infrastructure choices.

## Core User Flow

The main integrated path is:

```text
novetest test [target]
   |
   v
Run
   |
   v
Memory
   |
   v
Coverage
   |
   v
Regression
   |
   v
Localization
   |
   v
Replay (optional)
   |
   v
Recommendation
```

The top-level CLI examples are:

```bash
novetest test [target]
novetest inspect <run_id>
novetest compare <run_id1> <run_id2>
novetest status
novetest replay <run_id>
```

## Recommendation Output

Nove Test combines facts from the sub-products into a concise recommendation payload for agents and developers.

Example:

```text
120 tests passed
2 failed

Coverage gaps:
  - user_service.py:42 (branch not covered)

Regression detected:
  - test_login behavior changed

Suspected fault:
  - auth.py:88

Recommendations:
  - Add test for condition: user.active == False
  - Add boundary test for price < 0
  - Investigate auth.py:88
```

## Roadmap

1. **Run + Memory foundation** - Standardized execution results, durable run history, and basic inspection.
2. **Coverage structuring** - Test-to-code mapping, line and branch facts, and coverage deltas.
3. **Regression comparison** - Run-to-run comparison of test outcomes, outputs, and coverage changes.
4. **Localization** - Ranked suspicious code locations from failure and coverage signals.
5. **Replay validation** - Re-execution of stored runs to classify reproducibility.
6. **Recommendation synthesis** - Top-level aggregation into actionable guidance for the AI agent.

## Doc Map

| Area | Document |
| --- | --- |
| Product narrative | `design/product-plans/overall-plan.md` |
| Product architecture | `design/product-plans/overall-architecture.md` |
| Run | `design/product-plans/subproducts/nove-test-run.md` |
| Memory | `design/product-plans/subproducts/nove-test-memory.md` |
| Coverage | `design/product-plans/subproducts/nove-test-coverage.md` |
| Regression | `design/product-plans/subproducts/nove-test-regression.md` |
| Localization | `design/product-plans/subproducts/nove-test-localization.md` |
| Replay | `design/product-plans/subproducts/nove-test-replay.md` |
| Archived implementation planning notes | `design/archive/implementation-plan.md` |

## Planning Defaults

- `design/product-plans/` is the active home for product planning documents.
- Planning document filenames should use lowercase kebab-case, such as `overall-plan.md`, not underscores.
- The active sub-product set is Run, Memory, Coverage, Regression, Localization, and Replay.
- Top-level Nove Test is the only layer that generates recommendations.
- Detailed implementation technology choices should be made in later technical design documents, not in this product planning layer.
- The product should leverage each ecosystem's dominant test engine instead of replacing native test discovery, execution, assertion, or reporting behavior.
