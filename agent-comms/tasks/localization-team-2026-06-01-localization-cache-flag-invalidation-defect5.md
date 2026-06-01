---
from: novetest-pm-team
to: novetest-localization-team
type: task
status: pending
created: 2026-06-01
slug: localization-cache-flag-invalidation-defect5
related:
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
  - src/novetest/localization/derive.py
  - src/novetest/localization/persistence.py
---

# Task: Localization — re-derive when CLI flags differ from cached state (Defect 5)

## TL;DR

`novetest localization <run_id> --formula X --top-n N` (and same for
`latest`) **silently ignores `--formula` / `--top-n` flags** when a
findings cache file already exists for the run. The cache-read path
returns the persisted findings verbatim regardless of what flags the
caller passes; first call's flags get baked in forever (until manual
cache delete).

Manual Test root-cause-localized empirically: the flag-handling logic
itself works (post-cache-delete probe applies flags correctly). The
bug is purely **cache invalidation**: the cache should re-derive when
the requested flags differ from what's baked into the persisted file.

Surgical fix: ~10 lines in the orchestration localization workflow
(or `derive_localization_findings`) — compare requested
`(formula, top_n)` against persisted `(formula, top_n)`; on mismatch,
re-derive instead of cache-read.

## Why this slice exists (product framing)

Users (especially AI agents) trying alternate SBFL formulas without
deleting the cache get a misleading "your flag was applied" envelope
where the `formula` field still says `"ochiai"` (the cached value).
The envelope looks consistent — no error, no warning — so the bug is
invisible at the wire layer.

This is also a **5th occurrence of "Localization cache silently
returns stale data"** symptom. Last cycle a similar issue with the
2026-05-30 `localization-cache-args-ignored` warning fixed the
*disclosure* (now the wire envelope emits a warning); this slice
fixes the *behavior* (re-derive instead of warn-and-return-stale).

After this slice: explicit flags always take effect. Either via
re-derive on mismatch, or via clearer error if the implementing team
decides that's the right contract (see §"Design choice" below).

## Empirical reproduction (verbatim from Manual Test 2026-06-01 findings)

```sh
cp -r tests/fixtures/projects/localization-aggregate-only /tmp/d5-repro
cd /tmp/d5-repro
. "$HOME/.cargo/env"
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run --coverage >/dev/null 2>&1

# Call 1: implicit default → ochiai, top_n=10 baked into persisted file
novetest localization latest > /dev/null

# Call 2: explicit op2, top_n=3 → SHOULD apply, but does NOT
novetest localization latest --formula op2 --top-n 3 | grep -E '"formula"|"top_n"'
#   "formula": "ochiai"        ← BUG: flag silently dropped
#   "top_n": 10                ← BUG: flag silently dropped

# Proof flag-handling logic works (cache layer is the bug):
rm -rf .novetest/localization
novetest localization latest --formula op2 --top-n 3 | grep -E '"formula"|"top_n"'
#   "formula": "op2"           ← post-cache-delete, flag applied
#   "top_n": 3                 ← post-cache-delete, flag applied
```

Pre-fix: `score_raw: 0.5` (Ochiai math) regardless of explicit flag.
Post-cache-delete with `--formula op2 --top-n 3`: `score_raw: 0.25`
(Op2 math: `1 - 3/(0+3+1) = 0.25`). The flag handling produces correct
math — just doesn't fire when cache exists.

## Design choice — re-derive vs error

Two reasonable behaviors when explicit flags differ from cached:

### Option A — Re-derive (recommended)

When `--formula` or `--top-n` is explicitly passed AND differs from
the persisted file's stored values, re-derive findings with the new
flags and persist the new state (replacing the old cache).

Pros: matches user intent; AI agents iterating on formulas get
correct math each call.

Cons: re-derive can be expensive on large fixtures (Phase 4 §4 #3
perf NFR is `500 failed × 50k locations < 8s` — not free). But this
is the same cost the user explicitly opted into by passing the
flag.

### Option B — Error with clear message

When mismatch detected, return an envelope error like
`"requested formula 'op2' differs from cached 'ochiai'; pass
--rederive or delete cache"`.

Pros: no implicit re-compute; user explicitly opts in.

Cons: extra friction; AI agents will need to handle the error code
and retry; the warning channel already exists (the 2026-05-30
`localization-cache-args-ignored` warning) — adding an error path
on top is redundant.

**PM recommendation: Option A (re-derive)** — matches the existing
warning emission (warn on mismatch but still return cached) by
fixing the actual behavior. The implementing team can decide
whether to KEEP the warning + add re-derive (warn user that
re-derive happened, useful for audit) or DROP the warning (since
re-derive eliminates the inconsistency that the warning surfaced).

## Scope (what this slice DOES)

### 1. Detect flag mismatch on cache hit

In the orchestration layer's `localization` workflow (or in
`derive_localization_findings` if cache-read is internal there),
when a cached findings file exists:

1. Read persisted `formula` and `top_n` from the file.
2. Compare against requested `formula` and `top_n`:
   - If both NULL on input (caller didn't pass flags): use cached
     verbatim (current behavior — no change).
   - If either passed AND differs from cached: trigger re-derive
     path (Option A).

### 2. Re-derive on mismatch

Call `_derive_per_test` / `_derive_aggregate` /
`_derive_failure_proximity` (same dispatcher as the cache-miss
path) with the new flags. Persist the new findings (overwriting
the cache). Return the freshly-derived envelope.

### 3. Tests

- **Unit**: in `tests/unit/localization/` (or
  `tests/unit/orchestration/` if the cache-handling lives there),
  add tests pinning:
  1. Cache hit + no flags → cached returned (regression-pin)
  2. Cache hit + same flags → cached returned (regression-pin)
  3. Cache hit + different `--formula` → re-derive triggered,
     new findings returned, persisted file overwritten
  4. Cache hit + different `--top-n` → same
  5. Cache hit + both flags different → same
- **Integration**: extend `tests/integration/cli/test_localization_e2e.py`
  (or analogous) with ONE case that:
  1. Initial call with defaults persists ochiai/top_n=10
  2. Second call with `--formula op2 --top-n 3` re-derives and
     returns op2/top_n=3 findings
  3. Persisted file now reflects op2/top_n=3

### 4. (Optional) decide on warning channel

The existing `localization-cache-args-ignored` warning (envelope
top-level `warnings[]`) was added 2026-05-30 to disclose the
silent-ignore. After this slice's re-derive fix, the warning is
either:
- (a) **OBSOLETE** — re-derive eliminates the mismatch; no warning
  needed.
- (b) **STILL USEFUL** — emit a different warning code like
  `localization-cache-rederived` to inform the user that a
  re-derive happened (so they know they paid the re-compute cost).

Implementer's call. (a) is simpler; (b) is more transparent. PM has
no strong opinion.

## Out of scope (do NOT touch)

- **`retrieval.py`** (Defect 4 gate) — already correct as of
  `4b5fd1d`.
- **The SBFL formula implementations** (`sbfl/ochiai.py` etc) —
  unchanged.
- **`_derive_aggregate`, `_derive_failure_proximity`, `_derive_per_test`**
  — already work correctly. The bug is in the cache-handling layer
  ABOVE the dispatcher.
- **Defect 6** (status.sub_reports staleness) — parallel sibling
  slice, separate orchestration-team territory.
- **Phase 4 §4 #3 perf NFR** — separate slice.

## Pre-flight checks

1. **Full gate green** on equipped host:
   `uv run pytest -q tests/unit tests/integration`
   - Baseline tip (`97285e5` + post-Defect-4 `4b5fd1d`): **762 + 5**
     on equipped host.
   - Your tip = baseline + new tests. No regressions.
2. **mypy strict clean**: 72 source files (unchanged; this slice
   should add no src files).
3. **Empirical smoke** — reproduce Defect 5 pre-fix, then confirm
   post-fix:
   ```sh
   # Pre-fix: --formula silently dropped after cache hit (see
   #          Manual Test reproduction above)
   # Post-fix: --formula triggers re-derive; envelope returns op2
   ```

## DoD

- [ ] Cache-handling code path detects flag mismatch on cache hit.
- [ ] On mismatch with explicit flags, re-derive + persist new
      findings (Option A).
- [ ] Cached-read regression-pin: same flags → still cached.
- [ ] 5 unit tests + 1 integration test (per §3).
- [ ] Decision on warning channel (§4) — documented in handoff.
- [ ] Full pytest suite green; mypy strict clean.
- [ ] No `delivery-phasing.md` checkbox movement (bug fix, not
      phase-tracked).

## Handoff format

Standard at
`agent-comms/handoffs/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md`.
MUST include:

1. DoD bullets believed closed.
2. Pre-flight empirical proof: paste the verbatim shell session
   showing pre-fix vs post-fix behavior (the Manual Test reproduction
   above is the template).
3. Warning channel decision (kept / dropped / replaced).
4. Open questions for PM.

## Cross-references

- **Origin of Defect 5 + empirical reproduction**:
  `agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md`
  §"Defect 5 surfaced".
- **Related cache-warning slice** (2026-05-30):
  `agent-comms/decisions/2026-05-30-localization-outcome-envelope-shape.md`
  §"Cache-vs-request mismatch warning" — the warning's existence
  is the disclosure surface; this slice fixes the underlying
  behavior.
- **Sibling Defect 6 slice (independent, parallel-dispatchable)**:
  `agent-comms/tasks/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md`.
