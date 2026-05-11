# Use-Case Model

## Context Reference

- design/requirements-analysis/context-model.md

---

## Assumptions

| Assumption | Rationale |
| --- | --- |
| Install onboarding is part of the externally visible product behavior even though binary-delivery infrastructure remains outside the Nove Test system boundary. | The UX goal makes one-line install and immediate CLI verification part of the expected user-facing experience. |
| `novetest init` is a user-goal-level use case because it leaves the project in a new usable state by creating and governing the per-project `.novetest/` store. | The UX goal defines project initialization as the single obvious first-use command. |
| Project initialization may inspect existing project and native-engine readiness, but it does not install or configure native test engines on the user's behalf. | The UX goal explicitly prohibits Nove Test from bundling or managing native engines. |
| Direct sub-product CLI commands are modeled as externally visible use cases because the architecture lists them as supported command surfaces. | The product architecture documents both top-level and sub-product commands. |
| The integrated `novetest test [target]` workflow uses optional analysis stages only when the required stored evidence or native-derived facts are available. | Coverage, Regression, Localization, and Replay depend on facts that may not exist for every run. |
| `Native Test Engine Ecosystem` and `Project Under Test` participate as supporting actors in execution-related use cases, but they do not receive recommendation decisions. | The context model places them outside the system boundary as supporting external actors. |
| Stored run deletion can be triggered by both AI Agent and Developer actors. | User feedback confirmed that run memory deletion is available to both automated and human users in the current scope. |
| Latest regression review and localization review remain separate use cases. | User feedback confirmed that regression focuses on latest test result and coverage changes from the prior run, while localization is based on a test run result. |

---

## Use Cases

| Use Case Name | Description | Used By | Includes | Extends |
| --- | --- | --- | --- | --- |
| Install Nove Test CLI | Install the `novetest` CLI through the supported onboarding path so the command surface becomes available on the user's machine without requiring a language-specific toolchain for Nove Test itself. | AI Agent, Developer | Provide Installable Binary | None |
| Provide Installable Binary | Provide the installable Nove Test binary and related delivery material needed by the supported onboarding path. | Binary Distribution Channel | None | Install Nove Test CLI |
| Verify CLI Availability | Confirm that the installed `novetest` CLI responds immediately to version or top-level help commands after installation. | AI Agent, Developer | None | Install Nove Test CLI |
| Initialize Project Workspace | Initialize Nove Test in a project root so a managed `.novetest/` store exists and the project is ready for later Nove Test commands without manual configuration of Nove Test itself. | AI Agent, Developer | None | None |
| Execute Test Workflow | Run the top-level `novetest test [target]` workflow to execute tests, preserve evidence, analyze available facts, and receive a recommendation-oriented result. | AI Agent, Developer | Run Test Target, Store Run Evidence, Inspect Run Evidence, Generate Recommendations | None |
| Run Test Target | Execute a requested target through the wrapped native test engine path and receive standardized execution facts with a stable run reference. | AI Agent, Developer | Provide Native Execution Facts, Supply Test Target Material | Execute Test Workflow |
| Provide Native Execution Facts | Provide external native execution, assertion, output, reporting, and tightly-coupled coverage inputs for Nove Test to normalize. | Native Test Engine Ecosystem | None | Run Test Target |
| Supply Test Target Material | Provide the source code, tests, configuration, and selected target that Nove Test executes or analyzes. | Project Under Test | None | Run Test Target |
| Store Run Evidence | Preserve normalized run results, native-derived artifacts, metadata, and historical references for later workflows. | AI Agent, Developer | None | Execute Test Workflow |
| Inspect Run Evidence | Retrieve a stored run by reference and inspect factual execution results, metadata, output, and available derived facts. | AI Agent, Developer | None | Execute Test Workflow |
| Manage Stored Runs | List stored runs, show a stored run, or delete a stored run through explicit memory commands. | AI Agent, Developer | Inspect Run Evidence | None |
| Show Coverage Facts | View coverage facts for a stored run, including test-to-code mappings, line or branch facts, and gaps where available. | AI Agent, Developer | Inspect Run Evidence | Execute Test Workflow |
| Compare Coverage Facts | Compare coverage facts between two stored run references and view coverage deltas. | AI Agent, Developer | Inspect Run Evidence, Show Coverage Facts | Compare Run Behavior |
| Compare Run Behavior | Compare two stored run references to understand test outcome transitions, output differences, and available coverage changes. | AI Agent, Developer | Inspect Run Evidence, Compare Coverage Facts | Execute Test Workflow |
| Review Latest Regression | Compare the latest relevant run evidence without manually selecting both run references when the stored history supports it. | AI Agent, Developer | Compare Run Behavior | None |
| Localize Faults | Analyze failed-test context with available coverage and regression facts to view ranked suspicious code locations. | AI Agent, Developer | Inspect Run Evidence | Execute Test Workflow |
| Review Latest Localization | View suspicious-location analysis for a latest relevant test run result when stored evidence supports it. | AI Agent, Developer | Localize Faults | None |
| Replay Prior Run | Re-execute a stored run through the Run path and compare the replay outcome with the original run to validate reproducibility. | AI Agent, Developer | Inspect Run Evidence, Run Test Target | Execute Test Workflow |
| Check Testing Status | View current Nove Test status, recent run evidence, and available workflow readiness through the CLI. | AI Agent, Developer | None | None |
| Generate Recommendations | Receive top-level Nove Test guidance for the next testing, debugging, or coding step, with supporting facts cited. | AI Agent, Developer | Inspect Run Evidence | Execute Test Workflow |

---

## Model Notes

| Note | Description |
| --- | --- |
| Actor consistency | All actors referenced in `Used By` come from `design/requirements-analysis/context-model.md`; no new actors were introduced. |
| Onboarding coverage | Install, verification, and project initialization are now modeled as explicit user goals because `design/product-plans/ux-goal.md` makes them part of the required user-facing surface. |
| Integrated workflow | `Execute Test Workflow` represents the main top-level product goal, while direct sub-product commands remain separate use cases because they are documented CLI surfaces. |
| Include relationships | Includes represent mandatory reusable behavior when the base use case executes; optional fact analysis is represented as extensions of the integrated workflow or comparison flows. |
| Supporting actors | `Provide Native Execution Facts` and `Supply Test Target Material` are modeled to show external-system participation without treating internal Nove Test sub-products as actors. |
| Recommendation boundary | Only `Generate Recommendations` produces top-level guidance; fact-producing use cases remain factual. |
| Latest analysis split | `Review Latest Regression` remains separate because it compares the latest test result and coverage changes against prior evidence, while `Review Latest Localization` remains separate because localization analyzes suspicious locations from a specific test run result. |
| Review status | The newly added onboarding use cases and related assumptions in this revision should be treated as draft updates until explicitly re-approved. |

---

## Open Questions

| Question | Impact |
| --- | --- |
| None for the current use-case modeling scope. | None. |
