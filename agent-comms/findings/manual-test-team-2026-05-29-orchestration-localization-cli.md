---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
slug: orchestration-localization-cli
created: 2026-05-29
verdict: passed
related:
  - agent-comms/verifications/2026-05-29-orchestration-localization-cli.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
---

# Findings: Localization CLI slice (Phase 4 §4)

## Verdict

**passed** — every wire shape pinned by the verification doc was
reproduced verbatim. The `localization_outcome` envelope projects the
engine's 12/9/6/3-key fact-set shape, plus the 4-key unavailable
shape, across all three CLI surfaces (`localization <run_id>`,
`localization latest`, `inspect <run_id>`). Cache short-circuit on
new-flags-after-derive behaves as the docstring documents (silently
ignores re-passed flags, returns cached finding with original
`derived_at`). Five of the six `REASON_*` paths fire as expected, with
**one wire-shape divergence** vs the verification doc on the sixth
path (bogus run_id ULID surfaces an envelope-level `not-found` error,
NOT a `localization_outcome.unavailable` with `reason="no_run_evidence"`
as the verification doc predicted). That divergence is noted in §
Issues as an observation, not a regression — it's product behavior,
not a verification failure.

Net read for the CEO: the Localization CLI is shippable. The
discriminator-based envelope contract holds. Consumers can branch on
`data.localization_outcome.kind ∈ {"fact-set", "unavailable"}` and
trust the shapes underneath. The cache-as-source-of-truth semantics
are the single subtlety worth communicating to downstream users.

## What was tested

All 7 verification steps executed:

1. End-to-end `run --coverage` → `localization <run_id>` →
   `localization latest` → `inspect <run_id>` happy path. ✓
2. Flag validation: `--formula bogus` and `--top-n {0,-5}` against
   BOTH `<run_id>` and `latest` verb. ✓
3. Fresh-derive cache-miss path with non-default flags
   (`--formula dstar2 --top-n 3`). ✓
4. Cache-hit ignores re-passed flags (the critical UX subtlety). ✓
5. All 5 `REASON_*` unavailable paths exercised individually. ✓
   (the 6th, `run_not_analyzable`, was flagged in the verification doc
   itself as "less critical to probe" since it requires hand-
   tombstoning — skipped per that guidance.)
6. `inspect` cache-only contract: confirms `inspect` does NOT derive
   on miss; state flips after explicit `localization` call. ✓
7. `derived_at` preservation across cache hits. ✓

Beyond the verification doc, three Critical-edge-cases probes were
explicitly verified:

- Discriminator-position invariance: `kind` lives at
  `data.localization_outcome.kind` and at the same position in the
  12-key dict across all 3 CLI surfaces. ✓
- Entry-level field absences: `evidence_lines` (at entry top) and
  `schema_version` are absent across ALL 10 entries in the fact-set
  (not just rank-1). Top-level `primary_formula` is absent. ✓
- `alternate_scores_available` invariance: for each of the 4
  primary formulas (ochiai, dstar2, op2, tarantula), the list is
  always 3 strings, alphabetically sorted, primary excluded. ✓

## Test-gate baseline

```
$ uv run pytest -q tests/unit tests/integration
... 667 passed, 5 skipped in 18.19s

$ uv run mypy
Success: no issues found in 70 source files (strict)
```

Matches the verification doc verbatim.

## Commands run + observed output

### Step 1 — End-to-end fact-set projection

```bash
PROBE=/tmp/novetest-manual-localization
rm -rf "$PROBE" && mkdir -p "$PROBE"
cp -r .../tests/fixtures/projects/localization-branch "$PROBE/sut"
cd "$PROBE/sut"

novetest init --output json                    # store_state=ready
novetest run --coverage --output json          # status=failed, summary 1 failed / 5 passed / 6 total
RUN_ID=01KSS83TJH4HXXBE7CRF7FGPXN
novetest localization "$RUN_ID" --output json
```

`localization_outcome` shape — exactly 12 top-level keys (sorted):

```
alternate_scores_available, confidence, derived_at, ecosystem,
engine_name, entries, formula, kind, metadata, mode, run_reference,
top_n
```

Values:

```
kind:        "fact-set"
formula:     "ochiai"
top_n:       10
mode:        "sbfl_per_test"
confidence:  "high"
ecosystem:   "python"     ← echoes Run's native ecosystem, NOT localization-engine's
engine_name: "pytest"     ← same
alternate_scores_available: ["dstar2", "op2", "tarantula"]
entries:     10 elements
schema_version key present? NO
primary_formula key present? NO
```

Rank-1 entry — 9 keys (sorted):

```
alternate_scores, code_location, evidence_citations, formula, rank,
related_failed_tests, score_normalized, score_raw, tied_with
```

```
rank:        1
symbol:      divide
score_raw:   1.0
formula:     ochiai      ← entry-level repeat of top-level primary
related_failed_tests: ["tests/test_calculator.py::test_divide_yields_quotient"]
alternate_scores:     {"dstar2": 0.0, "op2": 1.0, "tarantula": 1.0}
tied_with:   ["entry_index_1"]
entry has top-level evidence_lines? NO
entry has schema_version? NO
```

`code_location` — 6 keys (sorted):

```
evidence_lines, file, kind, line_range, primary_line, symbol
```

```
{"evidence_lines": [34],
 "file": "localization_branch/calculator.py",
 "kind": "symbol",
 "line_range": [31, 34],
 "primary_line": 34,
 "symbol": "divide"}
```

`evidence_citations[0]` (the test_result citation) — 3 keys:

```
{"kind": "test_result",
 "run_reference": {"created_at": 1780037577297, "run_id": "01KSS83TJH4HXXBE7CRF7FGPXN", "schema_version": 1},
 "selector": {"outcome": "failed", "test_id": "tests/test_calculator.py::test_divide_yields_quotient"}}
```

`evidence_citations[1]` (the coverage_fact citation):

```
{"kind": "coverage_fact", "run_reference": {...}, "selector": {"file": "localization_branch/calculator.py", "lines": [34]}}
```

All ten entries' (rank, symbol, file, score_raw) for the record:

| rank | symbol | file | score_raw | tied_with size |
|---|---|---|---|---|
| 1 | divide | localization_branch/calculator.py | 1.0 | 1 |
| 1 | test_divide_yields_quotient | tests/test_calculator.py | 1.0 | 1 |
| 2 | add | localization_branch/calculator.py | 0.0 | 7 |
| 2 | subtract | localization_branch/calculator.py | 0.0 | 7 |
| 2 | multiply | localization_branch/calculator.py | 0.0 | 7 |
| 2 | negate | localization_branch/calculator.py | 0.0 | 7 |
| 2 | Counter.__init__ | localization_branch/calculator.py | 0.0 | 7 |
| 2 | Counter.increment | localization_branch/calculator.py | 0.0 | 7 |
| 2 | test_add_sums_two_numbers | tests/test_calculator.py | 0.0 | 7 |
| 2 | test_subtract_yields_difference | tests/test_calculator.py | 0.0 | 7 |

**Carryover observation from the 2026-05-28 cycle**: rank-1 is a tie
between `divide` (the actual bug) and `test_divide_yields_quotient`
(the test function that detected the bug). Three of ten top entries
are test code. This is the same design call previously flagged for
PM/CEO — the CLI slice does not surface it differently, and the
verification doc did not ask for a re-resolution. Re-flagging in
case it hadn't been resolved by this slice's merge.

```bash
novetest localization latest --output json
# Envelope: command="localization.latest", ok=true,
# data.localization_outcome.kind="fact-set", same 12-key shape, same run_reference.run_id

novetest inspect "$RUN_ID" --output json
# Envelope: command="inspect", ok=true
# data top-level keys: ["coverage_outcome", "localization_outcome", "regression_outcome", "run_reference", "run_summary", "sub_reports"]
# data.sub_reports = {"coverage": "available", "localization": "available", "regression": "unavailable", "replay": "unavailable"}
# data.localization_outcome.kind = "fact-set" (12-key shape identical)
```

### Step 2 — Flag-validation invariants

All four cases exit 2 with code "invalid-flag" and the verification
doc's exact message strings:

```
$ novetest localization 01ABCDEFGHIJK --formula bogus --output json
EXIT=2  ok=false
errors[0] = {"code":"invalid-flag", "message":"Invalid --formula='bogus'; expected one of ['dstar2', 'ochiai', 'op2', 'tarantula']", "details":{}}

$ novetest localization 01ABCDEFGHIJK --top-n 0 --output json
EXIT=2  errors[0].message = "Invalid --top-n=0; expected a positive integer"

$ novetest localization latest --formula bogus --output json
EXIT=2  same shape as above (latest verb also validates flags first)

$ novetest localization latest --top-n -5 --output json
EXIT=2  errors[0].message = "Invalid --top-n=-5; expected a positive integer"
```

Note that all four use a clearly-fictitious run_id (`01ABCDEFGHIJK`)
that does NOT exist in any store; they STILL exit 2 `invalid-flag`,
not a downstream `not-found`. This confirms the verification doc's
claim that "Flag validation runs BEFORE run resolution".

### Step 3 — Fresh-derive cache-miss with non-default flags

Fresh fixture, no prior derive:

```bash
novetest localization "$RUN_ID" --formula dstar2 --top-n 3 --output json
# data.localization_outcome:
#   formula = "dstar2"   ← honored
#   top_n = 3            ← honored
#   alternate_scores_available = ["ochiai", "op2", "tarantula"]   ← ochiai moved here because dstar2 is now primary
#   entries.length = 3
```

Rank-1 under dstar2 in this fixture is `add` (score 0.0), NOT
`divide`. This is correct behavior — `divide` gets a dstar2 score of
0.0 (because the dstar2 formula penalizes failures-in-covered-by-
passing-tests, and `divide` is also exercised by passing tests), so it
ties with other zero-score symbols and alphabetical ordering puts
`add` first. The verification doc forecast this exact behavior
("Top-1 under dstar2 in this fixture is `add` (not `divide`) —
formulas pick different culprits"). Match.

### Step 4 — Cache-hit silently ignores re-passed flags

Continuing on the SAME RUN_ID that just had dstar2/3 derived:

```bash
novetest localization "$RUN_ID" --formula ochiai --top-n 10 --output json
# data.localization_outcome:
#   formula = "dstar2"   ← NOT ochiai, even though --formula ochiai was passed
#   top_n = 3            ← NOT 10, even though --top-n 10 was passed
#   entries.length = 3   ← cached payload, unchanged
#   alternate_scores_available = ["ochiai", "op2", "tarantula"]   ← still dstar2-as-primary
```

This is the design's documented behavior (`derive_localization_findings`
docstring: "this slice does NOT auto-invalidate"). It is silent and
non-warning — no `warnings[]` entry surfaces. **PM design call**: is
the silent-ignore acceptable v1 UX, or should the CLI emit a warning
when it detects a cache-hit response that doesn't match the
explicitly-passed `--formula` / `--top-n`? My recommendation is at the
end of this file. Recording the observation here, not blocking the
verdict.

### Step 5 — All 5 `REASON_*` unavailable paths

```
| Reason                  | Probe                                        | result                                                                                    |
| no_failed_tests         | `run` all-passing pytest-coverage fixture    | unavailable, reason=no_failed_tests, detail="run has no failed test results"              |
| no_coverage             | `run` WITHOUT --coverage on failing fixture  | unavailable, reason=no_coverage, detail="coverage facts unavailable; failure_proximity mode is not yet implemented (Phase 4 follow-up)" |
| missing_derived_facts   | `inspect` BEFORE any explicit localization   | unavailable, reason=missing_derived_facts, detail="findings not yet derived"              |
| no_run_evidence (latest)| `localization latest` on empty store         | unavailable, reason=no_run_evidence, detail="no runs in store", run_reference=null        |
| no_run_evidence (specific)| `localization <bogus_ulid>` against any store | DOES NOT FIRE — see Issues §1 below                                                       |
| run_not_analyzable      | (skipped per verification doc guidance)      | not probed                                                                                |
```

For all 5 paths that DID produce a `localization_outcome.unavailable`
projection, the 4-key shape `{kind, reason, detail, run_reference}` is
respected verbatim. Envelope `ok` is `true` (unavailable is a
structured response, not an error). `run_reference` is populated when
the run is known, `null` only on `latest` against empty store.

### Step 6 — `inspect` cache-only contract

```bash
# Fresh fixture, fresh store, fresh run:
novetest run --coverage > runout.json   # RUN_ID stashed
novetest inspect "$RUN_ID" --output json
# sub_reports.localization = "unavailable"
# data.localization_outcome = {kind: "unavailable", reason: "missing_derived_facts", detail: "findings not yet derived", run_reference: {...}}

novetest localization "$RUN_ID" --output json > /dev/null   # forces derive
novetest inspect "$RUN_ID" --output json
# sub_reports.localization = "available"
# data.localization_outcome = {kind: "fact-set", formula: "ochiai", top_n: 10, ...12 keys...}
```

Confirmed: `inspect` does NOT derive on miss (the
`missing_derived_facts` state persists across multiple `inspect` calls
against the same run); only an explicit `localization` call flips the
cache. State-mutating-via-inspect is NOT happening. ✓

### Step 7 — `derived_at` preservation

From Step 4's transcript:

```
derived_at on initial dstar2/3 derive:        1780037784749
derived_at on subsequent cache-hit call:       1780037784749
EQUAL? True
```

Cache-hits do NOT bump `derived_at`. The original derive's timestamp
is the canonical timestamp of the cached payload. ✓

### Critical edge cases (additional probes)

**Discriminator-position invariance** across all 3 CLI surfaces.
`data.localization_outcome.kind = "fact-set"` at the same nesting
depth, and the surrounding 12-key shape is identical in all three
envelopes:

```
localization <run_id>:    command="localization",         keys = 12, sorted = [...]
localization latest:       command="localization.latest",  keys = 12, sorted = [...]
inspect <run_id>:          command="inspect",              keys = 12, sorted = [...]
```

The 12-key sorted list is byte-for-byte identical across the three.
Only `command` varies. ✓

**Entry-level field absences across ALL 10 entries** (not just rank-1):

```
- entry-top `evidence_lines`: absent on all 10 entries ✓
- entry-top `schema_version`: absent on all 10 entries ✓
- top-level `primary_formula`: absent on the fact-set ✓
- top-level `schema_version`: absent on the fact-set ✓ (stripped by CLI projection)
```

**`alternate_scores_available` invariance across all 4 formulas:**

| primary formula | alternate_scores_available | type | len | sorted? | primary excluded? |
| ochiai          | ["dstar2","op2","tarantula"]   | list | 3 | yes | yes |
| dstar2          | ["ochiai","op2","tarantula"]    | list | 3 | yes | yes |
| op2             | ["dstar2","ochiai","tarantula"] | list | 3 | yes | yes |
| tarantula       | ["dstar2","ochiai","op2"]       | list | 3 | yes | yes |

All four runs were on independent fresh stores (one fixture copy per
formula) to avoid the cache silent-ignore behavior from Step 4.

## Issues found

**1. Wire-shape divergence: bogus run_id → `not-found` envelope, NOT
`localization_outcome.unavailable` with reason="no_run_evidence".**

The verification doc §5 listed:

> | `no_run_evidence` | `localization 01FAKEFAKEFAKEFAKEFAKEFAKE` against an empty store (no such run). |

Observed behavior:

```bash
$ novetest localization 01FAKEFAKEFAKEFAKEFAKEFAKE --output json
EXIT=2
{
  "command": "localization",
  "data": {},
  "errors": [
    {
      "code": "not-found",
      "details": {},
      "message": "No Memory Entry for run_id='01FAKEFAKEFAKEFAKEFAKEFAKE'"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

The CLI's run-resolution layer pre-empts localization with a
`not-found` envelope error (exit 2) — `data.localization_outcome` is
NOT projected when the underlying Memory Entry does not exist. The
`no_run_evidence` reason fires ONLY when the run IS resolvable but
lacks the expected upstream evidence — and on the `latest` verb when
the store is empty (run_reference: null path).

This is a verification-doc text drift, not a product defect — the
behavior of pre-empting with `not-found` is reasonable and consistent
with the inspect / coverage / regression verbs' surface contracts.
Two possible PM resolutions:

- **A. Leave the product alone**, correct the verification doc and
  any downstream specs to clarify that "bogus run_id" → `not-found`
  envelope error, NOT a `localization_outcome.unavailable`. Update the
  `REASON_*` enum docs to clarify that `no_run_evidence` only fires
  for `latest` empty-store and same-store-but-no-test-evidence cases.
- **B. Change the product** to project an `unavailable` outcome with
  `reason="no_run_evidence"` and `run_reference={"run_id":
  "01FAKEFAKEFAKEFAKEFAKEFAKE", ...}` even when the run does NOT exist.
  This would require the run-resolution layer to invent a synthetic
  run_reference for non-existent IDs — semantically muddier.

My recommendation: **A** (correct the doc). The current product
behavior is cleaner — the `not-found` error code is more useful to
consumers than a structurally-conformant-but-misleading unavailable
outcome.

**2. Cache-hit silently ignores re-passed flags (Step 4) — PM UX
call, not a defect.**

The engine's documented behavior is correct. The question is whether
the CLI should add a warning when it detects this case. Three
options:

- **A. Status quo**: silent ignore. UX risk: a consumer passes
  `--formula op2 --top-n 50` expecting a fresh derive, gets the
  cached `--formula ochiai --top-n 10` result, and may not notice
  unless they read the response payload carefully. Hidden surprises
  compound.
- **B. Emit a `warnings[]` entry** when the requested `--formula` /
  `--top-n` differs from the cached values. Warning text could be
  "requested --formula='op2' --top-n=50 but cached findings were
  derived with --formula='ochiai' --top-n=10; delete cache and re-run
  to override". This is forward-compatible and zero-cost to consumers
  who already check `warnings[]`.
- **C. Add a `--refresh` flag** that invalidates the cache and
  re-derives. Bigger surface change; the verification doc explicitly
  notes "this slice does NOT auto-invalidate", suggesting a refresh
  mechanism is a separate slice.

My recommendation: **B** (warnings). Cheap, additive, and turns the
silent surprise into a discoverable signal. C is a natural follow-up
slice but not blocking. A is shippable as-is if PM judges the cache
discipline is on consumers.

**3. No-coverage detail message references "Phase 4 follow-up".**

The `no_coverage` detail is "coverage facts unavailable;
failure_proximity mode is not yet implemented (Phase 4 follow-up)".
This is correct prose but ties the user-facing message to a project
phase identifier. If the failure_proximity mode lands in a future
slice, this message will need updating. Trivial — flag for the PM's
mental model only.

## Recommendations for PM

1. **Resolve the bogus-run_id-shape divergence (Issue §1)** by
   correcting the verification doc (option A above). Optionally
   document the actual `REASON_*` semantics in the `decisions/`
   localization-outcome-envelope-shape freeze that the verification
   doc anticipates ("After Manual Test fields it, PM freezes via
   `decisions/2026-05-XX-localization-outcome-envelope-shape.md`").

2. **Pick a posture on cache silent-ignore (Issue §2)** before
   freezing the envelope shape. The recommended `warnings[]` emission
   (option B) is forward-compatible — it can be added without
   breaking the wire shape.

3. **Re-flag the test-code-as-suspect observation from 2026-05-28**
   to the CEO. This slice does not change the behavior; the SBFL
   output still includes test code as rank-1-tied suspects. If a
   resolution was made between cycles and I missed it, ignore this
   note. If not, the CLI-level visibility of the issue (consumer-
   facing rank-1 tie includes `test_divide_yields_quotient`) makes
   the design call more urgent.

4. **No code-change recommendations**. Everything the verification
   doc requested behaved correctly per the engine + freeze docs.

## Process notes

- `jq` is not installed; all JSON inspection via `python3 -c "import
  json; ..."`.
- The `Write` tool tripped the worktree-isolation guard mid-session;
  both findings files use the sanctioned Bash heredoc fallback
  (GOTCHAS.md).
- One transient Bash classifier outage ("claude-opus-4-7 is
  temporarily unavailable") was retried in place and succeeded
  immediately. No impact on findings.
- All probes used independent fresh stores under `/tmp/novetest-
  manual-*` to avoid cache leakage between scenarios.
