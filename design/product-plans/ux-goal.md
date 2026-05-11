# Nove Test - UX Goal

## Purpose

This document captures the **high-level user experience goal** for Nove Test, from first install through first use. It sets the bar that downstream documents (requirements, interface contracts, workflows, implementation plan) must respect at the user-facing surface.

It is intentionally narrow: it describes the **onboarding and entrypoint experience**. The full operating experience — command vocabulary, workflow shapes, recommendation outputs — is owned by the documents listed in [Downstream References](#downstream-references) below.

Related planning: [`overall-plan.md`](./overall-plan.md), [`overall-architecture.md`](./overall-architecture.md).

---

## 1. Primary Persona

The Nove Test user is a pair: an **AI coding agent** and **the human developer it works for**, operating together on the same project.

| Trait | Description |
| --- | --- |
| **Environment** | A common professional dev setup: Linux (typically Ubuntu) or macOS. Windows is not the primary persona target for the onboarding experience. |
| **Project shape** | A real software project under active development by the AI agent. The user is iterating on AI-generated code and needs to test it continuously. |
| **Testing literacy** | Capable of writing tests that run on a dominant native test engine for their ecosystem (e.g. `pytest`, `JUnit`, `jest`, `go test`, `cargo test`, `dotnet test`). The user does not need Nove Test to teach them how to write tests. |
| **Motivation for adopting Nove Test** | They want to run, record, and analyze tests **more efficiently** so that AI-generated code can be tested more rigorously. They expect structured, agent-consumable output as a baseline, not an upgrade. |
| **Tool relationship** | The AI agent is the primary direct caller of the CLI. The human supervises, reads recommendations, and acts on them. Both share the same factual outputs. |

This pair persona is the lens for every UX decision: if a step makes sense to a human but is awkward for an agent (or vice versa), it fails the goal.

---

## 2. Installation Experience

**Goal:** the user decides to try Nove Test and is up and running in **one CLI command**, with **no language toolchain prerequisite**.

### Acceptance shape

The user can install Nove Test with **a single line** (or, at worst, a very small number of lines) pasted into their shell. They do not need to first install Python, Node, a JVM, Cargo, or any other language-specific toolchain just to get Nove Test itself running.

Immediately after install completes, the user verifies it succeeded by running:

```bash
novetest -v    # prints the installed version
# or
novetest -h    # prints top-level help and the available commands
```

Both should respond instantly and confirm that the Nove Test binary and command surface are in place. There must be no second "now configure your environment" step between install and this verification.

This goal binds to the install strategy described in [`implementation-plan/foundations.md` §7 Distribution](../implementation-plan/foundations.md#7-distribution): a Tier-1 one-line installer that fetches a self-contained binary. If the install strategy ever changes, the constraints above are the bar it must continue to clear.

### What Nove Test does NOT install

**Nove Test does not bundle, install, or manage native test engines.** Installing Nove Test gives the user the `novetest` binary and its orchestration capabilities only. It does **not** install `pytest`, `JUnit`, `jest`, `go test`, `cargo test`, `dotnet test`, or any coverage tool.

This is a deliberate product principle, not a limitation:

- Nove Test **wraps** whatever native test engines the user already has installed for their project. It is additive infrastructure, not a replacement runtime. (See [`overall-plan.md`](./overall-plan.md) Product Principle 4.)
- If the user already runs their project's tests with `pytest`, Nove Test uses `pytest`. If they use `jest`, Nove Test uses `jest`. The user does not configure this — Nove Test detects what their project is already set up to use.
- If the user has **only** `pytest` installed, Nove Test exercises only `pytest`. It does not pretend other engines are available.
- If **no** supported native engine is detected for the project, Nove Test does not silently fail — it tells the user clearly that testing is not possible until they install (or are already using) one of the supported native engines, and points to which engines are supported. This message is the same whether the caller is the AI agent or the human; both can act on it.

This stance keeps install size small, keeps Nove Test out of the user's existing testing toolchain decisions, and avoids version conflicts with whatever the project already pins.

### Anti-goals

- Multi-step setup wizards.
- Requiring the user to install a language runtime they did not already have for their own project.
- A successful install where `novetest -v` or `novetest -h` does not immediately work.
- Different install paths for "the agent's install" vs. "the human's install." There is one install.
- Installing Nove Test as a way to obtain `pytest` / `JUnit` / `jest` / etc. Nove Test is not a meta-installer for test engines.

---

## 3. First Use - Project Initialization

**Goal:** the user adopts Nove Test in a specific project with a **single, obvious command**, after which Nove Test is "live" in that project with zero further setup.

### Acceptance shape

From the project's root directory, the user runs:

```bash
novetest init
```

This produces a `.novetest/` directory at the project root. The user understands, from the command's output and from the documentation, that:

- `.novetest/` is where Nove Test stores **all of its configuration and artifacts** for this project — run evidence, derived facts, recommendations, history.
- All future Nove Test commands in this project operate against `.novetest/` transparently.
- **The user is not expected to open, edit, or hand-inspect `.novetest/` directly.** It is an internal store. The Nove Test command surface (see [`overall-architecture.md` §6 CLI Surface](./overall-architecture.md#6-cli-surface)) provides every supported way to inspect, list, compare, and replay what is stored inside it.

After `init`, the user immediately has a working Nove Test environment for this project and can move on to the actual operating commands documented downstream.

### Why a per-project store

A per-project `.novetest/` directory — rather than a single global store — matches the persona's mental model:

- The AI agent's testing history is scoped to the project it is currently working on.
- Run references, recommendations, and replay artifacts travel with the project (and can be ignored or committed per the project's preference).
- Multiple projects on the same machine do not contaminate each other's history.

The exact relationship between this per-project store and any user-level cache or shared install state is an implementation concern for [`implementation-plan/foundations.md` §4 Persistence](../implementation-plan/foundations.md#4-persistence) to reconcile.

### Anti-goals

- Requiring the user to author or hand-edit a config file before `init` works.
- Requiring the user to understand `.novetest/`'s internal layout to use Nove Test.
- A two-step "init, then configure your engine" flow. Engine detection should happen automatically based on the project's existing test setup.

---

## 4. From Init to Daily Use

Once the user has completed install and `novetest init`, they enter the regular operating loop of Nove Test — running tests, inspecting evidence, comparing runs, reviewing localization, replaying, and acting on recommendations.

That loop is **not redefined here.** It is fully specified by the downstream design documents.

---

## 5. UX Principles (Binding)

These principles apply to every command surface, not just install and init:

1. **One command should do one obvious thing.** Composability lives in the agent driving the CLI, not in flag sprawl.
2. **Structured output is the baseline.** Every command must be consumable by the AI agent without scraping prose. Human-readable formatting is the alternate, not the default for non-TTY callers. (See [`foundations.md` §2 CLI Framework and Output Contract](../implementation-plan/foundations.md#2-cli-framework-and-output-contract).)
3. **No hidden state the user must manage.** All durable state lives in `.novetest/` and is managed through Nove Test commands.
4. **The agent and the human see the same facts.** Recommendations cite the underlying run evidence so both parties can audit them.
5. **Failure is legible.** Exit codes distinguish "the user's tests failed" from "Nove Test itself failed" from "the native engine is misconfigured." (See [`foundations.md` §2 Exit codes](../implementation-plan/foundations.md#2-cli-framework-and-output-contract).)

---

## Downstream References

The full operating experience is owned by the documents below. This UX goal sets the entry-point bar; those documents extend it consistently.

| Area | Document |
| --- | --- |
| Product narrative and command set | [`overall-plan.md`](./overall-plan.md) |
| Component architecture and CLI surface | [`overall-architecture.md`](./overall-architecture.md) |
| Actors and system boundary | [`../requirements-analysis/context-model.md`](../requirements-analysis/context-model.md) |
| Use cases | [`../requirements-analysis/use-case-model.md`](../requirements-analysis/use-case-model.md) |
| Per-sub-product interfaces | [`../interace-contract/`](../interace-contract/) |
| Per-sub-product workflows | [`../workflows/`](../workflows/) |
| Implementation foundations (install, output contract, persistence) | [`../implementation-plan/foundations.md`](../implementation-plan/foundations.md) |
