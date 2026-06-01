---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-06-01
slug: localization-cache-rederive-defect5
merged_commit: 4895847
source_handoffs:
  - agent-comms/handoffs/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md
source_tasks:
  - agent-comms/tasks/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md
related:
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
  - agent-comms/decisions/2026-05-30-localization-outcome-envelope-shape.md
  - src/novetest/cli/app.py
  - src/novetest/localization/derive.py
---

# Verification: Defect 5 closed — `localization` cache re-derives on explicit-flag mismatch

## Merged commit + summary

**Merged at**: `4895847` (FF from `0ed8fe4`; single-commit slice).

Pre-fix, `novetest localization <run_id> --formula X --top-n N` (and
`localization latest --formula X --top-n N`) silently dropped the
explicit flags whenever a `localization_findings.json` cache file
already existed for the run. The cache-read path returned the
persisted findings verbatim regardless of caller flags; only the
2026-05-30 `localization-cache-args-ignored` warning disclosed the
silent ignore — the actual data was still wrong.

Post-fix, the CLI handler implements a **peek-after-call rederive
pattern**: when the engine returns a `LocalizationFinding` whose
`formula` / `top_n` differ from the user's *explicit* request (a flag
the caller actually passed), the handler unlinks the on-disk cache,
re-invokes `derive_localization_findings` at the requested flags,
persists the fresh result, and emits a new
`localization-cache-rederived` warning carrying the previous AND
requested args plus the cache path (audit signal for AI agents
iterating on formulas).

Engine API (`derive_localization_findings`) is UNCHANGED — cache
invalidation policy lives entirely in the CLI handler. Cached-read
behavior when no explicit flags differ is UNCHANGED (regression-pin
via Loc team's `test_localization_run_no_warning_when_request_matches_cache`).

**Net surface**: 2 src files modified (`cli/app.py` + `derive.py`
docstring; ZERO new src files; count stays at 72), 3 test files
overhauled in-place (Net test count delta: 0 — existing 6+3+1 cache
tests rewritten to pin the new contract).

**Test counts** (equipped host, cargo on PATH):
- Pre-merge gate on worktree: **762 + 5** (baseline + 0)
- Post-merge gate on main: **776 + 5** (= 762 + 14 from Orch Defect 6 sibling slice that landed in the same cycle; D5 contributes 0 net test count)
- mypy `--strict`: **Success: no issues found in 72 source files**

## Source handoffs consumed

1. `agent-comms/handoffs/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md` — single handoff for the single-commit slice.

## What to verify (6 scenarios for Manual Test)

> **Note for Manual Test**: All envelope paths + JSON field literals
> in this doc were verified by Main Branch dry-running each scenario
> against the merged tip (`4895847`) — `run_id`s and timestamps
> differ in your run, but the SHAPE + load-bearing fields match.

### Scenario A — Canonical 3-step re-derive sequence

This is the load-bearing Defect 5 closure proof. The verbatim
envelope below was captured from the merged tip; please reproduce
and confirm the same shape.

**Setup**:
```sh
. "$HOME/.cargo/env"
cp -r tests/fixtures/projects/localization-aggregate-only /tmp/d5-cargo
cd /tmp/d5-cargo
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run --coverage >/dev/null 2>&1
```

**Step 1 — bake defaults**:
```sh
novetest localization latest
```

Expected (load-bearing fields):
```
formula: ochiai
top_n: 10
entries[0].score_raw: 0.5         # Ochiai math: 1/sqrt((1+0)*(1+3)) = 0.5
warnings: []                       # no warning on first derive
```

**Step 2 — explicit `--formula op2 --top-n 3`**:
```sh
novetest localization latest --formula op2 --top-n 3
```

Expected load-bearing envelope (verbatim shape from merged tip):
```json
{
  "command": "localization.latest",
  "data": {
    "localization_outcome": {
      "kind": "fact-set",
      "mode": "sbfl_aggregate",
      "confidence": "medium",
      "formula": "op2",
      "top_n": 3,
      "alternate_scores_available": ["dstar2", "ochiai", "tarantula"],
      "entries": [
        {
          "rank": 1,
          "formula": "op2",
          "score_raw": 0.25,
          "code_location": {"file": "src/arithmetic.rs", "primary_line": 53, ...},
          "alternate_scores": {
            "dstar2": 0.3333333333333333,
            "ochiai": 0.5,
            "tarantula": 0.5
          }
        }
      ]
    }
  },
  "warnings": [
    {
      "code": "localization-cache-rederived",
      "details": {
        "cache_path": ".novetest/localization/findings/run_<RUN_ID>/localization_findings.json",
        "previous": {"formula": "ochiai", "top_n": 10},
        "requested": {
          "formula": "op2",
          "top_n": 3,
          "formula_explicit": true,
          "top_n_explicit": true
        }
      },
      "message": "cached findings (--formula='ochiai' --top-n=10) were re-derived at requested --formula='op2' --top-n=3; cache overwritten at <path>"
    }
  ]
}
```

**What to assert**:
- Top-level `formula == "op2"`, `top_n == 3` (flags APPLIED — not the cached defaults)
- `entries[0].formula == "op2"`, `entries[0].score_raw == 0.25`
- `alternate_scores_available` no longer contains `"op2"` (it's the primary now); does contain `["dstar2", "ochiai", "tarantula"]`
- Exactly ONE warning with `code: "localization-cache-rederived"`
- Warning `details.previous == {"formula": "ochiai", "top_n": 10}` (carries the OLD cached values for audit)
- Warning `details.requested.formula_explicit == true` AND `requested.top_n_explicit == true`
- Warning `details.cache_path` matches `.novetest/localization/findings/run_<RUN_ID>/localization_findings.json`

**Step 3 — re-run defaults; verify cache now holds op2/3**:
```sh
novetest localization latest
```

Expected:
```
formula: op2                      # ← cache now holds op2/3 from Step 2's re-derive
top_n: 3
entries[0].score_raw: 0.25
warnings: []                       # no warning — defaults didn't trigger mismatch
```

**What to assert**:
- `formula == "op2"` (cache-as-source-of-truth post-rederive; subsequent defaulted calls correctly serve op2/3, NOT ochiai/10)
- No warning (cache is consistent with the implicit defaults of the second-call surface — there's nothing to re-derive)

### Scenario B — Cache-hit no-flags regression-pin (defaults stay cached)

This pins the unchanged behavior — without explicit flags, the cache
is read verbatim with no re-derive cost.

**Setup**: re-use Scenario A's `/tmp/d5-cargo` (cache now holds
op2/3 from Scenario A's Step 2).

**Probe**:
```sh
for i in 1 2 3; do
  novetest localization latest > /dev/null
done
ls -la .novetest/localization/findings/run_*/localization_findings.json
# mtime should NOT change across the 3 calls (cache reuse, no re-derive)
```

Then check the envelope:
```sh
novetest localization latest 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('warnings:', d['warnings'])"
```

**What to assert**:
- `warnings == []` (no re-derive triggered)
- `.localization_findings.json` mtime unchanged across the 3 calls
- `formula == "op2"`, `top_n == 3` (whatever Scenario A left in the cache)

### Scenario C — Cache-hit same-flags regression-pin (explicit-but-matches → no re-derive)

This pins the "explicit but matches cache" path — even when the user
passes flags, if they MATCH the cached state, no re-derive happens.

**Setup**: Scenario A's cache holds op2/3. Pass the same flags
explicitly.

**Probe**:
```sh
novetest localization latest --formula op2 --top-n 3 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('warnings:', d['warnings'])"
ls -la .novetest/localization/findings/run_*/localization_findings.json
```

**What to assert**:
- `warnings == []` (no `localization-cache-rederived` — values matched)
- File mtime unchanged from prior call
- `formula == "op2"`, `top_n == 3` (unchanged)

### Scenario D — Multiple sequential formula flips

Verify the cache flips correctly across multiple re-derives, with
audit warnings each time.

**Setup**: re-use Scenario A's `/tmp/d5-cargo`.

**Probe sequence**:
```sh
echo "===Flip 1: op2/3 → dstar2/5===" && novetest localization latest --formula dstar2 --top-n 5 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('formula:', d['data']['localization_outcome']['formula'], '| top_n:', d['data']['localization_outcome']['top_n'], '| previous:', d['warnings'][0]['details']['previous'])"

echo "===Flip 2: dstar2/5 → tarantula/2===" && novetest localization latest --formula tarantula --top-n 2 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('formula:', d['data']['localization_outcome']['formula'], '| top_n:', d['data']['localization_outcome']['top_n'], '| previous:', d['warnings'][0]['details']['previous'])"

echo "===Flip 3: tarantula/2 → ochiai/10===" && novetest localization latest --formula ochiai --top-n 10 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('formula:', d['data']['localization_outcome']['formula'], '| top_n:', d['data']['localization_outcome']['top_n'], '| previous:', d['warnings'][0]['details']['previous'])"
```

**What to assert**:
- Each flip produces a warning with `previous` matching the prior flip's `requested`
- The cache's `formula` / `top_n` is what was MOST RECENTLY requested
- No accumulated state pollution (each flip is clean)

### Scenario E — Explicit-run verb (not just `latest`)

Confirm the fix applies to BOTH verbs: `localization <run_id>` AND
`localization latest`.

**Setup**: re-use Scenario A's `/tmp/d5-cargo`.

**Probe**:
```sh
RUN_ID=$(novetest status 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['latest_run_reference']['run_id'])")

# Reset cache to a known baseline
rm -rf .novetest/localization
novetest localization "$RUN_ID" > /dev/null   # bake ochiai/10

# Explicit-run verb with flag mismatch
novetest localization "$RUN_ID" --formula op2 --top-n 3 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('command:', d['command']); print('formula:', d['data']['localization_outcome']['formula']); print('warnings:', d['warnings'][0]['code'] if d['warnings'] else [])"
```

**What to assert**:
- `command == "localization"` (NOT `"localization.latest"` — explicit-run verb)
- `formula == "op2"` (re-derive happened)
- `warnings[0].code == "localization-cache-rederived"`

This proves the fix is symmetric across both verbs (per Loc team's
handoff: same `_rederive_if_cache_overrode_flags` helper is invoked
from both `localization_run` and `localization_latest`).

### Scenario F — Persistence check (on-disk findings file matches envelope)

After a re-derive, the on-disk `localization_findings.json` should
reflect the NEW state (not the pre-rederive cached state).

**Setup**: re-use Scenario A's `/tmp/d5-cargo`. Reset to known baseline.

**Probe**:
```sh
rm -rf .novetest/localization
novetest localization latest > /dev/null   # ochiai/10 baked

# Re-derive
novetest localization latest --formula op2 --top-n 3 > /dev/null

# On-disk file should reflect op2/3
cat .novetest/localization/findings/run_*/localization_findings.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('on-disk formula:', d['formula']); print('on-disk top_n:', d['top_n']); print('on-disk entries count:', len(d['entries']))"
```

**What to assert**:
- On-disk `formula == "op2"` (matches re-derived envelope)
- On-disk `top_n == 3` (matches re-derived envelope)
- On-disk `len(entries) == 1` (matches re-derived envelope's truncation)

## Critical edge cases worth probing

1. **Failure_proximity mode re-derive**: Scenarios A–F all use cargo
   aggregate (`sbfl_aggregate` mode). Confirm the same re-derive
   policy fires for `failure_proximity` mode too — use the
   `localization-no-coverage` fixture. (Per Loc team's gotcha:
   `failure_proximity` reuses `formula="ochiai"` as a placeholder
   even though it doesn't compute alternates; if `--formula op2 --top-n 3`
   is passed there, what happens? Possibly the re-derive triggers
   and produces op2 entries for failure_proximity. Or possibly the
   mode dispatcher overrides the formula. Worth empirically pinning.)

2. **One flag explicit, one flag implicit**: e.g., `--formula op2`
   alone (no `--top-n`). Does the cache re-derive at `op2` with
   `top_n` taken from cached value? Or does it re-derive at `op2`
   with the new default `top_n=10`? Captured warning's
   `details.requested` should show `formula_explicit: true`,
   `top_n_explicit: false` — which is the test of whether the
   implementation distinguishes "default-equals-cached" from
   "default-differs-from-cached".

3. **Concurrent re-derive**: two processes running
   `novetest localization latest --formula <different> --top-n <different>`
   simultaneously against the same cache. Should be cleanly
   serialized by file-system atomicity, but worth noting if your
   test environment can simulate it.

4. **mtime regression-pin via repeated re-derive**: re-running
   the SAME explicit re-derive twice (e.g., `--formula op2 --top-n 3`
   twice in a row after Scenario A's Step 3) should fire a warning
   on the FIRST call (cache was ochiai/10 from Step 1's bake; first
   call flips to op2/3) but the SECOND call should NOT fire (cache
   is now op2/3, matches request). Verify the SECOND call's
   `warnings == []`.

## What wasn't obvious during merge (Main Branch notes)

- **WORKLOG.md conflict on rebase** — Loc Defect 5 merged first (FF
  from `0ed8fe4`); Orch Defect 6's rebase produced a WORKLOG conflict
  resolved surgically with the established "incoming-on-top"
  convention (Orch entry above Loc entry in WORKLOG). Verified clean
  via post-rebase gate.

- **Loc team's `derived_at` quirk worth re-confirming** — my prior
  cycle's Scenario D probe showed `derived_at` is byte-identical
  between explicit `<run_id>` and `latest` verbs on the SAME run
  (proving cache-read, not re-derive). Post-Defect-5, the re-derive
  path WILL update `derived_at` on the new findings file. So
  Manual Test should expect `derived_at` to change ONLY on
  re-derive (mismatch + explicit), NOT on cache-hit read-back.

- **Warning schema is in a freeze decision** — Loc team's open
  question 1 in the handoff: the previous `localization-cache-args-ignored`
  code is pinned in `decisions/2026-05-30-localization-outcome-envelope-shape.md`
  §"Cache-vs-request mismatch warning". Post-fix the code is
  `localization-cache-rederived` and the details schema differs
  (`previous` vs `cached`). PM may amend or supersede that decision;
  not blocking. Manual Test's findings should pin the NEW code
  literal so PM has a canonical reference.

- **Engine API stays minimal** — per Loc team's design choice, the
  cache-invalidation policy lives in `cli/app.py`. A future Replay /
  Orchestration caller that invokes `derive_localization_findings`
  directly will NOT get the auto-invalidation for free (per
  `derive.py` docstring's new paragraph). Worth flagging if Manual
  Test probes any non-CLI path that exercises the engine.

## End-of-work

- Commit hash for the merged Loc Defect 5 fix: **`4895847`**.
- Source handoff: `agent-comms/handoffs/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md`.
- Source task: `agent-comms/tasks/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md`.
- Sibling slice in the same cycle: Defect 6 — see
  `agent-comms/verifications/2026-06-01-status-sub-reports-staleness-defect6.md`.
