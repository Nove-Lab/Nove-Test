# Nove Test - Product Delivery Plan

**Audience:** Product leads, engineering leads, and AI-agent workflow designers.  
**Purpose:** Define the planning-level build sequence for the new Nove Test direction. This is not a detailed technical implementation guide.

Related planning:

- [`overall-plan.md`](./overall-plan.md)
- [`overall-architecture.md`](./overall-architecture.md)

## Delivery Principle

Build from execution facts toward recommendations:

```text
Execute -> Store -> Structure -> Compare -> Locate -> Validate -> Recommend
```

Each phase should deliver a usable product capability while preserving the boundary that sub-products produce facts and top-level Nove Test produces recommendations.

Across all phases, Nove Test should build on the dominant test engines in each ecosystem, such as pytest and JUnit. Run normalizes their execution results; dependent sub-products analyze those normalized native-engine facts instead of reimplementing test discovery, assertion semantics, or runner behavior.

## Phase 1 - Run + Memory Foundation

Goal: create the minimum repeatable testing loop.

Product capabilities:

- Execute a target test run through **Run**, which delegates to the dominant native test engine for that stack.
- Return a standardized execution result with a stable run reference.
- Store the raw result through **Memory**.
- Inspect stored runs by reference.
- Provide enough structure for an AI agent to decide whether testing passed, failed, or could not complete.

Expected planning outputs:

- Run result contract at product level, including the native engine used.
- Memory history and lookup behavior.
- Basic top-level `novetest test`, `novetest inspect`, and `novetest status` behavior.

## Phase 2 - Coverage Structuring

Goal: turn execution into structured test-to-code evidence.

Product capabilities:

- Show coverage facts for a stored run.
- Identify test-to-code relationships where the native engine ecosystem exposes them.
- Compare coverage between two runs.
- Expose coverage gaps as facts, not recommendations.

Expected planning outputs:

- Coverage fact categories.
- Coverage display and diff behavior.
- Relationship between Coverage facts and top-level recommendations.

## Phase 3 - Regression Comparison

Goal: make run-to-run behavior changes visible.

Product capabilities:

- Compare two run references.
- Identify pass-to-fail and fail-to-pass transitions.
- Surface output differences, native result changes, and coverage changes.
- Provide a latest-run comparison path for agents.

Expected planning outputs:

- Regression fact categories.
- Comparison result shape.
- Rules for distinguishing raw differences from top-level recommendations.

## Phase 4 - Localization

Goal: help the AI agent and developer focus investigation on likely fault locations.

Product capabilities:

- Analyze failed tests with native failure output, coverage, and regression context.
- Produce ranked suspicious code locations.
- Attach suspicion scores or equivalent ranking evidence.
- Keep the output factual and avoid prescribing final fixes inside the sub-product.

Expected planning outputs:

- Localization input requirements.
- Suspicious-location output shape.
- How localization evidence is cited by top-level recommendations.

## Phase 5 - Replay Validation

Goal: validate whether an observed run or failure can be reproduced.

Product capabilities:

- Re-execute a stored run through **Run** and the same native engine path where practical.
- Compare replay outcome with the original run.
- Report consistency, inconsistency, or inability to replay.
- Feed reproducibility facts back into Memory and top-level recommendations.

Expected planning outputs:

- Replay request behavior.
- Replay result categories.
- Relationship between Replay facts and recommendation confidence.

## Phase 6 - Recommendation Synthesis

Goal: make top-level Nove Test useful as an AI-agent testing loop.

Product capabilities:

- Aggregate facts from Run, Memory, Coverage, Regression, Localization, and Replay.
- Produce concise recommendations for what to test, inspect, or fix next.
- Preserve links back to supporting facts.
- Provide both human-readable and structured output.

Expected planning outputs:

- Recommendation categories.
- Evidence citation behavior.
- Top-level command behavior for `novetest test`, `novetest compare`, and `novetest replay`.

## Cross-Phase Rules

- Keep sub-products deterministic and fact-only.
- Keep recommendations centralized in top-level Nove Test.
- Build on dominant native test engines; do not replace test discovery, execution, assertion handling, or native reporting.
- Prefer structured outputs for AI-agent use.
- Avoid implementation choices in this planning document unless they are needed to define product behavior.
- Treat detailed runner support, storage technology, schemas, and infrastructure as later technical design work.
