# Domain Model

## Context Reference

- design/requirements-analysis/context-model.md

## Use Case Reference

- design/requirements-analysis/use-case-model.md

---

## Domain Description

Nove Test starts from a **Test Target** and asks a **Native Engine** to produce a **Native Result** from the external project and test ecosystem. The native result is an engine-specific umbrella for execution outcomes, logs, reports, coverage files, and other native evidence. The system normalizes the native result into a **Run Record** identified by a stable **Run Reference**, with associated **Test Result** evidence. A stored **Memory Entry** becomes part of **Run History**, which supports inspection, latest-run workflows, comparison, replay, and status review. When available, **Coverage Fact** data identifies exercised or uncovered **Code Location** values. **Regression Fact** records test result, output, or coverage changes derived from comparing run evidence. **Localization Finding** ranks suspicious code locations for a run. A **Replay Attempt** may execute again through the native engine path, producing a new native result that becomes a replay run record; the **Replay Result** is the reproducibility classification derived by comparing original and replay run records. Top-level Nove Test turns available facts into a **Recommendation** and connects each recommendation to supporting evidence through an **Evidence Citation**. **Status** summarizes current Nove Test evidence availability and workflow readiness.

---

## Entities

| Entity Name | Description | Attributes | Source |
|-------------|------------|-----------|--------|
| Test Target | Selected project, file, suite, package, or other scope requested for test execution or analysis. | targetExpression, targetType, workspaceContext | use-case |
| Native Engine | External test engine or tightly-coupled engine ecosystem used to execute tests and expose native-derived results. | engineName, engineVersion, ecosystem | context |
| Native Result | Engine-specific raw result bundle produced by a native engine, before Nove Test normalization. It may include execution status, test summaries, failed test references, stdout or stderr logs, stack traces, reports, coverage files, and other native artifacts. | resultId, sourceEngine, status, resultHandle, producedAt | product-plan |
| Run Reference | Stable identifier used to retrieve, compare, replay, and cite a run. | runId, createdAt | product-plan |
| Run Record | Normalized representation of one execution attempt. | runId, targetExpression, nativeEngine, status, summaryCounts, startedAt, completedAt, metadata | product-plan |
| Test Result | Individual or summarized test outcome associated with a run. | testId, outcome, duration, failureReference | product-plan |
| Memory Entry | Stored evidence package for a run, including normalized and native-derived evidence. | entryId, runId, storedAt, availabilityState | product-plan |
| Run History | Ordered collection of stored run evidence used for latest, status, comparison, and retention workflows. | historyId, orderingRule, latestRunId | inferred |
| Coverage Fact | Structured coverage information for a run, such as test-to-code mapping, line coverage, branch coverage, or uncovered code evidence. | factId, runId, coverageType, measuredValue, coverageState | product-plan |
| Regression Fact | Behavioral difference between run records, such as pass-to-fail transition, fail-to-pass transition, output difference, or coverage change. | factId, baseRunId, comparedRunId, transitionType | product-plan |
| Code Location | Source location referenced by coverage, regression, localization, or recommendation evidence. | filePath, line, branch, symbol | inferred |
| Localization Finding | Ranked suspicious code location with supporting evidence for a run. | findingId, runId, rank, score, evidenceSummary | product-plan |
| Replay Attempt | Request and execution context for re-running a stored run through the Run path. | replayId, originalRunId, replayRunId, attemptedAt | use-case |
| Replay Result | Reproducibility classification derived by comparing an original run record and a replay run record or replay failure state. It is not a native engine result. | resultId, classification, consistencySummary | product-plan |
| Recommendation | Top-level Nove Test guidance for the next testing, debugging, or coding step. | recommendationId, category, message, confidence | product-plan |
| Evidence Citation | Traceable link from a recommendation or finding to supporting run evidence or facts. | citationId, sourceType, sourceId, runId | product-plan |
| Status | Current summary of Nove Test evidence availability and workflow readiness. | statusId, latestRunId, availableFacts, readinessState | use-case |

---

## Relationships

| Source | Relationship | Target | Cardinality |
|--------|--------------|--------|-------------|
| Run Record | executes | Test Target | 1 to 1 |
| Run Record | records | Native Engine | 1 to 1 |
| Native Engine | produces | Native Result | 1 to 0..* |
| Run Record | is normalized from | Native Result | 1 to 1 |
| Run Record | has | Run Reference | 1 to 1 |
| Run Record | contains | Test Result | 1 to 0..* |
| Memory Entry | preserves | Native Result | 1 to 1 |
| Memory Entry | stores | Run Record | 1 to 1 |
| Run History | contains | Memory Entry | 1 to 0..* |
| Run History | identifies latest | Run Reference | 1 to 0..1 |
| Coverage Fact | describes | Run Record | 0..* to 1 |
| Coverage Fact | references | Code Location | 0..* to 0..* |
| Regression Fact | compares | Run Record | 1 to 2 |
| Regression Fact | may consider | Coverage Fact | 0..* to 0..* |
| Localization Finding | analyzes | Run Record | 1 to 1 |
| Localization Finding | ranks | Code Location | 1 to 1 |
| Localization Finding | cites | Evidence Citation | 1 to 1..* |
| Replay Attempt | replays | Run Record | 1 to 1 |
| Replay Attempt | may create | Run Record | 1 to 0..1 |
| Replay Attempt | produces | Replay Result | 1 to 1 |
| Replay Result | compares original | Run Record | 1 to 1 |
| Replay Result | may compare replayed | Run Record | 1 to 0..1 |
| Recommendation | cites | Evidence Citation | 1 to 1..* |
| Recommendation | may reference | Coverage Fact | 0..* to 0..* |
| Recommendation | may reference | Regression Fact | 0..* to 0..* |
| Recommendation | may reference | Localization Finding | 0..* to 0..* |
| Recommendation | may reference | Replay Result | 0..* to 0..* |
| Evidence Citation | points to | Run Reference | 1 to 1 |
| Status | summarizes | Run History | 1 to 1 |

---

## Glossary

| Term | Definition |
|------|-----------|
| Native-derived | Produced by, exposed by, or traceable to the native test engine ecosystem. |
| Native result | Engine-specific raw result bundle that can include structured outcomes, logs, reports, coverage files, and other native artifacts before Nove Test normalization. |
| Fact | A factual observation or primitive signal produced by Nove Test sub-products without prescribing a fix. |
| Run reference | Stable identifier used to retrieve, compare, replay, and cite run evidence. |
| Latest run | The most recent relevant run selected from run history for status, regression, or localization workflows. |
| Coverage gap | An uncovered code location, branch, or condition represented as a kind of Coverage Fact rather than as a separate domain entity. |
| Coverage change | A derived comparison result from two or more coverage facts, represented in coverage comparison outputs or Regression Fact rather than as a separate domain entity. |
| Regression | A behavioral change between run records, such as a test result transition, output difference, or coverage change. |
| Localization | Suspicious-location analysis based on failed test context and available coverage or regression evidence. |
| Replay | Re-execution of stored run context through the Run path to validate reproducibility. |
| Recommendation | Top-level guidance synthesized from cited facts. |

---

## Model Notes

| Note | Description |
| --- | --- |
| Actor exclusion | AI Agent, Developer, Native Test Engine Ecosystem, and Project Under Test remain context actors rather than domain entities. Domain entities model the evidence and facts Nove Test manages. |
| Native engine representation | Native Engine is included as a domain entity because run records must preserve which external engine produced the facts, even though the engine itself remains outside the system boundary. |
| Native result abstraction | Native Result intentionally aggregates engine-specific outcomes, logs, reports, coverage files, and artifacts. The internal structure can differ by native engine; Run Record is the normalized Nove Test representation derived from it. |
| Latest workflows | Run History is included to support `status`, `regression latest`, and `localization latest` behavior without modeling those commands as entities. |
| Fact boundary | Coverage Fact, Regression Fact, Localization Finding, Replay Result, and Recommendation are separated to preserve the product rule that sub-products produce facts while top-level Nove Test recommends. |
| Coverage comparison abstraction | Coverage gaps are represented through Coverage Fact state instead of a separate entity; cross-run coverage changes are derived by comparing Coverage Facts rather than modeled as a separate entity. |
| Replay result boundary | A replay execution can produce a new Native Result that normalizes into a replay Run Record. Replay Result is the comparison/classification over original and replay evidence, not the native result itself. |
| Source locations | Code Location is inferred because coverage gaps, localization findings, and evidence citations need a shared vocabulary for file, line, branch, or symbol references. |

---

## Assumptions

| Assumption | Rationale |
| --- | --- |
| Run Reference is stable within the active Nove Test evidence scope. | The design requires repeatable references but does not define global uniqueness. |
| A Run Record may exist for a failed, interrupted, or incomplete execution attempt. | The product needs evidence for failed and non-passing test workflows. |
| Coverage Fact, Regression Fact, Localization Finding, and Replay Result may be absent for some runs. | These facts depend on stored history, failures, replay attempts, or native ecosystem support. |
| Native Result may store embedded content, bounded excerpts, or durable handles depending on the native engine and artifact size. | Native engine output can include logs, reports, coverage files, and other artifacts with engine-specific structure. |
| A Replay Attempt may fail without creating a replay Run Record. | Replay can be unable to replay under reconstructed conditions. |

---

## Open Questions

| Question | Impact |
| --- | --- |
| Should Run Reference uniqueness be scoped to a project workspace, a user machine, or all Nove Test usage? | Affects identity relationships and evidence citation semantics. |
| Should Code Location initially support branch and symbol references, or only file and line references? | Affects Coverage Fact, Localization Finding, and Recommendation precision. |
| Should Memory Entry deletion leave a tombstone record for auditability, or remove the stored evidence completely? | Affects Run History and Evidence Citation behavior after deletion. |
