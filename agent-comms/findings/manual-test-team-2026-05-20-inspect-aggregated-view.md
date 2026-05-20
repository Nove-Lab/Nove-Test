---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-20
slug: inspect-aggregated-view
verdict: passed
related:
  - verifications/2026-05-20-inspect-aggregated-view.md
---

# Findings: `novetest inspect <run_id>` — aggregated single-run view

## Verdict: `passed`

All three documented scenarios and all four critical edge cases were
exercised against the merged CLI on a Linux dev box. Behaviour matched the
verification request exactly — including the byte-level envelope shapes.
No regressions, no issues filed.

## What was tested (plain-language narrative)

`novetest inspect <run_id>` used to be a placeholder that did nothing. As
of this slice it is a real command: give it the ID of a test run that was
already stored, and it hands back a single consolidated "report card" for
that run — what engine ran, whether the tests passed, how much code was
covered, and which deeper analyses (coverage / regression / localization /
replay) are available yet. It runs no tests itself; it only reads what is
already on disk. That makes it fast and safe to call repeatedly.

We confirmed the command behaves correctly in three situations:

1. **A run that has coverage data** — `inspect` shows the full coverage
   summary and marks the coverage sub-report as "available".
2. **A run with no coverage data** — `inspect` still succeeds, and clearly
   reports coverage as "unavailable" with a human-readable reason rather
   than failing or crashing.
3. **An ID that does not exist** — `inspect` returns a clean "not found"
   error and a non-zero exit code, no crash.

We then probed four trickier conditions the merge team asked us to stress,
all of which held up (details below).

## Commands run (verbatim) + observed output

CLI invoked as the repo virtualenv binary
(`/home/yjshin/dev/Nove-Test/.venv/bin/novetest`) from inside the scratch
copy of the fixture — this sidesteps the `uv run --with` wheel-staleness
trap documented in last cycle's findings (Issue #3 there).

### Scenario 1 — coverage-run inspect (happy path)

```sh
cp -r tests/fixtures/projects/pytest-coverage/. /tmp/nv-inspect-smoke/
cd /tmp/nv-inspect-smoke
novetest init
novetest run --coverage tests/      # entry_id 01KS2VXN4YDXCXYR1QH6SWNQBK
novetest inspect 01KS2VXN4YDXCXYR1QH6SWNQBK
```

Result: **exit 0**. Envelope structure matched the request verbatim:
- `data.coverage_outcome.kind == "fact-set"`
- `data.sub_reports.coverage == "available"`
- `data.coverage_outcome.run_reference.run_id == data.run_reference.run_id`
  (both `01KS2VXN4YDXCXYR1QH6SWNQBK`)
- coverage summary populated: `percent_covered 86.667`, `num_statements 11`,
  `num_branches 4`, `covered_statements 10`.
- `run_summary`: `engine_name pytest`, `status passed`,
  `summary_counts {collected:2, passed:2, total:2}`, `tombstoned false`.

### Scenario 2 — plain-run inspect (coverage unavailable)

```sh
novetest run tests/                 # entry_id 01KS2W25SWPNF53SEYWA0XPKB1
novetest inspect 01KS2W25SWPNF53SEYWA0XPKB1
```

Result: **exit 0**. `data.coverage_outcome.kind == "unavailable"`,
`reason == "missing-derived-facts"`, `detail` text matched the request
verbatim. `data.sub_reports.coverage == "unavailable"`; all four
sub-report keys present.

### Scenario 3 — unknown run_id -> `not-found`, exit 2

```sh
novetest inspect 01AAAAAAAAAAAAAAAAAAAAAAAA ; echo "exit=$?"
```

Result: **exit 2**. `ok false`, `data {}`, single error
`code "not-found"`, message
`No Memory Entry for run_id='01AAAAAAAAAAAAAAAAAAAAAAAA'`. Matched
verbatim.

## Critical edge cases — all pass

- **Uninitialized tree** — `novetest inspect <anything>` in a directory
  with no `.novetest/` store returned a structured `uninitialized`
  envelope, **exit 2**, `ok false`. **stderr was empty — no Python
  traceback leaked.** Message: "No Project Store found in this directory
  or any ancestor. Run `novetest init` to create one."

- **Tombstoned run** — we tombstoned the Scenario-2 run via
  `novetest memory delete 01KS2W25SWPNF53SEYWA0XPKB1`, then re-ran
  `inspect` on it. The run remained inspectable: **exit 0**, `ok true`,
  `data.run_summary.tombstoned == true`, full view populated (NOT
  `not-found`). The original test counts were preserved
  (`summary_counts {collected:2, passed:2, total:2}`). See the one
  informational observation below.

- **`run_reference` carries three keys** — confirmed: every
  `run_reference` block (top-level and nested under `coverage_outcome`)
  carries `run_id`, `created_at`, AND `schema_version: 1`. Consistent
  with `coverage show`. Not a drift.

- **`sub_reports` always has exactly four keys** — confirmed across all
  three scenarios and the tombstone case: `coverage`, `regression`,
  `localization`, `replay` are always present. Only `coverage` is
  dynamic; the other three are hard `"unavailable"`. No key ever missing.

## Issues found

None.

### Informational observation (not an issue, no action needed)

When a run is tombstoned, `data.run_summary.status` changes from its
original value (`"passed"`) to `"tombstoned"`, while `summary_counts`
still preserves the real outcome (`passed:2, total:2`). This is sensible
— `status` is acting as a top-level lifecycle discriminator and the
underlying test result is not lost. We flag it only because the
verification request's example envelope shows `"status": "passed"` for a
normal run and does not mention the tombstone substitution; a future doc
or contract note could spell this out. No code or behaviour concern.

## Recommendations for PM

1. **No follow-up required for this slice** — `inspect` is solid and
   ships clean.
2. **Optional contract note**: consider recording in
   `design/interace-contract/` (or the inspect workflow doc) that
   `run_summary.status` becomes `"tombstoned"` for a tombstoned run,
   while `summary_counts` retains the original counts — so downstream
   consumers know `status` is a lifecycle field, not purely a test
   verdict. Low priority; documentation hygiene only.
3. The `inspect` command is now a strong building block for the future
   `compare` / regression / localization sub-reports — each of those
   slices just needs to flip its `sub_reports` key from `"unavailable"`
   to `"available"`. The four-key invariant held perfectly, so that
   wiring should be low-risk.
