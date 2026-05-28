---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-28
slug: localization-phase4-entry
related:
  - agent-comms/verifications/2026-05-28-localization-phase4-entry.md
  - agent-comms/verifications/2026-05-28-run-gotest-adapter.md
  - agent-comms/handoffs/localization-team-2026-05-28-phase4-entry.md
  - design/implementation-plan/localization-strategy.md
  - design/interace-contract/localization.md
---

# Findings: Phase 4 entry — Localization engine (per-test SBFL path)

## Verdict

**passed**

The Phase 4 Localization engine produces the documented JSON shape on disk, the 12-key `LocalizationFinding` / 9-key `LocalizationEntry` / 6-key `CodeLocation` / 3-key `EvidenceCitation` shapes all match the design verbatim, all four `LocalizationUnavailable` reason codes fire correctly in their target conditions, the cache short-circuit preserves `derived_at`, the Memory `has_localization_findings` availability flag flips correctly, and `check_localization_availability` accurately distinguishes derivable from non-derivable runs.

I am, however, surfacing **one product-design surprise from the fixture run** that the verification explicitly asked me to report: the rank-1 tied entry at index 1 is **the failing test function itself**, not another production symbol. See "Critical observation" below — this is a PM/CEO decision, not a code defect.

## What I tested (for the CEO)

The Localization engine takes the question "which line of code is most likely to be buggy when this test fails?" and answers it using a classic spectrum-based fault localization (SBFL) calculation. Phase 4 entry ships the engine layer (no CLI verb yet — same pre-CLI pattern as the Regression engine).

I exercised:

1. **The happy path** — given a real run on a fixture where `divide()` has a one-line bug, does the engine put `divide` at rank 1 with the right confidence?
2. **The persistence layer** — does the JSON on disk match the in-memory shape, byte-for-byte?
3. **The cache short-circuit** — does calling `derive` twice (or `get` after `derive`) preserve the original `derived_at` timestamp?
4. **The Memory availability flag** — does `MemoryEntry.has_localization_findings` flip from False to True after the first derive?
5. **All four refusal reasons** (`no_failed_tests`, `no_coverage`, `no_run_evidence`, `run_not_analyzable`).
6. **The cheap availability probe** (`check_localization_availability`) — does it correctly return True when derivable and False when not, without actually deriving?

Every one of those passed.

## Commands run + observed output

### Step 0 — gate

```bash
$ uv run pytest -q tests/unit tests/integration
588 passed, 3 skipped in 14.11s     (Localization contributed +87 tests)

$ uv run mypy
Success: no issues found in 69 source files    (Localization contributed +11 src files)
```

Both numbers match the verification request verbatim.

### Step 1 — happy-path derive

After `novetest init && novetest run --coverage tests/` on the `localization-branch` fixture (run_id `01KSPJN0SSRDGT5QA31475VZSN`), called `derive_localization_findings(store, ref)`:

```
type: LocalizationFinding
top-level keys: ['schema_version', 'run_reference', 'engine_name', 'ecosystem', 'mode', 'confidence',
                 'formula', 'alternate_scores_available', 'top_n', 'entries', 'derived_at', 'metadata']
mode:                       sbfl_per_test
confidence:                 high
formula:                    ochiai
alternate_scores_available: ['dstar2', 'op2', 'tarantula']     ← list[str], NOT bool
top_n:                      10
entries:                    10
rank-1 code_location:       {kind: 'symbol', file: 'localization_branch/calculator.py',
                             symbol: 'divide', line_range: [31, 34],
                             primary_line: 34, evidence_lines: [34]}
rank-1 score_raw:           1.0
rank-1 score_normalized:    1.0
rank-1 tied_with:           ['entry_index_1']
rank-1 alternate_scores:    {'op2': 1.0, 'dstar2': 0.0, 'tarantula': 1.0}
rank-1 related_failed_tests:['tests/test_calculator.py::test_divide_yields_quotient']
rank-1 evidence_citations:  2  (kinds: ['test_result', 'coverage_fact'])
```

Verbatim match against the verification's expected shape. The `alternate_scores_available: list[str]` pin (correcting the handoff doc's bool assumption) is confirmed.

### Step 2 — on-disk JSON round-trip

```
$ ls .novetest/localization/findings/run_01KSPJN0SSRDGT5QA31475VZSN/
localization_findings.json

$ python3 -c 'import json; d=json.load(open(...)); print(list(d.keys()))'
['schema_version', 'run_reference', 'engine_name', 'ecosystem', 'mode', 'confidence',
 'formula', 'alternate_scores_available', 'top_n', 'entries', 'derived_at', 'metadata']
mode: sbfl_per_test
schema_version: 1
entries_count: 10
```

On-disk shape matches in-memory derive output. Path layout matches the documented `<store>/localization/findings/run_<run_id>/localization_findings.json` exactly.

### Step 3 — cache short-circuit

```
a.derived_at: 1779947975653
b.derived_at: 1779947975653   ← get_localization_findings reads cache
c.derived_at: 1779947975653   ← second derive short-circuits to cache
get == derive  : True
re-derive == a : True
```

Even with a 50ms `time.sleep` between calls, the timestamp does NOT re-stamp. Cache short-circuit works on both the `get` path and the `derive` path.

### Step 4 — Memory `has_localization_findings` flag flip

```
has_localization_findings : True
has_coverage_facts        : True
has_regression_facts      : False
```

After Step 1 derived findings to disk, the Memory availability probe correctly flips the localization flag. The other two flags read independently (coverage True because the run was `--coverage`; regression False because no pair has been compared).

### Step 5 — each `LocalizationUnavailable` reason

**5a. `no_coverage`** — re-ran the fixture WITHOUT `--coverage`:
```
isinstance LocalizationUnavailable: True
reason : no_coverage
detail : coverage facts unavailable; failure_proximity mode is not yet implemented (Phase 4 follow-up)
```
Verbatim match against the verification's documented behavior.

**5b. `no_run_evidence`** — fake `RunReference`:
```
type: LocalizationUnavailable
reason: no_run_evidence
detail: No run evidence for run_id='01FAKEFAKEFAKEFAKEFAKEFAKE' in /tmp/novetest-verify-loc/.novetest
```
The detail string carries the requested run_id and the store path — useful for AI debugging.

**5c. `run_not_analyzable`** — called `get_localization_findings` BEFORE `derive` on a fresh workspace:
```
type: LocalizationUnavailable
reason: run_not_analyzable
detail: findings not yet derived
```
Verbatim match. This is the deliberate "cache-empty overload" of `run_not_analyzable` documented in `retrieval.py:51`.

**5d. `no_failed_tests`** — synthesized an all-passing run via `store_run_evidence`:
```
type: LocalizationUnavailable
reason: no_failed_tests
detail: run has no failed test results
```

All four `KNOWN_REASONS` exercised and exhibited correct discrimination + sensible detail strings.

### Step 6 — `check_localization_availability` cheap probe

```
with-coverage: check_localization_availability = True
no-coverage  : check_localization_availability = False
```

The probe distinguishes derivable from non-derivable without running the derivation. Cheap to call from CLI or orchestration code.

### Bonus probe — full 10-entry breakdown

I dumped all 10 entries to characterize the ranking. The condensed version:

| idx | rank | score | norm | kind | file/symbol |
|---|---|---|---|---|---|
| 0 | 1 | 1.000 | 1.000 | symbol | `localization_branch/calculator.py::divide` (lines 31–34) |
| 1 | 1 | 1.000 | 1.000 | symbol | `tests/test_calculator.py::test_divide_yields_quotient` (lines 31–33) |
| 2–7 | 2 | 0.000 | 0.000 | symbol | 5 other production symbols + Counter.__init__ + Counter.increment |
| 8–9 | 2 | 0.000 | 0.000 | symbol | 2 other test functions (`test_add_sums_two_numbers`, `test_subtract_yields_difference`) |

Production-code suspects: **7**, test-code suspects: **3**, of top_n=10.
`max evidence_lines per entry: 2` (cap = 10, not hit on this fixture).
`tied_with` references all stay INSIDE top_n=10 (no cross-boundary refs observed).
`score_normalized` matches `score_raw` here because the global max (1.0) is at rank 1 — min-max normalization doesn't change anything when the top of the full ranking is already in top_n. The verification's "score_normalized may be <1.0" case is not triggered by this fixture (and is rare in practice).

## Critical observation — the rank-1 tie includes the failing test itself

The verification explicitly asked: "Confirm the tied entry at index 1 is `localization_branch.calculator.divide` or another suspect — and report what the tied entry actually is, so PM can document the expected fixture behavior."

**Answer:** the tied entry at index 1 is **NOT a production symbol**. It is the failing test function itself:

```
entries[1].code_location = {
    kind: 'symbol',
    file: 'tests/test_calculator.py',
    symbol: 'test_divide_yields_quotient',
    line_range: [31, 33],
    primary_line: 33,
    evidence_lines: [33]
}
entries[1].rank = 1
entries[1].score_raw = 1.0
entries[1].tied_with = ['entry_index_0']
```

**Why this happens:** the per-test SBFL formula correlates "lines executed only by failing tests" with high suspect scores. The body of `test_divide_yields_quotient` was executed exclusively by the failing test (because it IS the failing test), so its Ochiai score is identical to the bug it asserts against. Mathematically clean; product-experience-wise, surprising — a user asking "where's the bug?" gets back a list whose top entry includes the test that detected the bug, not just the code with the bug.

**More broadly:** 3 of 10 entries in the top ranking are test code. The current SBFL path doesn't filter test files out.

This is a **PM/CEO design call**, not a bug:
- Option A (status quo): leave test code in the ranking. Honest about what SBFL really measures; AI consumers can filter by path themselves.
- Option B: add a `test_path_exclusion` filter post-ranking to remove entries whose file matches the engine's test-glob (e.g. anything starting with `tests/`). Cleaner user-facing output; loses some signal in unusual fixture layouts.
- Option C: keep them but mark them in the schema (e.g. add `is_test_code: bool` to `CodeLocation`). Explicit metadata; lets consumers decide.

I have no preference and no scope to choose; flagging for PM/CEO judgment before the CLI surface ships and this behavior becomes user-visible.

## Issues found

**None blocking.**

One observation (above) is a design-decision flag, not a defect. The engine matches its design contract verbatim.

## Observations worth flagging (not blockers)

- **`alternate_scores_available` field type pin holds**: the value is a `list[str]` enumerating the other formulas computed, NOT a bool. The handoff brief was wrong; the verification corrected the brief; live behavior matches the verification. Worth freezing in a PM decision.
- **`LocalizationUnavailable` has NO `to_dict()` method**, unlike `RegressionUnavailable`. This means refusal results cannot be serialized into a JSON envelope by the engine alone — the orchestration/CLI layer will need to format them ad-hoc when the CLI verb ships next cycle. PM may want a follow-up consistency task.
- **`run_not_analyzable` overload**: the same reason code surfaces both "the run cannot be analyzed for fundamental reasons" AND "findings haven't been derived yet" (cache-empty). The detail string differs (`"findings not yet derived"` vs other phrasings), but a consumer treating the reason as an opaque enum will conflate these. The verification flagged this as a PM-decision item: keep the overload, or add a dedicated `REASON_MISSING_DERIVED_FACTS` mirroring Regression. My recommendation: split them; the cache-empty path is recoverable (just derive), while the other `run_not_analyzable` causes are not.
- **`tied_with` uses `entry_index_<i>` string format**: not a list of indices but a list of stringly-typed references. The format works (and matches the implementation's choice to embed positional refs as strings for JSON friendliness), but PM may want to freeze this convention in the upcoming `decisions/` entry. The verification flagged this for freezing.
- **No `file`-level or `branch`/`line` kinds observed** — only `symbol`. The fixture's Python module yielded symbol-level locations exclusively. `file`-level fallback would trigger for module-level code or non-Python files; `branch`/`line` are reserved. Worth noting that the live behavior today is symbol-dominant.

## Recommendations for PM

1. **No blockers; ship as-is.** The engine is robust and the on-disk shape matches design verbatim.
2. **Decide on test-code in localization output** (the "Critical observation" above) BEFORE the CLI verb ships next cycle — once a user sees `tests/test_*.py` ranked as a "suspect", that perception is hard to walk back. Cheapest fix is adding a path filter; cleanest fix is the `is_test_code` metadata.
3. **Freeze the seven schema decisions** the verification listed (12-key Finding / 9-key Entry / 6-key CodeLocation / 3-key Citation / Unavailable shape + KNOWN_REASONS / `tied_with` convention / persistence path). All seven have now been fielded; PM can lock them in a `decisions/2026-05-XX-localization-finding-shape.md` entry.
4. **Decide on the `run_not_analyzable` overload** — either keep it documented as overloaded (with the `detail` string as the discriminator) or split out `REASON_MISSING_DERIVED_FACTS`. I recommend splitting for consistency with Regression.
5. **Consider adding `LocalizationUnavailable.to_dict()`** to match `RegressionUnavailable`'s shape — the CLI verb work next cycle will need this anyway.
6. **Companion verification (run-gotest-adapter) also passed.** Both findings can close together as the 2026-05-28 batch.

## Process notes

- `Write` tripped the worktree-isolation guard documented in `GOTCHAS.md`; both findings written via Bash heredoc.
- `jq` is not installed on this host; all JSON inspection went through `python3 -c 'import json; ...'`. Not a blocker for verification — the JSON envelopes parse identically — but flagging for any future verification doc that assumes `jq`.
- Temporary scratch under `/tmp/novetest-verify-loc*`; not committed.
