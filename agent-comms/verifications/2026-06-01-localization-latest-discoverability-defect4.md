---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-06-01
slug: localization-latest-discoverability-defect4
merged_commit: 4b5fd1d
source_handoffs:
  - agent-comms/handoffs/localization-team-2026-06-01-latest-aggregate-discovery-defect4.md
source_tasks:
  - agent-comms/tasks/localization-team-2026-06-01-latest-aggregate-discovery-defect4.md
related:
  - agent-comms/history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md
  - agent-comms/questions/main-branch-team-2026-06-01-localization-latest-aggregate-discovery.md
  - src/novetest/localization/retrieval.py
  - src/novetest/localization/derive.py
  - tests/integration/localization/test_latest_verb_non_per_test.py
---

# Verification: Defect 4 closed — `novetest localization latest` now works for all 3 modes

## Merged commit + summary

**Merged at**: `4b5fd1d` (FF from `97285e5`; single-commit slice).

The `check_localization_availability` gate at `retrieval.py:67-99` was
relaxed to match the 3-mode dispatch in
`derive_localization_findings`. Pre-fix the gate insisted on
`mapping_granularity == "per-test"`, which made `novetest localization
latest` return `kind: "unavailable", reason: "run_not_analyzable"` for
3 of the 4 supported languages (cargo/go/jest aggregate runs + any
coverage-less run) — even though the explicit `<run_id>` verb already
handled them correctly via the dispatcher. Post-fix the resolver
walks `list_run_history` and returns the newest non-tombstoned run
with at least one failed test; the dispatcher then routes it to
`sbfl_per_test` / `sbfl_aggregate` / `failure_proximity` based on
coverage shape.

**Net surface**: 2 src files modified (gate + docstring relaxation
only; ZERO new src files; source count stays at 72), 4 test files
modified (assertion flips + helper switch), 1 new integration test
file (3 mode-coverage tests).

**Test counts**:
- Local equipped-host gate (this box, cargo on PATH): **762 passed +
  5 skipped** in 52.10s (Loc team's `_latest_verb_returns_aggregate_finding_for_cargo_fixture`
  test flips from skip → pass; gate is clean).
- mypy `--strict`: **Success: no issues found in 72 source files**.
- The new test `test_latest_verb_returns_aggregate_finding_for_cargo_fixture`
  PASSES on this equipped host (Loc team SKIP-guarded it for their
  Rust-less dev box; Pre-flight §A from the handoff is now
  empirically validated through Main Branch's gate AND via the CLI
  smoke in Scenario A below).

## Source handoffs consumed

1. `agent-comms/handoffs/localization-team-2026-06-01-latest-aggregate-discovery-defect4.md` — single handoff for the single-commit fix-up slice.

## What to verify (8 scenarios for Manual Test)

> **Note for Manual Test**: All scenarios below use REPRODUCIBLE
> fixture flows. The exact envelope shapes pasted under each
> scenario were captured by Main Branch running the same commands
> against the merged tip (`4b5fd1d`) — `run_id`s and timestamps
> will differ in your run, but the SHAPE + load-bearing fields
> should match. Paste your actual envelopes into findings.
>
> **All envelope paths + JSON field literals in this doc were
> verified by Main Branch dry-running each scenario against the
> merged tip before this verification was filed.** (Per Manual
> Test's prior-cycle feedback on dry-run discipline.)

### Scenario A — Defect 4 closure proof: cargo aggregate via `latest`

**Setup**:
```sh
. "$HOME/.cargo/env"
cp -r tests/fixtures/projects/localization-aggregate-only /tmp/d4-cargo
cd /tmp/d4-cargo
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run --coverage >/dev/null 2>&1   # status=failed, has_coverage_facts=true
```

**Probe**:
```sh
novetest localization latest
```

**Expected load-bearing envelope** (verbatim shape, copy-pasted from
merged-tip run; `run_id` will differ):
```json
{
  "command": "localization.latest",
  "data": {
    "localization_outcome": {
      "kind": "fact-set",
      "mode": "sbfl_aggregate",
      "confidence": "medium",
      "ecosystem": "rust",
      "engine_name": "cargo-test",
      "formula": "ochiai",
      "alternate_scores_available": ["dstar2", "op2", "tarantula"],
      "metadata": {
        "changed_files_count": 0,
        "regression_reweighted": false
      },
      "top_n": 10,
      "entries": [
        {
          "rank": 1,
          "score_raw": 0.5,
          "score_normalized": 0.0,
          "formula": "ochiai",
          "code_location": {
            "file": "src/arithmetic.rs",
            "kind": "file",
            "primary_line": 53,
            "evidence_lines": [53],
            "line_range": null,
            "symbol": null
          },
          "related_failed_tests": [
            "localization_aggregate_only::localization_aggregate_only$arithmetic::tests::test_divide"
          ],
          "tied_with": [],
          "alternate_scores": {
            "dstar2": 0.3333333333333333,
            "op2": 0.25,
            "tarantula": 0.5
          }
        }
      ]
    }
  },
  "ok": true,
  "errors": [],
  "warnings": [],
  "schema": "novetest/v1"
}
```

**Pre-fix would have returned** (negative-proof reference; you do
NOT need to reproduce this — `97285e5` is the pre-fix tip if you
want to historically verify):
```json
{
  "data": {
    "localization_outcome": {
      "kind": "unavailable",
      "reason": "run_not_analyzable",
      "detail": "no analyzable runs in store (1 candidates checked)",
      "run_reference": null
    }
  },
  "ok": true
}
```

**What to assert in findings**:
- `kind == "fact-set"` (not `"unavailable"`)
- `mode == "sbfl_aggregate"`
- `confidence == "medium"`
- `entries[0].rank == 1`
- `entries[0].code_location.file == "src/arithmetic.rs"`
- `entries[0].code_location.primary_line == 53`
- `entries[0].score_raw == 0.5` (Ochiai math: `1 / sqrt((1+0)*(1+3))` = `0.5`; 3 covered non-failing lines in arithmetic.rs)
- `top_n == 10` (default; explicit `--top-n N` covered in Scenario E)

### Scenario B — failure_proximity discoverability via `latest`

**Setup**:
```sh
cp -r tests/fixtures/projects/localization-no-coverage /tmp/d4-pyfp
cd /tmp/d4-pyfp
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run >/dev/null 2>&1   # NO --coverage; status=failed
```

**Probe**:
```sh
novetest localization latest
```

**Expected load-bearing envelope** (verbatim shape):
```json
{
  "command": "localization.latest",
  "data": {
    "localization_outcome": {
      "kind": "fact-set",
      "mode": "failure_proximity",
      "confidence": "low",
      "ecosystem": "python",
      "engine_name": "pytest",
      "formula": "ochiai",
      "alternate_scores_available": [],
      "metadata": {
        "changed_files_count": 0,
        "regression_reweighted": false
      },
      "top_n": 10,
      "entries": [
        {
          "rank": 1,
          "score_raw": 1.0,
          "score_normalized": 0.0,
          "code_location": {
            "file": "/tmp/d4-pyfp/localization_no_coverage/statistics.py",
            "kind": "file",
            "primary_line": 39,
            "evidence_lines": [39],
            "line_range": null,
            "symbol": null
          },
          "related_failed_tests": [
            "tests/test_statistics.py::test_average_of_empty_returns_zero"
          ],
          "tied_with": [],
          "alternate_scores": {}
        }
      ]
    }
  }
}
```

**What to assert in findings**:
- `kind == "fact-set"` (not `"unavailable"`)
- `mode == "failure_proximity"`
- `confidence == "low"`
- `entries[0].code_location.file` ENDS WITH `"statistics.py"`
- `entries[0].code_location.primary_line == 39`
- `alternate_scores_available == []` (failure_proximity doesn't compute alternates)
- `entries[0].alternate_scores == {}` (matching empty list above)

**Mode quirk to flag** (worth documenting in your findings):
`failure_proximity` mode emits **absolute file paths** (e.g.,
`/tmp/d4-pyfp/localization_no_coverage/statistics.py`), whereas
`sbfl_aggregate` (Scenario A) and `sbfl_per_test` (Scenario C)
emit **repo-relative paths** (e.g., `src/arithmetic.rs`,
`localization_branch/calculator.py`). This is a UX inconsistency
across modes — not introduced by this slice, but now visible on
the `latest`-verb surface. If you think this should be normalized,
escalate via findings; PM can decide.

### Scenario C — per-test regression-pin via `latest`

**Setup**:
```sh
cp -r tests/fixtures/projects/localization-branch /tmp/d4-pypt
cd /tmp/d4-pypt
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run --coverage >/dev/null 2>&1
```

**Probe**:
```sh
novetest localization latest
```

**Expected load-bearing envelope** (verbatim shape; first entry only —
this fixture returns 10 entries with rank-1/rank-1 tie):
```json
{
  "data": {
    "localization_outcome": {
      "kind": "fact-set",
      "mode": "sbfl_per_test",
      "confidence": "high",
      "ecosystem": "python",
      "engine_name": "pytest",
      "formula": "ochiai",
      "alternate_scores_available": ["dstar2", "op2", "tarantula"],
      "metadata": {},
      "top_n": 10,
      "entries": [
        {
          "rank": 1,
          "score_raw": 1.0,
          "score_normalized": 1.0,
          "code_location": {
            "file": "localization_branch/calculator.py",
            "kind": "symbol",
            "symbol": "divide",
            "primary_line": 34,
            "evidence_lines": [34],
            "line_range": [31, 34]
          },
          "related_failed_tests": [
            "tests/test_calculator.py::test_divide_yields_quotient"
          ],
          "tied_with": ["entry_index_1"],
          "alternate_scores": {
            "dstar2": 0.0,
            "op2": 1.0,
            "tarantula": 1.0
          }
        }
      ]
    }
  }
}
```

**What to assert in findings**:
- `kind == "fact-set"`
- `mode == "sbfl_per_test"` (UNCHANGED from pre-Defect-4 behavior — load-bearing regression-pin)
- `confidence == "high"`
- `entries[0].rank == 1`
- `entries[0].code_location.file == "localization_branch/calculator.py"`
- `entries[0].code_location.symbol == "divide"` (symbol-level granularity, unlike Scenarios A+B which are file-level)
- `entries[0].code_location.kind == "symbol"` (per-test has symbol info; aggregate + failure_proximity have `kind == "file"`)
- `metadata == {}` (per-test specific; differs from `{"changed_files_count", "regression_reweighted"}` in Scenarios A+B — see "Mode-specific metadata shape" below)

**Mode quirk to flag**: `metadata` shape is **mode-specific** —
- `sbfl_per_test` -> `{}`
- `sbfl_aggregate` + `failure_proximity` -> `{"changed_files_count": 0, "regression_reweighted": false}`

This is because `_derive_aggregate` (the function `_derive_failure_proximity`
inherits its envelope-shaping from) computes FLUCCS-style change-set
metadata as part of its contract; per-test doesn't. If Manual Test
thinks this asymmetry needs normalizing, escalate.

### Scenario D — Cross-verb consistency: `<run_id>` matches `latest` on the same run

**Setup**: re-use any of the 3 fixtures above (Scenario A
recommended). Extract the `run_id` from `novetest status`, then
call both verbs.

**Setup + probe**:
```sh
cd /tmp/d4-cargo
RUN_ID=$(novetest status 2>/dev/null | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['latest_run_reference']['run_id'])")
echo "RUN_ID=$RUN_ID"

echo "===VERB A (explicit run_id)==="
novetest localization "$RUN_ID" > /tmp/d4-explicit.json

echo "===VERB B (latest)==="
novetest localization latest > /tmp/d4-latest.json

diff /tmp/d4-explicit.json /tmp/d4-latest.json
```

**Expected `diff` output** (verified by Main Branch on merged tip):
```
2c2
<   "command": "localization",
---
>   "command": "localization.latest",
```

That is — **only the top-level `"command"` field differs** (`"localization"` for the explicit-`<run_id>` verb vs `"localization.latest"` for the `latest` verb). Everything else byte-identical, including `derived_at` (findings are persisted on first derive and re-read from disk on subsequent calls).

**What to assert in findings**:
- Both verbs return the SAME `kind`, `mode`, `confidence`,
  `entries[]`, `run_reference`, `derived_at`.
- Only `"command"` field differs (`localization` vs `localization.latest`).
- If `derived_at` differs between calls, document it (would indicate
  re-derive on every read rather than persisted cache).

### Scenario E — Probe whether `--formula` and `--top-n` flags affect output

**Background**: `novetest localization --help` shows `--formula` and
`--top-n` are accepted parameters for BOTH `<run_id>` and `latest`
verbs. Main Branch observed during envelope capture that passing
these flags appears to have NO effect on the output — the persisted
findings file may be read back regardless of flags.

**This scenario is a probe, not an assertion.** Determine empirically
whether the flags work and report. If they don't, file a question for
PM as a potential Defect 5.

**Probe A**: re-rank by Op2 (a different formula than the default Ochiai):
```sh
cd /tmp/d4-cargo
novetest localization latest --formula op2 --top-n 3
```

Look at:
- `formula` field at top level — does it say `"op2"` or `"ochiai"`?
- `entries[0].formula` — does it say `"op2"` or `"ochiai"`?
- `entries[0].score_raw` — for Scenario A's fixture, Op2 score should be `0.25` (not Ochiai's `0.5`).
- `top_n` field — does it say `3` or `10`?
- `entries` length — does the array have 3 entries or 10?
- `alternate_scores_available` — does Op2 disappear from this list (since it's now the primary)? Or does the list stay `["dstar2", "op2", "tarantula"]`?

**Main Branch's observation** (verbatim from dry-run on merged tip):
```
formula: ochiai
top_n: 10
alt_avail: ['dstar2', 'op2', 'tarantula']
entries[0].formula: ochiai
entries[0].score_raw: 0.5
entries count: 1
```

I.e. — **the `--formula op2 --top-n 3` flags appear to be IGNORED**
(output is identical to the default-flags call from Scenario A).
This observation was reproduced on BOTH the `latest` verb AND
the explicit `<run_id>` verb. The persisted findings file
(`<store>/localization/run_<id>/localization_findings.json`) is
read back as-is, ignoring the CLI flags.

**Probe B**: try a few more formulas to triangulate:
```sh
novetest localization latest --formula dstar2 --top-n 1
novetest localization latest --formula tarantula --top-n 5
```

**Probe C**: delete the persisted findings, re-run with explicit flag:
```sh
rm -rf /tmp/d4-cargo/.novetest/store/projects/*/localization/
novetest localization latest --formula op2 --top-n 3
```

If post-delete the flags DO take effect, then the bug is in the
"reuse persisted findings" code path (flags should invalidate the
cache). If post-delete the flags STILL don't take effect, then
the bug is in flag handling at the CLI/orchestration layer.

**What to file**: if flags are ignored, file `agent-comms/findings/`
with the empirical evidence + a request for PM to triage. Don't
prescribe a fix — just document the observed behavior and the
diagnostic data from Probes A/B/C.

### Scenario F — Genuine "unanalyzable" remains unanalyzable

The relaxed gate did NOT remove the unanalyzable case entirely —
it just narrowed it. Verify the gate still rejects runs with NO
failed tests.

**Setup** (passing-only run):
```sh
mkdir -p /tmp/d4-passing && cd /tmp/d4-passing
cat > pyproject.toml <<'PYEOF'
[project]
name = "passing-only"
version = "0.0.1"
requires-python = ">=3.9"
PYEOF
mkdir tests
cat > tests/test_pass.py <<'PYEOF'
def test_one(): assert True
def test_two(): assert True
PYEOF
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run >/dev/null 2>&1   # status=passed (all green)
novetest localization latest
```

**Expected envelope** (verified by Main Branch on merged tip):
```json
{
  "data": {
    "localization_outcome": {
      "kind": "unavailable",
      "reason": "run_not_analyzable",
      "detail": "no analyzable runs in store (1 candidates checked)",
      "run_reference": null
    }
  },
  "ok": true
}
```

This is the new minimal "structurally unanalyzable" case (no
failed tests to localize). If this returns `kind: "fact-set"`,
the gate over-relaxed.

### Scenario G — Empty store probe

**Setup**:
```sh
mkdir -p /tmp/d4-empty && cd /tmp/d4-empty
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null   # NO `novetest run` after init
novetest localization latest
```

**Expected envelope** (verified by Main Branch on merged tip):
```json
{
  "data": {
    "localization_outcome": {
      "kind": "unavailable",
      "reason": "no_run_evidence",
      "detail": "no runs in store",
      "run_reference": null
    }
  },
  "ok": true
}
```

**Load-bearing**: the `reason` literal for empty-store is
`"no_run_evidence"` (distinct from `"run_not_analyzable"` which
Scenario F returns). The `detail` literal is `"no runs in store"`.

### Scenario H — Inspect cross-check + `status.sub_reports.localization` discrepancy

`novetest inspect <run_id>` exposes the `localization_outcome`
inline in its envelope. `novetest status` exposes
`sub_reports.localization` as a per-engine availability marker.
Both should be consistent with the `latest`-verb result.

**Setup** (re-use Scenario A's `/tmp/d4-cargo`):
```sh
cd /tmp/d4-cargo
RUN_ID=$(novetest status 2>/dev/null | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['latest_run_reference']['run_id'])")

echo "===STATUS sub_reports===" && novetest status 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['sub_reports'])"

echo "===INSPECT localization_outcome.kind===" && novetest inspect "$RUN_ID" 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('kind:', d['data']['localization_outcome']['kind'], '| mode:', d['data']['localization_outcome'].get('mode'))"
```

**Main Branch's observation on merged tip** — this is the
discrepancy worth flagging:
```
===STATUS sub_reports===
{'coverage': 'unavailable', 'localization': 'unavailable', 'regression': 'unavailable', 'replay': 'unavailable'}

===INSPECT localization_outcome.kind===
kind: fact-set | mode: sbfl_aggregate
```

I.e. — `novetest status` reports
`sub_reports.localization == "unavailable"` even though `inspect`
AND `localization latest` both return a fact-set for the same run.
This is a cross-verb inconsistency in the post-Defect-4 state —
possibly because `status.sub_reports.coverage` reports `"unavailable"`
too (the `inspect` envelope shows `coverage_outcome.kind: "fact-set"`
with `mapping_granularity: "aggregate"` and `percent_covered: 85.71`,
so coverage facts DO exist on disk for this run).

**This may be Defect 6** — `status.sub_reports.*` reporting is
disconnected from the actual on-disk state. But Main Branch is
NOT investigating further (boundary-respecting per the prior
cycle's process correction). Manual Test should:
1. Confirm the discrepancy reproduces in your run.
2. Probe whether `status.sub_reports.*` is supposed to track
   per-test-availability specifically (pre-Defect-4 semantic) or
   all-modes availability (post-Defect-4).
3. Probe whether `coverage` is similarly mis-reported.
4. File `findings/` (and/or a question for PM) if this looks
   like a real bug.

**Load-bearing for THIS slice's Defect 4 verification**: even
if Defect 6 turns out to be real, it does NOT undermine Defect
4's closure — `localization latest` AND `inspect` both work
post-fix. The discrepancy is in `status`'s reporting surface,
not in the localization derivation itself.

## Critical edge cases worth probing

1. **Mixed-engine store**: init a store, run pytest with
   `--coverage` (per-test path), THEN run cargo aggregate (in a
   sibling subdir if your fixture supports it; or just run two
   different fixtures in sequence in the same `.novetest/` store
   if you can). Verify `localization latest` returns the NEWEST
   analyzable run regardless of mode (resolver is engine-agnostic
   per the relaxed gate).

2. **Tombstoned run**: after a run, tombstone it (if there's a CLI
   for this) or hand-edit the Memory Entry. Verify `latest` skips
   the tombstoned candidate and returns the next-newest analyzable
   one (or `unavailable` if none).

3. **One passing + one failing in same store**: confirm `latest`
   walks past the newest passing-only run (Scenario F's case) to
   the older failing run (Scenario A's case). The integration
   test `test_resolve_latest_walks_past_passing_only_to_first_with_failed_tests`
   pins this at the unit level — confirming end-to-end via CLI
   adds a UX-level guarantee.

4. **Coverage shape transitions**: if a project runs pytest with
   `--coverage` (per-test) and then later without (no-coverage),
   `latest` should return the no-coverage run via failure_proximity
   if it's newer. Worth confirming the resolver doesn't
   "remember" the per-test path.

## What wasn't obvious during merge (Main Branch notes)

- **FF merge was clean** — base commit was exactly `97285e5` (current
  main tip at start of cycle); zero conflicts; gate green pre-merge
  and post-merge (762 + 5 unchanged).

- **The skip-guarded test PASSED on equipped host** — Loc team's
  `test_latest_verb_returns_aggregate_finding_for_cargo_fixture`
  ran the full cargo-llvm-cov flow under pytest and the new gate
  routing worked correctly. Pre-flight §A from the handoff
  ("DEFERRED to Main Branch's equipped-host gate") is now closed
  empirically — both via the integration test AND via the CLI
  smoke pasted in Scenario A.

- **Two mode-specific shape asymmetries surfaced during envelope
  capture** that are NOT regressions from this slice (they
  pre-exist) but become more visible now that all 3 modes are
  reachable through `latest`:
  1. `metadata` shape differs between per-test (`{}`) and
     aggregate/failure_proximity (`{"changed_files_count": 0,
     "regression_reweighted": false}`).
  2. `failure_proximity` emits **absolute** file paths;
     `sbfl_aggregate` and `sbfl_per_test` emit **repo-relative**
     paths.

  Both are flagged in their respective scenarios (B and C) for
  Manual Test to escalate via findings if normalization is
  warranted.

- **Two POTENTIAL orthogonal defects surfaced during dry-run** (Main
  Branch is logging the observations but NOT investigating further
  per the prior cycle's process correction — these are Manual Test
  exploratory territory):
  1. **Possible Defect 5** — `--formula <name>` and `--top-n <N>`
     flags appear to be silently ignored on BOTH `localization
     <run_id>` and `localization latest` verbs (Scenario E in this
     doc). Probably because the persisted findings file is read
     as-is. Worth Manual Test confirming and triangulating before
     filing for PM triage.
  2. **Possible Defect 6** — `novetest status` reports
     `sub_reports.localization == "unavailable"` even when
     `localization latest` AND `inspect` both return a fact-set
     for the same run (Scenario H in this doc). Possibly stems from
     `status.sub_reports.*` being disconnected from on-disk state.
     Same — Manual Test exploratory territory.

  These observations are exposed by the new "all 3 modes reachable
  through `latest`" surface that this slice opened up. They were
  not visible pre-Defect-4 because the per-test-only gate prevented
  reaching them.

## End-of-work

- Commit hash for the merged Loc Defect 4 fix-up: **`4b5fd1d`**.
- Source handoff: `agent-comms/handoffs/localization-team-2026-06-01-latest-aggregate-discovery-defect4.md`.
- Source task: `agent-comms/tasks/localization-team-2026-06-01-latest-aggregate-discovery-defect4.md`.
- After Manual Test files findings, PM can close the long-running
  Phase 4 §4 modes-related work narrative (this is the LAST
  open piece per the task brief) — pending any Defect 5 / Defect 6
  follow-up triage.
