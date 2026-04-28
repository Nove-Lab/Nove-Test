# Nove Test Console

**Context:** [Product family architecture](../architecture.md) · **Sub-product 8 (human surface).**  
Developed **in parallel from the first shipped sub-products** (Run + Memory onward) and **continued** as new sub-products appear.

## Purpose

**Unified human operator experience** over the **same artifact handles and structured facts** agents consume—diff-first views, drill-down to evidence (coverage handles, replay recipes, Oracle blocks), and **governed actions** (baseline promote/demote, mute, annotations) with **audit log**.

## Role

- Implements **per–sub-product adapters** so one shell can show Run sessions, Memory timelines and diffs, Oracle verdicts, Trace summaries, Replay status, Explorer corpus growth, and Orchestrator invocations as they come online.
- Calls the **same Orchestrator / Memory APIs** the CLI uses so humans and agents never disagree on underlying facts—only on policy.

## Expectations

- **Not the primary driver** of the inner loop; agents remain first actors on each sub-product; Console supervises.
- **MVP Console:** minimal visualization (e.g. static HTML from dumped JSON or a small local UI) is enough early; rich dashboards and SSO are post-MVP.
- **No duplicate persistence:** reads/writes go through Memory / artifact substrate and Orchestrator as designed—not a parallel database of truth.
- **Governance:** read-only vs write-capable modes; every governed action audited.
