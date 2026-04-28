# Nove Test Orchestrator

**Context:** [Product family architecture](../architecture.md) · **Sub-product 7 (integration layer).**  
Formerly referred to as “platform”; this is the **named integration product** that composes the other sub-products.

## Purpose

Coordinates **Nove Test Run**, **Memory**, **Oracle**, **Trace**, **Replay**, and **Explorer** into a **single autonomous testing workflow**: one **invocation** with budgets, idempotency, scrub-before-store, flake policy, and a **tiered agent-facing payload** built from the same artifacts **Nove Test Console** reads.

## Role

- Owns the **stage DAG** (Run → Trace ∥ Oracle → … → Memory, with Explorer children and Replay on failures as configured).
- Enforces **cross-cutting policy** so sub-products stay composable: cancellation, partial results, correlation ids, **artifact store writes** only after scrub gate.

## Expectations

- **Agent-first (primary contract surface for full-stack use):**  
  - **Invocation bundle** inputs: `invocation_id` (idempotency), `requested_determinism_tier`, `budget`, `payload_tier` (`summary` | `standard` | `deep`), optional `change_set`, optional **Memory `continuity`** handles.  
  - **Responses:** every payload declares `schema_version`, `engine_version`, `tier`; includes terminal status, **stop reason**, **budget telemetry**, bounded failures with **handles** (never inline large blobs), **next-action hints** from a **stable enum** (e.g. `stabilize_env`, `add_assertion`, `expand_corpus`, `fix_flake`, `fix_timeout`, `tighten_sandbox`, `fix_infra_error`, `investigate_drift`), and **deterministic ordering** of lists for the same inputs.  
  - **Streaming:** incremental events (`stage:start`, `stage:end`, `partial:failure`, `budget:update`, `terminal`) sharing `invocation_id` and a sequence number; batch mode remains available.  
  - **Plan-only mode:** `plan: true` returns DAG + cost estimate without execution.  
  - **Annotation ingress** to Memory (dedup / merge / mute hints) as an **overlay** layer, auditable, never silently overwriting engine classification.  
  - **Agent micro-loop:** document session continuity—re-submit with same `session_id` and Memory `continuity` so baselines align across invocations.  
- **CLI reference** (`novetest` or product CLI) should mirror the same contract: e.g. `run`, `replay`, `annotate`, tier and stream flags; exit codes map to terminal statuses; full JSON on stdout or `--output`.
- Individual sub-products may expose **narrower agent surfaces** before Orchestrator ships; Orchestrator becomes the **single envelope** for the full loop.

## Non-goals (at contract level)

- Does not replace **Run**’s responsibility to invoke dominant native runners with industry-interoperable semantics.
- Does not mandate a specific HTTP/gRPC transport; any remote adapter must conform to the same JSON/event contracts.
