# Nove Test Oracle

**Context:** [Product family architecture](../architecture.md) · **Sub-product 3.**

## Purpose

Turns **Run** session outputs (exit codes, stderr, framework-native structured reports such as JUnit XML, framework-reported assertion failures) into a **small, stable verdict taxonomy**, **machine-readable evidence blocks**, and **failure fingerprints**—without claiming full behavioral correctness beyond what the project’s own tests assert.

## Role

- Consumes signals produced **only after a Run completes** (or from the same session attachment point).
- Feeds **Memory** and **Replay** with comparable failure identity; informs **Explorer** when classifying exploratory outcomes.

## Expectations

- **Agent-first:** verdicts and fingerprints are JSON-friendly and sized for agent payloads.
- **Execution-level scope** for the core product line; semantic/business oracles driven by separate AI generation are out of scope for this sub-product’s core contract.
- **Interop:** parsers and normalizers follow **industry-standard shapes** from each dominant runner where they exist.
