---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-06-01
slug: localization-perf-nfr-loc-002
merged_commit: 36c6b82
source_handoffs:
  - handoffs/localization-team-2026-06-01-perf-nfr-loc-002.md
related:
  - tasks/localization-team-2026-06-01-perf-nfr-loc-002.md
  - design/implementation-plan/delivery-phasing.md
  - design/implementation-plan/localization-strategy.md
  - design/requirements-analysis/requirements-specification/groups/localization.md
---

# Verification: Phase 4 §4 #3 — perf NFR-LOC-002 closure (Branch A)

## TL;DR for Manual Test

A Localization-team slice landed at `36c6b82` (FF-merge onto
`6a3b801`) that:

1. Adds a perf-benchmark tree under `tests/perf/localization/`
   (1 helper + 3 mode-specific tests) that **empirically validates
   NFR-LOC-002** ("≤500 failed-test refs × ≤50,000 covered
   locations within 8 s").
2. Lands **three surgical vectorization patches** to
   `src/novetest/localization/derive.py` private helpers
   (`_count_vectors`, `_aggregate_by_symbol`, `_related_failed_tests`).
   These reduced the per-test mode from ~9.85 s (pre-patch, Branch C
   trigger) to ~1.33 s (Branch A outcome) at NFR scale on the
   originating dev host.
3. Updates `spectra.py`'s module docstring (no behavior change there)
   and `localization-strategy.md`'s Open Items #3 (Open Q #11
   disposition: dense representation suffices at NFR scale; sparse
   repr deferred to post-MVP).
4. **No CLI envelope change. No algorithmic change.** The 166 existing
   Localization unit + integration tests still pass. Pre-merge gate:
   771 + 10. Post-merge gate on `main`: **771 + 10**, mypy strict
   clean on 72 src files.

The slice is the **last Phase 4 §4 DoD bullet**. Phase 4 → 100%
complete once PM ticks `delivery-phasing.md:188` at cycle close.

Manual Test's job for this slice is:

- (A) re-confirm the default suite + mypy gates on your host
- (B) re-run the perf suite and report your host's median for the
  per-test mode (NFR-COV-002 precedent showed host variance is
  ~order-of-magnitude across dev machines; we want a second data point)
- (C) algorithmic-equivalence pin: a quick `novetest localization
  latest` run on the `localization-branch` fixture should still
  rank `divide` top-1 with `score_raw: 1.0` under Ochiai — exactly
  as Phase 4's existing integration tests expect
- (D) regression-pins from prior cycles still hold (D5 cache
  rederive, D6 status sub_reports)

## Merged commit + source

| Aspect | Value |
|---|---|
| Merge tip | `36c6b82` (FF, no merge commit) |
| Base | `6a3b801` (prior `main` tip) |
| Branch on origin | `main` (pending CEO push authorization) |
| Source handoff | `agent-comms/handoffs/localization-team-2026-06-01-perf-nfr-loc-002.md` |
| Files touched | 10 (2 src edited, 5 perf-test new, 1 strategy doc, 1 WORKLOG, 1 handoff) |
| Net source-file count | **72** (unchanged) |

### Files changed (verbatim from `git show --name-only 36c6b82`)

```
WORKLOG.md
agent-comms/handoffs/localization-team-2026-06-01-perf-nfr-loc-002.md
design/implementation-plan/localization-strategy.md
src/novetest/localization/derive.py
src/novetest/localization/sbfl/spectra.py
tests/perf/localization/__init__.py
tests/perf/localization/generate_large_inputs.py
tests/perf/localization/test_perf_derive_aggregate.py
tests/perf/localization/test_perf_derive_failure_proximity.py
tests/perf/localization/test_perf_derive_per_test.py
```

## Pre-merge gates (worktree, equipped host)

Reproduced on the worktree before FF-merge:

| Gate | Command | Result |
|---|---|---|
| Default suite | `uv run pytest -q tests/unit tests/integration` | 771 passed, 10 skipped (31.88 s) |
| mypy strict | `uv run mypy` | Success — 72 source files |
| Perf suite | `uv run pytest tests/perf -v` | **7 passed** (10.65 s) |

Worktree perf re-measurement (independent of the team's handoff numbers,
captured by Main Branch on the equipped host):

| Mode | Median | Mean | Stdev | Budget | NFR |
|---|---|---|---|---|---|
| sbfl_per_test | **1.297 s** | 1.311 s | 0.048 s | 5.0 s | 8.0 s |
| sbfl_aggregate | 0.038 s | 0.040 s | 0.005 s | 5.0 s | 8.0 s |
| failure_proximity | 0.018 s | 0.018 s | 0.000 s | 5.0 s | 8.0 s |

(Team handoff captured 1.328 s median — both well under budget; the
~30 ms drift between two runs on the same host is within stdev. Branch
A outcome confirmed independently.)

## Post-merge gates on `main` (this is the gate that ships)

```
$ uv run pytest -q tests/unit tests/integration
… 771 passed, 10 skipped in 32.04s

$ uv run mypy
Success: no issues found in 72 source files
```

**Both green.** No regression in default suite. No type regression.

## Verification scenarios for Manual Test

> **Setup note**: all CLI scenarios below assume the working tree is
> at commit `36c6b82` (`git log -1 --oneline` should show
> `36c6b82 perf(localization): Phase 4 §4 #3 — NFR-LOC-002 perf
> benchmark + vectorize derive.py hot paths (Branch A)`). The slice
> is local-only until CEO authorizes push to `origin`.

---

### Scenario A — default suite still green on your host

```sh
cd /home/yjshin/dev/Nove-Test
uv run pytest -q tests/unit tests/integration
```

**Expected**: `771 passed, 10 skipped` in roughly the same wall time
as your last cycle's baseline (`6a3b801` → 771 + 10 in ~32 s on
Main Branch's equipped host). The perf suite is **outside**
`[tool.pytest.ini_options].testpaths` and should NOT be collected
here — confirm by visually checking that `tests/perf/` files do not
appear in pytest's collected modules.

**Why it matters**: the slice's three `derive.py` patches preserve
algorithmic semantics — 166 existing Localization tests (which DO
get collected here) must all still pass.

---

### Scenario B — mypy strict still clean

```sh
uv run mypy
```

**Expected**: `Success: no issues found in 72 source files`.

**Why it matters**: the perf patches introduced
`absolute_path_cache: dict[str, Path] = {}` and `col_indices_arr =
np.asarray(col_indices, dtype=np.intp)` — both annotated. mypy must
accept the new shape.

---

### Scenario C — perf suite collects + passes; report YOUR host's per-test median

```sh
uv run pytest tests/perf -v
```

**Expected**: `7 passed`. The per-test print statements should show
roughly:

```
[NFR-COV-002] compare_coverage_facts at 50,000 covered locations/side: median=~0.03s …
[NFR-LOC-002 / sbfl_aggregate] 500 failed × 50,000 locations: median=~0.04s …
[NFR-LOC-002 / failure_proximity] 500 failed-log parses: median=~0.02s …
[NFR-LOC-002 / sbfl_per_test] 3500 tests × 50,000 locations: median=<some value>s …
```

**The number to capture**: the `sbfl_per_test` median. The internal
budget gate is 5.0 s (the test asserts `median < 5.0`); the NFR
ceiling is 8.0 s. The Coverage NFR-COV-002 precedent (closed
2026-05-21) showed dev-host variance of ~10x — so Manual Test's
host might see anything from sub-second up to several seconds.

**Report in your finding**:
- The verbatim print line for `sbfl_per_test` (including
  `median=`, `mean=`, `stdev=`, and the `timings=[...]` list)
- The verbatim print lines for the other two modes (for completeness)
- Whether `7 passed` was observed
- Your host's specs if convenient (CPU model, RAM, OS) — helps PM
  understand the budget headroom envelope across machines

**Why it matters**: this is the **empirical core** of the slice.
NFR-LOC-002 is a published MVP exit criterion; a second host data
point validates that the 5.0 s internal budget is broadly
defensible (not just a single-machine artifact).

**Memory note**: the per-test benchmark holds a `numpy.uint8`
matrix of shape `3500 × 50000` (~175 MB) plus index dicts. The team
estimated ~210 MB peak. If your host has <1 GB free RAM and OOMs,
report that as a finding (the perf test currently makes no memory
assertion; we may need one).

---

### Scenario D — algorithmic-equivalence pin on `localization-branch` fixture

The `derive.py` patches MUST preserve byte-identical algorithmic
output. The cheapest way to gate that beyond the existing 166 unit
+ integration tests is a CLI smoke against the `localization-branch`
pytest fixture (deliberate bug at `localization_branch/calculator.py`
`divide` function, lines 31-34).

```sh
# Stage the fixture in a temp workspace
TMP=$(mktemp -d /tmp/loc-pin-XXXXXX)
cp -r tests/fixtures/projects/localization-branch/* "$TMP/"
cd "$TMP"

# Init + run with coverage
uv --project /home/yjshin/dev/Nove-Test run novetest init
uv --project /home/yjshin/dev/Nove-Test run novetest run --coverage

# Localization with defaults
uv --project /home/yjshin/dev/Nove-Test run novetest localization latest \
    | python3 -m json.tool > /tmp/loc-D.json

# Read the top entry
python3 -c "
import json
d = json.load(open('/tmp/loc-D.json'))
lo = d['data']['localization_outcome']
e0 = lo['entries'][0]
print('kind:', lo['kind'])
print('mode:', lo['mode'])
print('formula:', lo['formula'])
print('top_n:', lo['top_n'])
print('confidence:', lo['confidence'])
print('alternate_scores_available:', lo['alternate_scores_available'])
print('entries[0].rank:', e0['rank'])
print('entries[0].score_raw:', e0['score_raw'])
print('entries[0].score_normalized:', e0['score_normalized'])
print('entries[0].file:', e0['code_location']['file'])
print('entries[0].symbol:', e0['code_location']['symbol'])
print('entries[0].line_range:', e0['code_location']['line_range'])
print('entries[0].primary_line:', e0['code_location']['primary_line'])
print('entries[0].alternate_scores:', e0['alternate_scores'])
print('entries[0].related_failed_tests:', e0['related_failed_tests'])
print('entries[0].tied_with:', e0['tied_with'])
"
```

**Expected (verbatim from Main Branch's empirical capture on
`36c6b82`)**:

```
kind: fact-set
mode: sbfl_per_test
formula: ochiai
top_n: 10
confidence: high
alternate_scores_available: ['dstar2', 'op2', 'tarantula']
entries[0].rank: 1
entries[0].score_raw: 1.0
entries[0].score_normalized: 1.0
entries[0].file: localization_branch/calculator.py
entries[0].symbol: divide
entries[0].line_range: [31, 34]
entries[0].primary_line: 34
entries[0].alternate_scores: {'dstar2': 0.0, 'op2': 1.0, 'tarantula': 1.0}
entries[0].related_failed_tests: ['tests/test_calculator.py::test_divide_yields_quotient']
entries[0].tied_with: ['entry_index_1']
```

`entry_index_1` is the failing test function
(`tests/test_calculator.py::test_divide_yields_quotient`) — it
shares the Ochiai score 1.0 because per-test attribution sees
exactly that one test executing both lines (the bug + the test).
Tie behavior is the engine's standard handling, not a regression.

**Why it matters**: this is the canonical "find the deliberate bug"
scenario. If the perf patches accidentally broke rank order, file
attribution, or the score computation, this scenario flips on the
first line. The 166 existing tests should already catch any
breakage, but a CLI-level smoke is the human-visible regression-pin.

---

### Scenario E — D5 regression-pin still holds (cache rederive on flag mismatch)

The slice landed on a tip that already contains the D5 cache-rederive
fix (`4895847`). Confirm it still functions post-merge.

**Setup**: continue from Scenario D's `$TMP` workspace.

```sh
# Already have a defaults-derived cache from Scenario D.
# Now force a flag mismatch:
uv --project /home/yjshin/dev/Nove-Test run novetest localization latest \
    --formula op2 --top-n 3 \
    | python3 -m json.tool > /tmp/loc-E.json

python3 -c "
import json
d = json.load(open('/tmp/loc-E.json'))
lo = d['data']['localization_outcome']
w = d['warnings']
print('warnings count:', len(w))
print('warning[0].code:', w[0]['code'])
print('warning[0].previous:', w[0]['details']['previous'])
print('warning[0].requested:', w[0]['details']['requested'])
print('formula:', lo['formula'])
print('top_n:', lo['top_n'])
print('entries count:', len(lo['entries']))
e0 = lo['entries'][0]
print('entries[0].symbol:', e0['code_location']['symbol'])
print('entries[0].score_raw:', e0['score_raw'])
"
```

**Expected**:

```
warnings count: 1
warning[0].code: localization-cache-rederived
warning[0].previous: {'formula': 'ochiai', 'top_n': 10}
warning[0].requested: {'formula': 'op2', 'formula_explicit': True, 'top_n': 3, 'top_n_explicit': True}
formula: op2
top_n: 3
entries count: 3
entries[0].symbol: divide
entries[0].score_raw: 1.0
```

**Why it matters**: D5 was closed PASSED 2026-06-01. The `derive.py`
perf patches touch the same module as D5's fix. We want a
fresh-eyes confirmation that D5's behavior is intact.

---

### Scenario F — D6 regression-pin still holds (status sub_reports reflect on-disk facts)

```sh
# Still in $TMP, after Scenarios D + E ran.
uv --project /home/yjshin/dev/Nove-Test run novetest status \
    | python3 -m json.tool > /tmp/status-F.json

python3 -c "
import json
d = json.load(open('/tmp/status-F.json'))
sub = d['data']['sub_reports']
print('sub_reports:')
for k, v in sub.items():
    print(f'  {k}: {v}')
print('run_history_size:', d['data']['run_history_size'])
"
```

**Expected**:

```
sub_reports:
  coverage: available
  localization: available
  regression: unavailable
  replay: unavailable
run_history_size: 1
```

**Why it matters**: D6 was closed PASSED 2026-06-01. The perf slice
does NOT touch `src/novetest/orchestration/workflows/status.py`, but
a CLI smoke confirms the integration is intact post-merge.

---

### Scenario G — perf determinism pin (RNG seed produces same fixture)

```sh
# In the main worktree
cd /home/yjshin/dev/Nove-Test
uv run pytest tests/perf/localization/test_perf_derive_per_test.py -v 2>&1 | tee /tmp/perf-G1.log
uv run pytest tests/perf/localization/test_perf_derive_per_test.py -v 2>&1 | tee /tmp/perf-G2.log
```

**Expected**: BOTH runs pass; both print the same `timings=[…]`
list length (5 entries) and the medians stay in the same regime
(within ~10% of each other on a quiet host).

**Why it matters**: the perf helper uses a fixed RNG seed
(`generate_large_inputs.py` per §5.2.1 of the brief). Manual Test
re-running the perf suite must produce equivalently-shaped fixtures.
If two consecutive runs show wildly different timings (e.g., one
runs 1.3 s and the other 7 s), the determinism contract is broken
or the host has heavy background load.

---

### Scenario H — pre-vs-post-patch sanity (optional, deeper probe)

If you want to validate that the `derive.py` perf patches are
genuinely the cause of the speedup (not just a measurement artifact),
checkout the pre-merge tip and re-run the per-test perf benchmark.
This is **optional** — the team's pre-optimization measurement
(9.85 s median; cProfile attached in the handoff) is the canonical
record.

```sh
# Save your spot
git stash --include-untracked  # if any
git checkout 6a3b801
uv run pytest tests/perf/localization/test_perf_derive_per_test.py -v 2>&1 | tee /tmp/perf-H.log
# This test will probably FAIL with median ≥ 5.0 s on 6a3b801
# (the perf tests don't exist on that tip — pytest will report a
# collection error / not-found, NOT a budget failure. The test files
# only exist on 36c6b82 onwards.)
git checkout main  # back to 36c6b82
```

Actually — Scenario H as written above doesn't work because the
perf tests are **new in `36c6b82`**. To genuinely measure pre-vs-post,
one would have to manually revert the three `derive.py` patches
while keeping the perf tests. That's deeper than Manual Test should
go without explicit ask. **Skip Scenario H unless PM explicitly
requests it**; the team's cProfile evidence in the handoff is
sufficient.

---

## Critical edge cases worth probing (Manual Test's discretion)

The slice's §"Out of scope" was tight (private helpers only, no
public API or formula module edits). The following are areas where
Main Branch could not exhaustively probe in a single after-merge
pass; flag as findings if anything looks off:

1. **Cargo aggregate mode regression**: this slice is per-test mode
   focused. Quick smoke against `cargo-test-basic-coverage` (or
   `localization-aggregate-only`) confirming `mode: sbfl_aggregate`
   still derives correctly post-merge. Main Branch's standing
   regression-pin from the D5 cycle (`score_raw: 0.5` on
   `arithmetic.rs:53` under Ochiai/10) should still hold byte-
   identically. (Main Branch did not re-run this scenario this
   cycle because the cargo binary path was inconsistent in the
   default shell; Manual Test's host typically has `cargo` on
   PATH.)

2. **`alternate_scores` correctness**: Scenario D pins `op2: 1.0`,
   `tarantula: 1.0`, `dstar2: 0.0` for the top entry. If any of
   these drift, the Op2/Tarantula/DStar2 formula modules might have
   been impacted by the `_count_vectors` patch. (Pre-patch was
   `matrix.astype(np.int64)` upfront; post-patch is
   `sum(axis=0, dtype=np.int64)` per formula call. Numpy guarantees
   numerical equivalence, but worth one sample-check.)

3. **`run_not_analyzable` path**: on an all-passing fixture (e.g.,
   `cargo-test-basic-coverage` without manual edits, or
   `pytest-coverage`), `localization latest` should still emit
   `kind: 'unavailable'` with `reason: 'run_not_analyzable'`. The
   D5 cycle pinned this; the perf slice does not touch the
   unavailable path but a smoke check is cheap.

4. **Memory profile under per-test mode at NFR scale**: if your
   host has `/usr/bin/time -v` or similar, capture max-RSS while
   running `test_perf_derive_per_test_meets_nfr_loc_002`. The team
   estimated ~210 MB peak. If you see significantly more (e.g.,
   2 GB+), the in-place vectorization may not have eliminated all
   the intermediate copies and a follow-up could be queued.

5. **Cold-cache vs warm-cache regime**: the perf test explicitly
   unlinks `localization_findings.json` between each timed iteration
   to force cold-derive. If you remove that unlink and re-run, the
   median should collapse to <0.1 s (cache hit). This isn't a
   regression-pin; it's a sanity-check on the cache contract.

---

## Phase 4 closure context (for PM cycle close, not Manual Test)

This slice is the **last unticked Phase 4 §4 DoD bullet** per
`design/implementation-plan/delivery-phasing.md:188`. Once Manual
Test confirms the gates + perf median holds, PM ticks the bullet
and Phase 4 → **100% complete**.

Remaining MVP scope after Phase 4 closes:
- Phase 3 JUnit + .NET adapters
- Phase 5 (Replay engine + SQLite derived index)
- Phase 6 (MCP transport / release polish per delivery-phasing)

This is informational for Manual Test's situational awareness.
No action item.

---

## Anything that wasn't obvious during merge (Main Branch notes)

1. **Clean FF**: base commit `6a3b801` matched main tip exactly.
   No rebase, no conflict, no merge commit.

2. **INDEX.md regen was NOT in the slice commit** (the handoff
   manifest mentioned it would be; the team forgot to stage it).
   Main Branch regenerates INDEX as part of the verification
   commit (this file's sibling commit). This is the standard
   pattern and not a slice defect.

3. **Worktree perf re-measurement was independent**: Main Branch
   re-ran `uv run pytest tests/perf -v` on the worktree before
   FF-merge to confirm the team's median claim. Saw 1.297 s
   (team: 1.328 s) — within stdev. No discrepancy.

4. **`cargo` binary on PATH**: Main Branch's default shell does
   not have `~/.cargo/bin` on `PATH`. For cargo-aggregate
   regression-pins (e.g., the standing D5 fixture), Main Branch
   used `export PATH="$HOME/.cargo/bin:$PATH"` for the smoke
   probes. If Manual Test's shell has `cargo` natively, the cargo
   scenario in Critical Edge Cases §1 should run without that
   tweak.

5. **`derive.py` patch scope verification**: Main Branch
   spot-checked that the three patches modify only the named
   private helpers (`_count_vectors`, `_aggregate_by_symbol`,
   `_related_failed_tests`) and the algorithmic invariant
   (`isinstance(result, FactSet)` for D6 / the cached findings
   shape for D5) is unchanged. `git diff main~..main --
   src/novetest/localization/derive.py` shows +71 -20 lines
   confined to these three frames + one new `import` line for
   `numpy`'s `np.ix_` / `np.any` usage. No public API touch.

6. **No `mcp`, no `replay`, no `models/` touch**: the slice is
   strictly perf-validation. Future-phase territories are
   undisturbed.

## Final disposition gate

If Manual Test's run reports:

- ✅ default suite green (771 + 10) on your host
- ✅ mypy strict clean (72 src files)
- ✅ perf suite 7 passed; per-test median < 5.0 s
- ✅ Scenarios D, E, F return the documented envelope literals
- ✅ Scenario G shows determinism (two consecutive perf runs in
   the same regime)

→ then Phase 4 §4 #3 is closed PASSED and PM can tick the
delivery-phasing bullet at cycle close.

If any of the above fails, write a finding under
`agent-comms/findings/` per your charter and flag for PM.
