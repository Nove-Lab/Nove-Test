# Nove Test - Product Architecture

This document describes the planning-level architecture for **Nove Test**. It explains the active components, their boundaries, and how information flows from execution to recommendation.

Related planning: [`overall-plan.md`](./overall-plan.md).

## 1. Architectural Stance

Nove Test is a top-level orchestration and recommendation layer over deterministic sub-products.

- **Sub-products produce facts only.**
- **Top-level Nove Test produces decisions and recommendations.**
- **Run wraps dominant native test engines such as pytest and JUnit instead of replacing them.**
- **Dependent sub-products consume normalized facts derived from those native engines.**
- **Every meaningful result is tied to a run reference.**
- **Outputs should be structured enough for AI agents to consume.**

The core lifecycle is:

```text
Execute -> Store -> Structure -> Compare -> Locate -> Validate -> Recommend
```

## 2. Actors

| Actor | Role |
| --- | --- |
| **AI agent** | Primary user; invokes Nove Test while coding and consumes recommendations for the next action. |
| **Developer** | Reviews results, supervises agent behavior, and uses recommendations for debugging and test improvement. |
| **Nove Test** | Coordinates the active sub-products and synthesizes their signals into recommendations. |

## 3. Active Components

| Component | Responsibility | Spec |
| --- | --- | --- |
| **Nove Test** | Integrated workflow and recommendation synthesis. | This document and `overall-plan.md` |
| **Run** | Wrap dominant native test engines and produce standardized execution results. | [`subproducts/nove-test-run.md`](./subproducts/nove-test-run.md) |
| **Memory** | Store raw execution results and native-derived historical references. | [`subproducts/nove-test-memory.md`](./subproducts/nove-test-memory.md) |
| **Coverage** | Structure test-to-code mappings and coverage deltas from native-engine outputs. | [`subproducts/nove-test-coverage.md`](./subproducts/nove-test-coverage.md) |
| **Regression** | Compare normalized run facts and identify behavioral changes. | [`subproducts/nove-test-regression.md`](./subproducts/nove-test-regression.md) |
| **Localization** | Rank suspicious code locations using failure, coverage, and regression facts. | [`subproducts/nove-test-localization.md`](./subproducts/nove-test-localization.md) |
| **Replay** | Re-execute stored runs through Run to validate reproducibility. | [`subproducts/nove-test-replay.md`](./subproducts/nove-test-replay.md) |

## 4. Dependency Flow

```text
Nove Test
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

Logical dependencies:

- **Run** is the execution entrypoint for governed test execution and delegates actual test semantics to dominant native engines.
- **Memory** depends on Run outputs so future work can inspect and compare prior native-derived results.
- **Coverage** depends on a stored run and structures execution relationships exposed by the native engine ecosystem.
- **Regression** depends on comparable normalized run records and may use Coverage facts.
- **Localization** depends on failed tests plus Coverage and Regression signals; it does not replace native assertion or failure semantics.
- **Replay** depends on Memory and Run to reconstruct and validate a prior run through the same native engine path.
- **Recommendation** depends on all available facts but is owned by top-level Nove Test.

## 5. Data Boundary

The planning-level data model is intentionally simple:

- **Run record** - identity, target, native engine, status, test outcomes, captured output, and execution metadata.
- **Memory entry** - stored run record, native-derived artifacts, and historical reference.
- **Coverage facts** - test-to-code mapping, line or branch coverage, and deltas derived from the engine ecosystem.
- **Regression facts** - pass/fail transitions, output differences, and coverage changes.
- **Localization facts** - ranked suspicious locations and scores.
- **Replay facts** - re-execution result and consistency against the original run.
- **Recommendation** - top-level guidance assembled from the facts above.

Large implementation details such as storage engines, schemas, transport protocols, and runner-specific adapters belong in later technical design. The product-level rule is stable: Nove Test wraps native engines; it does not replace them.

## 6. CLI Surface

Top-level commands:

```bash
novetest test [target]
novetest inspect <run_id>
novetest compare <run_id1> <run_id2>
novetest status
novetest replay <run_id>
```

Sub-product commands:

```bash
novetest run [target]
novetest memory list
novetest memory show <run_id>
novetest memory delete <run_id>
novetest coverage show <run_id>
novetest coverage diff <run_id1> <run_id2>
novetest regression compare <run_id1> <run_id2>
novetest regression latest
novetest localization <run_id>
novetest localization latest
novetest replay <run_id>
```

The CLI should be friendly to both humans and AI agents, with structured output as a first-class expectation.

## 7. Design Rules

1. Sub-products must not emit final recommendations.
2. Top-level Nove Test must cite the facts that support a recommendation.
3. Sub-product output should be deterministic for the same inputs where practical.
4. Cross-run comparison should use stored run references, not informal terminal text.
5. Native test engine behavior remains the source of truth for discovery, execution, assertion handling, and native reports.
6. Planning documents should avoid premature implementation choices unless they are required to explain product behavior.
