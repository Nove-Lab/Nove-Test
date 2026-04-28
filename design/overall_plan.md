# Nove Test — Overall plan

## **Stop vibe testing. Make your agent do genuine testing.**

### Nove Test is a testing engine for AI agents. It turns AI-written tests into **proof you can run again and manage**—not vibes.

---

## Executive summary

**Nove Test** is a **testing engine for AI agents**. It turns **quick, “feels fine”** testing work into **clear proof** the agent can **run again, keep, and act on**.

- **Users:** The **AI agent** is the **main user**: it **writes code**, **uses Nove Test to test that code**, and gets back **evidence and structured outputs** for the next change. **People** **watch**, **manage**, and **supervise** when they want. They do not need to drive every step.
- **Problem:** **AI-written tests** are often **shallow**, **hard to repeat**, and **hard to stack**—one run does not turn into **saved proof** for the next. There is usually **little evidence that tests are sufficient**—nothing that shows they **really cover risk**. A **green result** alone is **not real trust**.
- **Solutions:** A **sub-product family** on **shared contracts**, wrapping each stack’s **standard runners** (pytest, JUnit, …) so teams keep **CI interoperability** while turning runs into **saved, comparable proof**—not one-off green checks.
- **Expectations:** **With that stack**, **AI-run testing** becomes **deeper**, **repeatable for the same proof**, and **built on saved outputs**—not vibe guesses. **Trust** in **testing** and in **software AI built** **can keep pace with how fast AI ships code.**

---

## Product family strategy (sub-products → Nove Test)

Nove Test ships as **separate sub-products** that share contracts and can be adopted incrementally. **All governed test execution** for the family goes through **Nove Test Run** so sessions, fingerprints, and downstream evidence stay comparable. **Nove Test Orchestrator** (integration product) composes the sub-products into one **autonomous validation loop** when teams want the full experience.

**Agent-first by design:** every sub-product exposes **CLI, API, and structured JSON** shaped for **tool-calling agents** as a first-class experience.

**Nove Test Console** is the **human interface sub-product**: a **unified operator surface** with views into each sub-product so people see the **same artifacts and governance** the stack relies on.

### Sub-product line (delivery order for the MVP)

| Order | Sub-product | One-line role |
|------|-------------|----------------|
| 1 | **Nove Test Run** | Single execution gate; wraps dominant runners; `run_id`, fingerprint, limits. |
| 2 | **Nove Test Memory** | Archive Run outputs + simple regression-oriented diffs + continuity handles. |
| 3 | **Nove Test Oracle** | Execution-level verdicts, evidence blocks, fingerprints from Run outputs. |
| 4 | **Nove Test Trace** | Coverage + failure-time insight on the same session; handles for agents. |
| 5 | **Nove Test Replay** | Replay recipes + reproducibility checks via Run. |
| 6 | **Nove Test Explorer** | Coverage-guided exploration; child sessions via Run (or Orchestrator). |
| 7 | **Nove Test Orchestrator** | DAG, budgets, idempotency, scrub, tiered payloads—full loop composition. |
| ∥ | **Nove Test Console** | Unified human UI and governance across the family. |

Detailed purpose and expectations per sub-product: [`design/subproducts/`](./subproducts/).

---

## Product principles

1. **AI-native** — The **AI agent** is the **primary user** of **each** sub-product; **CLI, API, and structured JSON** are first-class on every surface. **Nove Test Console** gives humans the **same facts** for supervision and governance.
2. **Stop vibe testing** — Testing aims for **proof**, not “sounds OK.” Prefer **repeatable runs**, **traceable evidence**, and **clear pass/fail meaning** over loose, feel-based checks.
3. **Tests as assets** — Treat **tests, failures, coverage, traces, replays, and related outputs** as **saved objects** you can **reuse, compare, and build on**—not one-off throwaway files.
4. **Interop with industry runners** — Each stack’s **dominant test platform** (pytest, JUnit, …) does what it already does best; Nove wraps it and **follows native specs and formats** where they exist so teams stay compatible with existing CI and tooling.
5. **One execution gate** — For Nove-governed work, **tests run through Nove Test Run** so contracts (session, fingerprint, limits) are uniform for Memory, Oracle, Trace, Replay, Explorer, and Orchestrator.
6. **Cross-language support** — **Portable contracts** (identity, verdict, handles) span stacks; **language packs** adapt Run, Oracle, and Trace per runner ecosystem. Richer coverage meaning stays **within each stack** until a broader unified model is justified.
7. **Local runs, optional cloud** — **Repeatable, heavy execution stays local**; **analysis, governance, and parts of the experience** can use **optional cloud** when teams want it.

---

## Development roadmap and phases

Delivery follows the **sub-product order** above: **Run → Memory** first, with **early Console** for operators on the same data, then **Oracle → Trace → Replay → Explorer**, then **Orchestrator** as the integrating product. **Python** is the first vertical slice; additional language packs follow.

### MVP scope (one sentence)

Ship **Nove Test Run** and **Nove Test Memory** for **Python** (pytest-first), with **Nove Test Console** in early form, then layer **Oracle**, **Trace**, **Replay**, **Explorer**, and **Nove Test Orchestrator** until the full loop is available. **JS/TS and Java** adapters are **post-MVP** unless scope is explicitly expanded.

### Phases (aligned to the family)

- **Phase 1 — Run + Memory spine:** Schemas/handles + **Run** (Python) + **Memory** (archive + simple regression diff); **Console** surfaces the same data for operators; agent-first JSON on Run/Memory.
- **Phase 2 — Observation & meaning:** **Oracle** + **Trace** on the same `run_id`; Memory consumes richer signals.
- **Phase 3 — Replay & exploration:** **Replay** (replay-first) + scoped **Explorer**; Memory promotions and continuity harden.
- **Phase 4 — Orchestrator & GA loop:** **Nove Test Orchestrator** composes all sub-products; tiered payloads, streaming, idempotency, and plan-only mode as the **unified agent entrypoint** for the full workflow.
- **Phase 5 — Scale-out & monetized depth:** Additional language packs; optional **test-strength** (e.g. mutation) as paid add-on; richer Console and team features.

### Milestones (illustrative; map to sub-products)

1. **Backbone schema** — shared handles for run, failure, coverage, regression, replay (portable across sub-products).
2. **Nove Test Run (Python)** — subprocess pytest with Nove session envelope + fingerprint + agent JSON/CLI.
3. **Nove Test Memory** — archive + baseline + simple diff; continuity handles for next invocation.
4. **Nove Test Console v0** — Run + Memory views + adapters; governance hooks as APIs stabilize.
5. **Nove Test Oracle (Python)** — JUnit/native structured paths; verdict + fingerprint.
6. **Nove Test Trace (Python)** — coverage.py path; failure-time snapshots; handles.
7. **Nove Test Replay** — recipes + Run-backed verification + Memory integration.
8. **Nove Test Explorer** — budgeted exploration; Run child sessions; Trace/Oracle feedback.
9. **Nove Test Orchestrator** — full DAG, policies, tiered agent payload (contracts summarized in [`subproducts/nove-test-orchestrator.md`](./subproducts/nove-test-orchestrator.md)).
10. **Post-MVP** — JS/TS/Java packs; paid test-strength; enterprise Console and CI integrations.

---

## Business model

- **Domain:** ailovestesting.com  
- **Company:** NoveAI  
- **Product:** Nove Test (product **family**; sub-products and **Nove Test Orchestrator** as the integrated offering)  
- **Core positioning:** A testing stack for **AI agents** that turns **generated tests** into **reproducible, verifiable proof**—not vibes.

### How we make money (at a glance)

**One-line frame: Free = diagnosis, Paid = resolution.**

1. **Freemium (acquire)** — **Free:** coverage / run insight, read-only visibility into **gaps** so users see risk but cannot fully close it on the free tier alone.  
2. **Paid conversion (fix the gap)** — **Paid:** deeper exploration, **mutation-based test-strength and remediation**, fuzz / edge-case generation, reproducibility guarantees.  
3. **Modular packs** — **Per-language adapters** and **advanced engines** as add-ons—customers pay for the **scope** they need.  
4. **Team / enterprise** — CI gates, team Console, reporting, collaboration, governance.  
5. **Product-led growth** — `Free usage → gap visibility → friction → paid upgrade → team adoption → enterprise expansion`

### Pricing philosophy

- **Free = visibility** (diagnosis); **Paid = resolution** (generation + hardening).  
- Core paid value around **test-strength hardening**, **advanced exploration**, and **reproducibility guarantees**.

### Why we are different

- Coverage is framed as **often insufficient**, not a trophy metric alone.  
- Work is **reproducible** and backed by **handles and archives**, not one-off “vibes.”  
- **Agent-first on every sub-product**, not bolt-on.  
- **Interop:** we ride pytest/JUnit/…, we do not fork the ecosystem story.

### Where this goes

- From **testing** toward broader **QA / reliability** and **agent testing infrastructure**; deeper hooks in **CI, review, and deployment gates**.

### One line

**Free tools show coverage; Nove Test shows whether tests actually work—and helps you harden them.**

---

## Doc map

| Area | Document |
|------|----------|
| Product narrative (this file) | `design/overall_plan.md` |
| Product family architecture | `design/architecture.md` |
| Implementation stack (CTO guide) | `design/implementation_plan.md` |
| Sub-product specs | `design/subproducts/nove-test-run.md`, `nove-test-memory.md`, `nove-test-oracle.md`, `nove-test-trace.md`, `nove-test-replay.md`, `nove-test-explorer.md`, `nove-test-orchestrator.md`, `nove-test-console.md` |

---

## Open questions and decision log

- **MVP is Python-first** (pytest as default adapter); JS/TS and Java are post-MVP unless replanned.
- **All governed execution goes through Nove Test Run**; Orchestrator never replaces Run’s runner contract.
- **Determinism tiers** — details in `nove-test-run.md`; narrative stays high-level.
- **Oracle** — execution-level core; behavioral correctness beyond project tests remains out of scope for the core Oracle contract.
- **Agent contract (full stack)** — tiering, streaming, idempotency, hints, annotations: normative summary in `nove-test-orchestrator.md`; per-product CLIs may expose subsets earlier.
- **Mutation / test-strength** — optional paid add-on; not required for the minimal Run→Memory→Oracle→Trace spine.
- **Artifact substrate** — implemented as part of Run/Memory engineering (handles, CAS-style blobs); not a separately marketed sub-product in this line.
