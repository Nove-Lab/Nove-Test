---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: resolved
created: 2026-07-04
slug: coverage-compare-engine-guard
related:
  - agent-comms/verifications/2026-07-04-coverage-compare-engine-guard.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md
---

# Findings: coverage-compare-engine-guard (D5 Finding A — Wave 2, 1/3)

## Verdict: **passed**

## Narrative (for the CEO)

Before this slice, asking novetest to diff the code coverage of a Python
test run against a Rust test run would happily produce a number — a
meaningless one, since the two engines measure different code. Now the
product refuses cleanly: it reports the comparison as **unavailable** with
the reason **engine-mismatch**, names both engines so the user knows exactly
why, and does so as a *successful answer* (exit 0), not a crash — refusing
to lie is a valid result. I verified this end-to-end with a real pytest
coverage run plus a seeded Rust run in the same store, confirmed ordinary
same-engine diffs still work exactly as before, and confirmed the top-level
`compare` verb's two halves (coverage + regression) now tell the same story
on a cross-engine pair instead of one half being silently wrong.

## Commands run (verbatim) + observed output

```
REPO=/home/yjshin/dev/Nove-Test; PY=$REPO/.venv/bin/python
rm -rf /tmp/mt-cov && cp -r $REPO/tests/fixtures/projects/pytest-coverage /tmp/mt-cov
cd /tmp/mt-cov && $PY -m novetest init && $PY -m novetest run --coverage tests/   # exit 0
# → pytest RUNID 01KWMD2MDYDXE0DMW8WMJYVG8C
# seeded cargo facts via /tmp/mt-seed-cargo.py (verbatim copy of
# tests/integration/orchestration/test_coverage_cli.py::_seed_cargo_fact_set)
# → cargo run 01HCARGO00000000000000FACT
```

### Step 1 — cross-engine refusal ✅ (matches the verification anchor byte-for-byte in shape)

```
$PY -m novetest coverage diff 01KWMD2MDYDXE0DMW8WMJYVG8C 01HCARGO00000000000000FACT   # exit 0
ok: true
data.coverage_delta: {
 "detail": "baseline engine_name='pytest' != target engine_name='cargo-test'",
 "kind": "unavailable",
 "reason": "engine-mismatch",
 "run_reference": {"run_id": "<BASELINE pytest run_id>", ...}
}
# no delta fields leak (file_deltas / files_added / files_removed / summary_delta all absent)
```

### Step 2 — same-engine diff unchanged ✅

Second `run --coverage tests/` then `coverage diff <run1> <run2>` → exit 0,
`kind: "delta"` with the normal fields (`baseline_granularity,
baseline_run_reference, file_deltas, files_added, files_removed,
summary_after, summary_before`). The guard keys on inequality, not a
privileged engine.

### Step 3 — TEXT mode ✅

```
$PY -m novetest coverage diff <pytest> <cargo> --output text   # exit 0
coverage diff · — unavailable (engine-mismatch)
```

Reason-generic rendering confirmed; no crash.

### Step 4 — targeted suite ✅

```
env -u PYTHONPATH uv run pytest -q tests/unit/coverage/ tests/integration/orchestration/test_coverage_cli.py
  → 158 passed (11.67s)
```

### Edge probes — all ✅

- **Argument-order symmetry**: `coverage diff <cargo> <pytest>` →
  `detail: "baseline engine_name='cargo-test' != target engine_name='pytest'"`,
  `run_reference` = the cargo run (the new baseline). Follows argument
  order exactly as pinned.
- **Single-side-missing precedence**: seeded a second cargo run WITHOUT
  facts → `coverage diff <pytest> <cargo-no-facts>` →
  `reason: "missing-derived-facts"`, detail "No coverage_facts.json found
  for this run…", run_reference = the facts-less side. The missing side's
  OWN reason fires BEFORE the engine guard. ✅
- **Top-level `compare` verb**: `novetest compare <pytest> <cargo>` →
  exit 0; `data.coverage_delta` → `unavailable / engine-mismatch` AND
  `data.regression_outcome` → `unavailable / engine-mismatch` with the
  identical detail wording. Both halves of the envelope now AGREE. ✅

## Issues found

**None.** No regressions; the 2026-05-16 envelope constraints (unavailable
is not a CLI error; no delta-field leakage) hold everywhere probed.

## Recommendations for PM

1. Close this slice as verified. The CI-matrix bullet (10/10) remains a
   post-merge item for whoever holds dispatch rights, as Main Branch noted.
2. Nothing else — this was a tight, zero-conflict slice that did exactly
   what the D5 audit asked.

*(Process note: findings written via Bash heredoc per GOTCHAS.md
Write-isolation gotcha — no deliverable impact.)*
