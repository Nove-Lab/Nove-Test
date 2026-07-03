---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: resolved
created: 2026-07-04
slug: engine-scoped-regression-prior
related:
  - agent-comms/verifications/2026-07-04-engine-scoped-regression-prior.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Findings: localization engine-scoped regression-prior (D5 Finding B — Wave 2, 2/3)

## Verdict: **passed**

## Narrative (for the CEO)

Fault localization ("which code is probably broken?") can sharpen its
ranking using the previous run's regression data. Before this slice, in a
workspace whose history mixes engines (e.g. Rust + Python runs
interleaved), the "previous run" lookup was engine-blind: it grabbed the
newest older run even if it came from a different engine, and the
sharpening silently switched off. Now the lookup delegates to the shared
engine-aware selector, so it finds the most recent *same-engine* run and
the sharpening activates where it should. No output formats changed — this
is purely smarter selection under the hood. I ran the acceptance tests
(6/6), a 471-test cross-suite over every consumer of the shared selector,
a real single-engine localization flow to confirm nothing shifted for the
common case, and a live mixed-engine store to watch the selector skip an
interleaved Rust run and pair the two Python runs — exactly the D5 promise.

## Commands run (verbatim) + observed output

### Step 1 — acceptance suite ✅

```
env -u PYTHONPATH uv run pytest -q tests/unit/localization/test_regression_prior.py -v
  → 6 passed (0.14s)
```

The six cases: `mixed_engine_store_applies_fluccs_reweighting` (the
behavioral proof — full `derive_localization_findings`, asserts
`regression_reweighted is True` + boosted changed-file at rank 1),
`mixed_engine_store_probe_finds_same_engine_pair_one_step_back`,
`single_engine_store_prior_selection_unchanged`,
`no_prior_run_returns_none`, `cross_engine_only_priors_return_none`,
`prior_without_cached_facts_returns_none`.

### Step 2 — targeted cross-suite ✅

```
env -u PYTHONPATH uv run pytest -q tests/unit/localization tests/integration/localization tests/unit/regression tests/unit/orchestration
  → 471 passed (7.84s)
```

### Step 3 — envelope stability, single-engine store ✅

`pytest-failing` fixture copy → `init` → `run --coverage` →
`novetest localization --run-id <run>` → exit 0, `ok: true`, normal
outcome: `confidence: high`, ranked entries with code locations +
alternate scores (dstar2/op2/tarantula). Nothing about the single-engine
flow moved.

### Extra E2E — the D5 selector observed live in a mixed store ✅

In `/tmp/mt-cov` (two real pytest `--coverage` runs) I seeded a cargo-test
run record timestamped **between** them, then:

```
$PY -m novetest regression latest    # exit 0
  kind: fact-set
  baseline: 01KWMD2MDYDXE0DMW8WMJYVG8C   (pytest run 1)
  target  : 01KWMD35QR0J42DJCJZQ20CV2A   (pytest run 2)
```

The interleaved cargo run — the run an engine-blind "newest strictly
older" scan would have picked — was skipped; the same-engine pair one step
back was selected and normal facts derived. This is the exact
mixed-history behavior the slice exists to enable.

### Edge probes ✅

- **Cross-engine-only priors stay silent-and-correct**: in a store whose
  only runs older than a failing cargo-test run are pytest runs,
  `novetest localization --run-id <cargo run>` → exit 0, `kind: fact-set`,
  `mode: failure_proximity`, `metadata.regression_reweighted: false` — no
  reweighting, no error, no refusal. The best-effort posture held E2E.
- **Head-run resolution engine-agnostic, no surprise refusals**: in the
  mixed store, localization on the newest (all-passing) pytest run →
  graceful `unavailable / no_failed_tests` — the documented reason, not an
  engine-related refusal.
- **Same-engine prior WITHOUT a regression cache → None** is pinned by
  `test_prior_without_cached_facts_returns_none` (cache-only probe; ran
  green in step 1).

## Issues found

**None.** No envelope drift observed on single-engine flows; mixed-engine
behavior matches the decision and the handoff.

## Recommendations for PM

1. Close this slice as verified.
2. Optional nicety spotted while probing (pre-existing, NOT this slice):
   bare `novetest localization` without `--run-id` emits a non-JSON
   Cyclopts error panel (exit 1) rather than a JSON envelope — the only
   non-JSON surface I touched all cycle. If the AI-first contract is meant
   to cover argument-parse errors, a small orchestration follow-up could
   catch it; otherwise ignore.

*(Process note: findings written via Bash heredoc per GOTCHAS.md
Write-isolation gotcha — no deliverable impact.)*
