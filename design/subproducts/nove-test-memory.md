# Nove Test Memory

**Context:** [Product family architecture](../architecture.md) · **Sub-product 2.**

## Purpose

**Archive and regression surface** for everything produced after a Run: time-ordered storage of outcomes, handles to blobs (via content-addressed layout where applicable), and **simple regression-oriented diffs** (e.g. failure sets, test identities, coarse new/fixed/known) so agents and **Nove Test Console** share one timeline of proof.

## Role

- Ingests **Run** session records (and later Oracle verdicts, Trace handles, Replay recipes, Explorer corpus pointers).
- Owns **baselines**, **continuity handles** for the next invocation, and **promotion / governance hooks** consumed by Console and Orchestrator.
- Hosts or indexes **artifact handles** so proof stays portable across machines and CI.

## Expectations

- **Agent-first:** read/write APIs for querying archives, submitting annotations, and receiving diff summaries in structured form.
- Early versions prioritize **faithful archiving + simple diff** over full classification sophistication; depth grows as Oracle and others land.
- Depends on **Run** for meaningful regression comparison at the execution-contract level.
