# Nove Test — Product family architecture

This document describes how the **Nove Test** sub-products fit together: **who acts**, **how execution flows**, and **what depends on what**. It stays at the **family** level; per-sub-product purpose and expectations live under [`subproducts/`](./subproducts/).

**Related planning:** [`overall_plan.md`](./overall_plan.md) (strategy, principles, roadmap).

---

## 1. What the family must achieve

1. **Single execution gate** — All Nove-governed test runs go through **Nove Test Run**, wrapping each stack’s dominant runner (pytest, JUnit, …) while preserving **interop with native CLIs and report formats** where the industry defines them.

2. **Comparable proof** — **Session identity**, **environment fingerprint**, and **artifact handles** let **Memory**, **Replay**, and **Orchestrator** compare runs over time without re-executing blindly.

3. **Agent-first everywhere** — Each sub-product exposes **structured, tool-calling-friendly** surfaces; there is no separate “agent SKU.” **Nove Test Orchestrator** is the **unified envelope** for the full loop when teams want one invocation.

4. **Human parity** — **Nove Test Console** reads the **same handles and payloads** agents use, with adapters per sub-product; governance actions go through the same APIs as the CLI where possible.

5. **Composable growth** — Sub-products can ship and deliver value **individually** early (Run + Memory + Console), then stack until **Orchestrator** binds the full DAG.

---

## 2. Actors and boundaries

| Actor | Role | Typical touchpoints |
|--------|------|---------------------|
| **AI agent** | Primary user of every sub-product; drives runs, reads archives, consumes diffs and hints | Each sub-product’s CLI/API/JSON; **Nove Test Orchestrator** for full-stack invocations |
| **Human operator** | Supervise, govern baselines, triage | **Nove Test Console** |
| **Nove Test product family** | Run, Memory, Oracle, Trace, Replay, Explorer, Orchestrator (+ Console) | This document + [`subproducts/*.md`](./subproducts/) |

The family **does not** replace **VCS** or the **CI scheduler**; it **integrates** via CLIs/APIs and **exported artifacts**.

---

## 3. Sub-product index

| # | Sub-product | Role (one line) | Spec |
|---|-------------|-----------------|------|
| 1 | **Nove Test Run** | Execution gate: native runner + Nove session contract. | [`subproducts/nove-test-run.md`](./subproducts/nove-test-run.md) |
| 2 | **Nove Test Memory** | Archive, baselines, simple regression diffs, continuity. | [`subproducts/nove-test-memory.md`](./subproducts/nove-test-memory.md) |
| 3 | **Nove Test Oracle** | Verdicts, fingerprints, evidence from Run signals. | [`subproducts/nove-test-oracle.md`](./subproducts/nove-test-oracle.md) |
| 4 | **Nove Test Trace** | Coverage + failure-time insight on `run_id`. | [`subproducts/nove-test-trace.md`](./subproducts/nove-test-trace.md) |
| 5 | **Nove Test Replay** | Replay recipes + reproducibility via Run. | [`subproducts/nove-test-replay.md`](./subproducts/nove-test-replay.md) |
| 6 | **Nove Test Explorer** | Budgeted exploration; child runs via Run. | [`subproducts/nove-test-explorer.md`](./subproducts/nove-test-explorer.md) |
| 7 | **Nove Test Orchestrator** | Composes all; policies; tiered agent payloads. | [`subproducts/nove-test-orchestrator.md`](./subproducts/nove-test-orchestrator.md) |
| ∥ | **Nove Test Console** | Unified human UI + adapters (parallel from #1). | [`subproducts/nove-test-console.md`](./subproducts/nove-test-console.md) |

---

## 4. Dependency spine (logical)

```
                    ┌──────────────────────────────────────┐
                    │     Nove Test Orchestrator (opt.)   │
                    │  DAG · budgets · idempotency · JSON │
                    └─────────────────┬────────────────────┘
                                      │
     ┌─────────────── Run ◄────────────┼──────────── child sessions
     │  (only execution gate)         │
     ▼                                │
  Memory ◄── Oracle ◄── (same session attach)
     ▲           ▲
     │           │
  Trace      Replay
     ▲
     └── Explorer (feedback loop; always via Run for execution)
```

- **Run** depends on **nothing** in the Nove family (only language packs + OS).  
- **Memory** depends on **Run** (and grows richer with Oracle, Trace, Replay, Explorer outputs).  
- **Oracle** depends on **Run**.  
- **Trace** depends on **Run**; **Memory** for baseline-relative deltas when used.  
- **Replay** depends on **Run** + **Oracle**.  
- **Explorer** depends on **Run** + **Oracle** + **Trace**; **Memory** optional for seeds/continuity.  
- **Orchestrator** depends on **all** when offering the full loop.  
- **Console** depends on **whatever sub-products are shipped** (adapters per product).

---

## 5. End-to-end loop (when Orchestrator is used)

1. Agent (or human via Console triggering Orchestrator) submits an **invocation bundle** (targets, seeds, budgets, `invocation_id`, optional Memory **continuity**).
2. **Orchestrator** schedules **Run** → attaches **Trace** and **Oracle** to the same session → optionally **Explorer** (child Runs) → on failure **Replay** → commits into **Memory**.
3. **Memory** returns **diffs, classifications, and continuity handles** for the next invocation—closing the loop described in product strategy.

Without Orchestrator, agents may **compose** sub-products manually in order; Run → Memory remains the **minimal closed archive loop**.

---

## 6. Language packs

**Language packs** are **adapters** for Run (invoke pytest/JUnit/…), Oracle (parse native structured outputs), Trace (coverage backends), and Replay (recipe shape). They live in implementation repos, not as separate rows in the sub-product index, but they are **required** for each new stack.

**Rule:** Nove follows **native runner contracts** for interoperability; packs translate into the **shared Nove artifact model** (handles, `run_id`, verdict enum at the portable layer).

---

## 7. Cross-cutting concerns

- **Artifact identity** — Content-addressed blobs + manifests (engineering inside Run/Memory path; see sub-product notes).
- **Determinism & fingerprint** — Owned by **Run** output; consumed by Memory, Replay, Orchestrator.
- **Scrubbing & retention** — Orchestrator gate before persistence when Orchestrator is used; policy tables owned with Memory engineering.
- **Flake policy** — Orchestrator when present; history stored in Memory.
- **Security** — MVP: process + env policy; stronger sandbox adapters later.

---

## 8. Suggested reading order

1. [`overall_plan.md`](./overall_plan.md) — strategy and roadmap  
2. **This file** — family shape and dependencies  
3. [`implementation_plan.md`](./implementation_plan.md) — CTO stack choices for the Python slice  
4. [`subproducts/nove-test-run.md`](./subproducts/nove-test-run.md) onward — one file per sub-product  
