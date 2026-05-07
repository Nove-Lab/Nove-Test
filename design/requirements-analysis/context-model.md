# Context Model

## System Summary

- Upstream artifacts: None for step 1.
- System purpose: Nove Test is an AI-first testing orchestration and recommendation system that runs native test engines, stores structured evidence, compares runs, localizes likely fault areas, optionally replays prior runs, and produces actionable recommendations for the next coding step.
- Inside the system boundary: the top-level Nove Test orchestration and recommendation layer, plus the internal Run, Memory, Coverage, Regression, Localization, and Replay capabilities and their CLI behaviors.
- Explicitly outside the system boundary: human and agent users, the project under test, native test-engine and coverage-reporting tooling, CI or other automated pipeline tooling for the current scope, future GUI interfaces, and any execution environment not defined as a Nove Test capability in the product plans.

---

## System Boundary

In scope:

- The `novetest` product surface described in `design/product-plans/overall-plan.md` and `design/product-plans/overall-architecture.md`.
- Top-level commands such as `novetest test`, `inspect`, `compare`, `status`, and `replay`.
- Internal orchestration across Run, Memory, Coverage, Regression, Localization, and Replay.
- Recommendation synthesis that cites supporting facts from internal sub-products.

Out of scope:

- Native test discovery, execution semantics, assertions, and native reports owned by tools such as `pytest` and `JUnit`.
- CI or other automated pipeline integrations, which are not covered as actors in the current scope.
- Future GUI or non-CLI interfaces, which may be modeled later but are intentionally excluded from this context model.
- The source codebase and test suite being evaluated by Nove Test.
- Separate human decision-making outside the system after recommendations are returned.
- Detailed implementation technology choices, storage engines, schemas, transports, and infrastructure not fixed by the planning documents.

---

## Actors

| Actor Name | Type | Description | Parent Actor |
| --- | --- | --- | --- |
| AI Agent | Primary | Invokes Nove Test while coding, requests runs and comparisons, and consumes structured recommendations to decide the next engineering action. | None |
| Developer | Primary | Runs inspection, comparison, and replay workflows directly or supervises the AI agent using the same factual outputs and recommendations. | None |
| Native Test Engine Ecosystem | Supporting | Provides the external test execution, assertion semantics, and tightly-coupled native-derived reporting or coverage data that Nove Test wraps rather than replaces. | None |
| Project Under Test | Supporting | Supplies the source code, tests, and execution target that Nove Test analyzes through wrapped native test runs. | None |

---

## External Systems

- Native test engines and related ecosystem tooling, such as `pytest`, `JUnit`, and compatible coverage/report producers, remain the source of truth for test execution behavior outside the Nove Test boundary.
- Coverage tooling is distinct from test engines at the ecosystem level, but it is tightly coupled to native test execution for the current scope and is therefore grouped under the Native Test Engine Ecosystem actor.
- The project workspace under test is external to Nove Test even when Nove Test runs within the same repository or machine context.

---

## Assumptions

- The CLI is the only explicit interaction surface in the current design set, so the context model treats `novetest` command usage as the primary system entrypoint.
- Run, Memory, Coverage, Regression, Localization, and Replay are modeled as internal capabilities, not actors, because the planning documents define them as sub-products inside Nove Test.
- Coverage and native reporting tools are grouped under the broader Native Test Engine Ecosystem actor because they are distinct but tightly coupled in the current scope.
- The project under test is an external system actor because Nove Test operates on it but does not own or define it.
- CI or automated pipeline tooling is intentionally excluded from the current actor scope.
- GUI and other non-CLI interfaces are expected later but are intentionally excluded from the current actor scope.

---

## Open Questions

- None for the current context modeling scope.
