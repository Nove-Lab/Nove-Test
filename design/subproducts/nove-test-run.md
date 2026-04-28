# Nove Test Run

**Context:** [Product family architecture](../architecture.md) · **Sub-product 1 (foundation).**

## Purpose

The **single execution gate** for the Nove Test product line. All test execution that must honor Nove contracts (session identity, environment fingerprint, resource limits, determinism tiers) goes **through Run**, wrapping each stack’s **dominant test runner** (e.g. pytest, JUnit) **without replacing** its CLI semantics, report formats, or interoperability with the rest of the industry.

## Role

- Wraps **pytest / JUnit / …** via **language-pack adapters**; preserves native behavior where it is part of the public contract.
- Emits **`run_id`**, bounded streams, exit metadata, and **environment fingerprint** so downstream sub-products attach to one comparable session.

## Expectations

- **Agent-first:** Run exposes **CLI + structured JSON** (or equivalent) suitable for tool-calling agents for “execute once and return session summary.”
- Other sub-products **do not spawn the native runner directly** for Nove-governed work; they request **child or replay sessions** via Run (or via **Nove Test Orchestrator**, which delegates to Run).
- Determinism tier semantics and fingerprint fields are specified here as this product evolves (not in the high-level narrative alone).
