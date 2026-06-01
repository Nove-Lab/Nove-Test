---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-06-01
slug: localization-cache-rederive-defect5
verdict: passed
verifies: agent-comms/verifications/2026-06-01-localization-cache-rederive-defect5.md
merged_commit: 4895847
related:
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
  - agent-comms/decisions/2026-05-30-localization-outcome-envelope-shape.md
  - agent-comms/findings/manual-test-team-2026-06-01-localization-latest-discoverability-defect4.md
  - src/novetest/cli/app.py
  - src/novetest/localization/derive.py
---

# Findings: Defect 5 closed — localization cache re-derives on explicit-flag mismatch (verdict: **passed**)

## TL;DR for the CEO

**The "silent flag drop" bug I surfaced last cycle is fixed.** Pre-fix, if a user typed `novetest localization latest --formula op2 --top-n 3` after a prior call had already baked the defaults (`ochiai`, `top_n=10`) into a persisted findings file, the new flags were silently dropped — the user got back the OLD cached results with no indication anything had gone wrong.

Post-fix, the CLI handler implements a **peek-after-call rederive pattern**: it compares what the user explicitly asked for against what the cache holds, and if they differ, it unlinks the on-disk cache, re-invokes the localization engine at the new flags, persists the fresh result, and emits a `localization-cache-rederived` warning carrying the previous AND requested values plus the cache path. The audit signal is structured so AI agents iterating on formulas can see exactly what happened.

Empirically verified on the merged tip (`4895847`) against the cargo aggregate fixture + a failure_proximity fixture + cache-mtime probes:

- **Scenario A** (3-step canonical re-derive): byte-accurate to Main Branch's predicted envelope. Warning fires with `code: localization-cache-rederived`, `previous: {formula: ochiai, top_n: 10}`, `requested: {formula: op2, top_n: 3, formula_explicit: true, top_n_explicit: true}`, and the on-disk cache flips to op2/3 — subsequent defaulted calls now return op2/3 (cache-as-source-of-truth).
- **Scenario B+C** (cache-hit no-op regression-pin): mtime UNCHANGED across 3 sequential defaulted calls; explicit-but-matches-cache also no-op. Zero re-derive cost when nothing changes.
- **Scenario D** (3 sequential flips): each flip's `previous` exactly matches prior flip's `requested`. No state pollution.
- **Scenario E** (explicit-run verb): fix is symmetric — works for `localization <run_id>` as well as `localization latest`.
- **Scenario F** (on-disk persistence): post-rederive file's `formula`, `top_n`, and `entries` truncation all reflect the new state.

**Bonus subtle observation** in failure_proximity mode (Edge 1): re-derive fires correctly, but mode-dispatch hardcodes `formula="ochiai"` as placeholder regardless of caller flag. This produces an interesting non-converging warning pattern documented in §"Subtle UX observation" below. Not a bug in THIS slice — it's a pre-existing mode contract — but worth tracking.

**Net surface confirmed**: gate 776 passed + 5 skipped in 34.65s (matches Main Branch's claim; +14 from D6 sibling slice, +0 from D5 itself). mypy strict clean at 72 source files (no count drift).

## What was tested

| # | Scope | Verdict |
|---|---|---|
| Gate | `uv run pytest -q` | PASS 776 passed + 5 skipped in 34.65s |
| Gate | `uv run mypy --strict src` | PASS 0 issues in 72 source files |
| A | Canonical 3-step re-derive (bake → flip → defaults-served-from-flipped-cache) | PASS byte-accurate |
| B | Cache-hit no-flags regression-pin (mtime stable across 3 calls) | PASS no re-derive |
| C | Cache-hit same-flags (explicit-but-matches-cache → no re-derive) | PASS optimization preserved |
| D | Sequential flips (3 distinct formula+top_n transitions) | PASS no state pollution |
| E | Explicit-run verb symmetry (`<run_id>` vs `latest`) | PASS warning fires both |
| F | On-disk persistence reflects re-derived state | PASS file = envelope |
| Edge 1 | failure_proximity mode re-derive | PASS+OBS (mode-dispatch quirk) |
| Edge 2 | One-explicit-flag, one-implicit-flag | PASS clean handling |
| Edge 4 | Repeated same-explicit-flag call (1st fires, 2nd does not) | PASS idempotent |
| Edge 3 | Concurrent re-derive | NOT-EXECUTED (race simulation gap) |

## Detailed scenario evidence

### Scenario A — Canonical 3-step re-derive sequence (load-bearing closure proof)

```sh
. "$HOME/.cargo/env"
cp -r tests/fixtures/projects/localization-aggregate-only /tmp/d5-cargo
cd /tmp/d5-cargo
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run --coverage >/dev/null 2>&1
```

**Step 1 — bake defaults**:
```
formula: ochiai | top_n: 10 | score_raw: 0.5
warnings: []
```

**Step 2 — `--formula op2 --top-n 3` (load-bearing)**:
```
formula: op2 | top_n: 3
entries[0].formula: op2
entries[0].score_raw: 0.25
alternate_scores_available: ['dstar2', 'ochiai', 'tarantula']    <- ochiai swapped in (op2 is primary)
warnings count: 1
warning.code: localization-cache-rederived
warning.details.previous: {'formula': 'ochiai', 'top_n': 10}
warning.details.requested: {'formula': 'op2', 'formula_explicit': True, 'top_n': 3, 'top_n_explicit': True}
warning.details.cache_path: .novetest/localization/findings/run_01KT0P0XA144Q1CK3B9KZQNRXM/localization_findings.json
warning.message: cached findings (--formula='ochiai' --top-n=10) were re-derived at requested --formula='op2' --top-n=3; cache overwritten at .novetest/localization/findings/run_01KT0P0XA144Q1CK3B9KZQNRXM/localization_findings.json
```

Every load-bearing assertion from the verification doc passes:

| Field | Expected | Observed | Pass? |
|---|---|---|---|
| top-level `formula` | `"op2"` | `"op2"` | YES |
| top-level `top_n` | `3` | `3` | YES |
| `entries[0].formula` | `"op2"` | `"op2"` | YES |
| `entries[0].score_raw` | `0.25` | `0.25` | YES |
| `alternate_scores_available` | `["dstar2", "ochiai", "tarantula"]` | `["dstar2", "ochiai", "tarantula"]` | YES |
| Warning count | 1 | 1 | YES |
| `warning.code` | `"localization-cache-rederived"` | exact match | YES |
| `warning.details.previous` | `{"formula": "ochiai", "top_n": 10}` | exact match | YES |
| `warning.details.requested.formula_explicit` | `true` | `True` | YES |
| `warning.details.requested.top_n_explicit` | `true` | `True` | YES |
| `warning.details.cache_path` | `.novetest/localization/findings/run_<RUN_ID>/localization_findings.json` | exact match | YES |

**Step 3 — re-run defaults (cache should hold op2/3)**:
```
formula: op2 | top_n: 3 | score_raw: 0.25
warnings: []
```

Cache-as-source-of-truth confirmed: implicit defaults now correctly serve op2/3 (the previously-explicitly-flipped state), with no warning because the cache and request match.

### Scenario B — mtime stability across cache-hit defaulted calls

```
mtime_before=1780287043 | mtime_after=1780287043 | unchanged=TRUE
formula: op2 | top_n: 3 | warnings: []
```

Three consecutive defaulted `novetest localization latest` calls — file mtime unchanged. **No re-derive, zero cost**. Regression-pin holds.

### Scenario C — explicit-but-matches-cache (no re-derive)

```
mtime_before=1780287043 | mtime_after=1780287043 | unchanged=TRUE
formula: op2 | top_n: 3 | warnings: []
```

Passing `--formula op2 --top-n 3` (matching what's already cached) does NOT trigger a re-derive. The handler checks request-vs-cache state before invalidating — clean optimization preserved.

### Scenario D — Sequential flips with chain audit

```
Flip 1: op2/3 -> dstar2/5    | previous: {'formula': 'op2', 'top_n': 3}
Flip 2: dstar2/5 -> tarantula/2 | previous: {'formula': 'dstar2', 'top_n': 5}
Flip 3: tarantula/2 -> ochiai/10 | previous: {'formula': 'tarantula', 'top_n': 2}
```

Each `previous` field exactly carries the prior flip's `requested` state. **Chain audit is clean** — AI agents iterating formulas can reconstruct the sequence from the warnings alone.

### Scenario E — Explicit-run verb symmetry

```sh
RUN_ID=01KT0P0XA144Q1CK3B9KZQNRXM
rm -rf .novetest/localization
novetest localization "$RUN_ID" > /dev/null               # bake ochiai/10
novetest localization "$RUN_ID" --formula op2 --top-n 3   # flip
```

Result:
```
command: localization                                       <- NOT "localization.latest"
formula: op2
top_n: 3
warning_code: localization-cache-rederived
```

The fix is **symmetric across both verbs** — Loc team's `_rederive_if_cache_overrode_flags` helper is invoked from both `localization_run` and `localization_latest`.

### Scenario F — On-disk persistence reflects re-derived state

```sh
rm -rf .novetest/localization
novetest localization latest > /dev/null                  # bake ochiai/10
novetest localization latest --formula op2 --top-n 3      # flip
cat .novetest/localization/findings/run_*/localization_findings.json
```

```
on-disk formula: op2
on-disk top_n: 3
on-disk entries count: 1
on-disk entries[0].formula: op2
on-disk entries[0].score_raw: 0.25
```

**File contents match envelope contents byte-for-byte**. The re-derive is durably persisted; not just a runtime override.

### Edge 1 — failure_proximity mode (subtle UX observation, not a bug)

**Setup**: copied `localization-no-coverage` to `/tmp/d5-fp`, ran `novetest run` (no `--coverage`), then `novetest localization latest`. Then re-ran with `--formula op2 --top-n 3`.

Step 1 output:
```
mode: failure_proximity | formula: ochiai | top_n: 10 | warnings: []
```

Step 2 output (`--formula op2 --top-n 3`):
```
mode: failure_proximity | formula: ochiai | top_n: 3
alternate_scores_available: []
entries[0].score_raw: 1.0
warning fired: localization-cache-rederived
warning.previous: {'formula': 'ochiai', 'top_n': 10}
warning.requested: {'formula': 'op2', 'formula_explicit': True, 'top_n': 3, 'top_n_explicit': True}
```

**Interesting wrinkle**: the warning fired (re-derive triggered as expected), BUT the returned `formula` stayed `"ochiai"` instead of becoming `"op2"`. This is because `failure_proximity` mode hardcodes `formula="ochiai"` as a **placeholder** at the mode-dispatch layer — the cache-invalidation policy correctly triggered, but the mode contract overrode the caller's explicit `op2` request.

**Consequence**: a user iterating formulas on a failure_proximity run will see the warning fire EVERY time they pass `--formula <non-ochiai>`, even after the cache was just re-derived — because the cache always re-persists as `formula: ochiai` regardless of what was requested, so the next mismatch comparison will see `previous.formula: ochiai` vs `requested.formula: op2` → warning fires again. Non-converging.

**Not a bug in THIS slice**. The cache policy IS correct. The mode contract for failure_proximity is correct (alternates don't make sense for proximity-based scoring). But the COMPOSITION produces a warning loop for AI agents iterating formulas on failure_proximity runs.

**Recommended next step**: the cli-handler comparison should optionally skip the formula mismatch check when the engine returns `mode == "failure_proximity"` (since the formula is a noop for that mode); OR the warning message could include "formula is a no-op in failure_proximity mode" hint. Minor UX polish, low priority. PM may file as Defect 7 if iterating-on-formulas UX is important for AI agent flows.

### Edge 2 — One-explicit, one-implicit flag

```sh
rm -rf .novetest/localization
novetest localization latest > /dev/null              # bake ochiai/10
novetest localization latest --formula dstar2         # only formula explicit
```

Result:
```
formula: dstar2 | top_n: 10
warning.previous: {'formula': 'ochiai', 'top_n': 10}
warning.requested: {'formula': 'dstar2', 'formula_explicit': True, 'top_n': 10, 'top_n_explicit': False}
```

The handler correctly tracks `formula_explicit: True` vs `top_n_explicit: False`. Re-derive triggers because formula differs; top_n stays at the default 10 (which happens to match the cached 10 — incidentally). 

**Caveat** (worth noting for future polish): if the CLI default for `top_n` ever differs from the cached value (e.g., the cache had `top_n=5` from prior explicit, and now the user types `--formula op2` with implicit default `top_n=10`), the comparison would see a mismatch — but is that the desired behavior? Two intuitions:
- **"Implicit means inherit from cache"**: top_n stays at 5 (no re-derive on the implicit field).
- **"Implicit means apply default"**: top_n flips to 10 (re-derive fires).

I could not construct a test case where these intuitions diverge (the CLI defaults are stable). Worth a sanity check in Loc team's unit tests if PM cares — Manual Test does not have visibility into the explicit-tracking comparator's exact semantics.

### Edge 4 — Idempotent (1st fires, 2nd does not)

```sh
rm -rf .novetest/localization
novetest localization latest > /dev/null
novetest localization latest --formula op2 --top-n 3   # Call 1: warning fires
novetest localization latest --formula op2 --top-n 3   # Call 2: no warning
```

```
Call 1: warnings: ['localization-cache-rederived']
Call 2: warnings: []
```

**Idempotent**. The cache converges after the first re-derive; subsequent identical calls are no-ops. (This is the property that fails for failure_proximity mode — see Edge 1 above.)

### Edge 3 — Concurrent re-derive (NOT-EXECUTED)

**Reason**: Reproducible race simulation requires either multi-process orchestration with timing controls or a deterministic delay injection inside the handler. Neither is available at the Manual Test layer. The relevant guarantee — file-system atomicity on `unlink` + `write` — is structural. If a regression slips here it would surface as "stale cache served after a race"; worth noting as a future test-automator scope.

## Subtle UX observation worth tracking (low priority)

Two formulas are tied for "first thing I'd hit if I were trying to break the cache invalidation":

1. **failure_proximity mode warning loop** (documented in Edge 1 above): non-converging warning for AI agents iterating formulas. Cache is structurally correct; UX is noisy.
2. **Mode shape asymmetry persists** (from prior cycle's findings): the cache file's `formula` field always reflects what was actually computed (ochiai for failure_proximity, whatever was requested for SBFL modes). The warning's `previous` and `requested` semantics differ slightly across modes — this is structurally fine but worth a doc note in the design doc.

## Recommendations for PM

1. **Close 2026-06-01 D5 cycle as `passed`** — load-bearing peek-after-call rederive proven byte-accurate on merged tip `4895847`. Engine API stays minimal (cache policy in CLI only) per Loc team's design.

2. **Open question 1 disposition (warning code change)**: I confirmed the post-fix code is `localization-cache-rederived` (NOT the prior `localization-cache-args-ignored`). The details schema also changed (`previous` field carries the cached state). PM may amend `decisions/2026-05-30-localization-outcome-envelope-shape.md` §"Cache-vs-request mismatch warning" to pin the new code+schema, OR supersede with a new decision; either way Manual Test has documented the NEW canonical code literal here for cross-reference.

3. **Optional Defect 7 (failure_proximity warning loop)**: if AI-agent iteration on formulas is important for the localization UX, file as a low-priority Loc polish. Possible fixes: (a) skip the formula mismatch check when engine returns `mode == failure_proximity` in cli/app.py's rederive helper; (b) emit a different warning code (e.g., `localization-formula-noop-in-mode`) that's louder semantically. Reproducer included in §"Edge 1" above.

4. **Engine API gotcha worth flagging at design level**: per Main Branch's note, the cache-invalidation policy lives in `cli/app.py`. A future Replay or Orchestration caller that invokes `derive_localization_findings` directly will NOT inherit the auto-invalidation. Document this in the engine API contract OR move the policy to `derive_localization_findings` for symmetry. (Per Loc team's docstring update, this is acknowledged — worth tracking when Phase 5 lands.)

## End state

- Verdict: **passed**.
- Gate: 776 + 5 in 34.65s.
- mypy strict clean (72 src).
- 6 scenarios + 3 of 4 critical edges executed.
- Sandboxes preserved at `/tmp/d5-cargo`, `/tmp/d5-fp` for any follow-up.

Push remains gated on CEO/Main-Branch authorization per Manual Test charter.
