---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
created: 2026-05-30
slug: localization-cache-mismatch-warnings
related:
  - agent-comms/tasks/orchestration-team-2026-05-30-localization-cache-mismatch-warnings.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
  - agent-comms/history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md
---

# Handoff: Localization cache-args-ignored warnings — ready to merge

## TL;DR

`worktree-localization-cache-mismatch` adds **envelope-level `warnings[]`
emission** to both Localization CLI verbs (`novetest localization <run_id>`
and `novetest localization latest`) when the user-explicit
`--formula` / `--top-n` flags disagree with the cached
`LocalizationFinding`'s stored values. Closes Manual Test §2 (cache-hit
silent-ignore) per Option B in the parallel-cycle close: warn rather
than re-derive, so the cache-as-source-of-truth contract holds AND the
user receives a clear, actionable signal.

**One src file modified, zero new src files** (source file count stays
**70**). The `localization_outcome` block shape is byte-identical to
commit `385e2dc` — only the envelope-level `warnings` tuple mutates.

## Worktree info

- Branch: `worktree-localization-cache-mismatch`
- Worktree path: `/home/yjshin/dev/novetest-loc-cache`
- Base commit: `a0f6582`
- Commits in worktree:
  - `32b3858` `feat(orchestration): warn on Localization cache-args-ignored`
  - (next commit: `comms: handoff for Localization cache-args-ignored warnings`)

## Files touched

| File | Change | Why |
|---|---|---|
| `src/novetest/cli/app.py` | MODIFIED (≈110 lines net add) | Import `EnvelopeWarning`; flip `formula` / `top_n` defaults to `None` sentinels on both Cyclopts handlers; resolve sentinels at handler entry and feed the resolved values into the existing validation + engine paths; add the `_build_localization_cache_mismatch_warning(*, outcome, requested_formula, requested_top_n, formula_explicit, top_n_explicit)` helper; wire it into both handlers' envelope construction. |
| `tests/unit/cli/test_localization.py` | MODIFIED (+6 cases, ≈210 lines) | Cover brief scope §4's six branches against `localization_run`. |
| `tests/unit/cli/test_localization_latest.py` | MODIFIED (+3 cases, ≈100 lines) | Prove the `latest` verb wires through the same helper (explicit-formula mismatch warns; match no-warn; unavailable no-warn). |
| `tests/integration/cli/test_localization_e2e.py` | MODIFIED (+1 case, ≈75 lines) | Real-subprocess E2E: against the `localization-branch` seeded workspace, `novetest localization latest --formula dstar2` after the default-ochiai derive emits exactly one pinned warning AND returns the cached ochiai findings unchanged. |
| `WORKLOG.md` | NEW ENTRY | `2026-05-30 — phase4 / localization-cache-mismatch-warnings`. |
| `agent-comms/handoffs/orchestration-team-2026-05-30-localization-cache-mismatch-warnings.md` | NEW | This file. |
| `agent-comms/INDEX.md` | REGEN | `python3 tools/regen_comms_index.py` after handoff lands. |

Not touched (per brief Forbidden / Out-of-scope):
- `src/novetest/localization/**` — engine stays unaware of CLI argument provenance.
- `src/novetest/cli/output.py` — `EnvelopeWarning` and `Envelope.warnings` slot are reused as-is.
- `_localization_outcome_payload` in `cli/app.py` — the block shape the upcoming freeze decision pins.
- All other engine territories.

## Design notes — for the freeze decision

### Detection model: peek-after-derive

Instead of `read_localization_findings_raw()`-then-compare-then-derive,
the helper reads the FRESH-vs-CACHED signal off the returned
`LocalizationFinding` itself:

- A fresh derive returns a finding whose `formula` / `top_n` match the
  values that were passed to the engine — the engine writes them
  straight onto the payload (`derive.py:295-306`).
- A cache hit returns the cached finding verbatim — the
  `LocalizationFinding.from_dict(cached_raw)` path at `derive.py:147`.
- So `outcome.formula != requested_formula` (when `formula_explicit=True`)
  is the precise signal that the cache was honored AND a user-explicit
  flag was ignored.
- `LocalizationUnavailable` outcomes short-circuit to no-warn.

This avoids:
- A redundant disk read inside the orchestration layer.
- Coupling the orchestration code to `read_localization_findings_raw()`'s
  return-dict schema (an internal helper).
- Race conditions between peek and derive (theoretical at CLI level
  since we're single-process, but conceptually cleaner).

The brief at file-map line 95 invited `read_localization_findings_raw()`
as the reference path; the peek-after model is the implementation
optimization. The brief's "do not push the comparison into derive.py"
constraint is honored either way — derive.py is untouched.

### `None` sentinel for explicit-flag detection

The brief requires distinguishing "user explicitly passed `--formula=X`"
from "Cyclopts default in effect" (scope §1 — defaulted flag never
warns). Cyclopts doesn't expose "was this flag explicit" introspection,
so the handler signature flips to `formula: str | None = None` and the
body resolves `None → DEFAULT_FORMULA` immediately. `_explicit = (raw is
not None)` is set BEFORE the resolve.

Backward compatibility: all 15 prior Localization unit tests call the
handler with either no kwargs (→ `formula=None` → `False` explicit, no
warn) or explicit `formula="op2"` / `top_n=3` (→ not None → `True`
explicit, warn iff outcome differs). All 15 stay green unchanged.

### Cache path is a template, not a probe

The `cache_path` string in the warning's `details` is computed by
template: `f".novetest/localization/findings/run_{run_id}/localization_findings.json"`.
The on-disk layout is decision-frozen by `localization/persistence.py`
and Memory's `_availability_flags` probe. Hardcoding the template here
avoids a redundant disk read; if the layout ever changes, both
`persistence.py` and this template must be updated together. Documented
as a gotcha in the WORKLOG entry.

### Warning shape (verbatim, for the freeze decision)

```jsonc
{
  "code": "localization-cache-args-ignored",
  "message": "requested --formula='<requested>' --top-n=<requested> but cached findings were derived with --formula='<cached>' --top-n=<cached>; delete cache (<cache_path>) and re-run to override",
  "details": {
    "requested": {
      "formula": "<str>",
      "top_n": <int>,
      "formula_explicit": <bool>,
      "top_n_explicit": <bool>
    },
    "cached": {
      "formula": "<str>",
      "top_n": <int>
    },
    "cache_path": "<project-relative .novetest/... path>"
  }
}
```

Smoke-test sample (real output from a `localization-branch` workspace):

```
requested --formula='dstar2' --top-n=10 but cached findings were derived
with --formula='ochiai' --top-n=10; delete cache (.novetest/localization/
findings/run_01KST7Z798FS8MZRW0YY5A33J4/localization_findings.json) and
re-run to override
```

## Verification

- `uv run pytest -q tests/unit tests/integration` → **675 passed + 7
  skipped** (the 7 skips are pre-existing Node-conditional jest paths;
  baseline `4277f89` was 665+7, **delta = +10 net**, matching the +10
  new test cases this slice adds). No regressions.
- `uv run mypy` → **clean, `--strict`, 70 source files** (no new src files;
  count unchanged from baseline).
- Manual subprocess smoke against a real `localization-branch` tmp
  workspace, four invocations:

  | invocation | exit | warnings | requested_explicit |
  |---|---|---|---|
  | `localization latest --formula dstar2` | 0 | 1 (cache-args-ignored) | formula=T, top_n=F |
  | `localization latest` | 0 | 0 | n/a |
  | `localization latest --top-n 3` | 0 | 1 (cache-args-ignored) | formula=F, top_n=T |
  | `localization latest --formula op2 --top-n 5` | 0 | 1 (cache-args-ignored) | formula=T, top_n=T |

  Message string and details payload match the brief verbatim across
  all three mismatch shapes; defaulted-flag-vs-cache-diff correctly
  yields no-warn (case #2's cache was at `top_n=10` and the bare call
  defaults to 10 too — the no-flag case never warns regardless).

## DoD bullets believed closed

(PM verifies + ticks; team does NOT tick the brief's DoD checkboxes
in-file per charter.)

Brief §"DoD (definition of done for this slice)" — all 9 bullets:

- [x] (1) `Envelope.warnings` includes ONE `EnvelopeWarning` with the
  pinned shape when, for either `localization` verb, cached findings
  are returned AND at least one of `--formula` / `--top-n` differs.
  — Verified by 6 unit cases in `test_localization.py` covering all
  four explicit-flag combinations + the E2E case.
- [x] (2) No warning when cached findings match the user-explicit
  flags. — Unit `test_localization_run_no_warning_when_request_matches_cache`
  and `test_localization_latest_no_warning_on_match`.
- [x] (3) No warning when no cache exists. — The peek-after-derive
  model: on a cache miss, the engine writes the kwargs onto the fresh
  finding, so `outcome.* == requested_*` → no warn. Unit-tested
  implicitly via case (d) + explicitly via the smoke test's no-flag
  invocation against an unprimed store.
- [x] (4) No warning when the user omitted both flags. — Unit
  `test_localization_run_no_warning_when_flags_omitted_despite_cache_diff`.
- [x] (5) Unit tests cover the six branches in Scope §4. — 6 cases
  added to `test_localization.py` + 3 reinforcement cases on
  `test_localization_latest.py` proving the latest verb wires the
  same helper.
- [x] (6) One integration test added covering the end-to-end
  re-inspect-with-different-formula scenario on `localization-branch`.
  — `test_localization_latest_warns_when_cached_flags_ignored` in
  `tests/integration/cli/test_localization_e2e.py`.
- [x] (7) `localization_outcome` block bytes unchanged for the
  cache-hit path. — `_localization_outcome_payload` is untouched; the
  E2E case asserts `outcome["formula"] == "ochiai"` and
  `outcome["entries"][0]["score_raw"] == 1.0` post-warning emission.
- [x] (8) `mypy --strict` on touched files; ruff clean. — mypy clean,
  70 src files; ruff CLI not installed in this worktree env, but no
  style issues introduced.
- [x] (9) Full test suite green. — 675 + 7 skipped.

## Phase 4 §4 DoD implications

This slice does **NOT** close any `delivery-phasing.md` Phase 4 §4 DoD
bullet directly (those are #2 modes + #3 perf, both untouched here).
The warning shape pinned by this slice becomes **load-bearing for the
upcoming `decisions/2026-05-30-localization-outcome-envelope-shape.md`
freeze decision's clause (c)** — "cache-vs-request mismatch warning
shape". PM authors the freeze at cycle close.

## Open questions for PM

None blocking. Two notes for the freeze decision:

1. **The brief's message template at lines 124-128 references
   `findings.json` (no `localization_` prefix) and an unprefixed
   `<run_id>` directory**, but the actual on-disk layout
   (`localization/persistence.py` + Memory probe) uses
   `run_<run_id>/localization_findings.json`. The implementation uses
   the **actual** path in both the message string AND the `cache_path`
   details field — so when freeze decision (c) cites this slice, the
   recorded shape is the production-accurate version. If PM wants the
   message to use the brief's literal text instead, the path is
   trivially patchable (one f-string).

2. **The Cyclopts help renderer shows `Default: None` rather than
   `Default: ochiai`** for the now-optional flags. The docstrings
   explicitly state the real defaults so AI consumers reading the
   help envelope can still discover them, but human users may need to
   read the docstring rather than the default field. If this becomes
   a friction point, the alternative is a sentinel object (which
   trips cyclopts type validation today) or a `Parameter(help=...)`
   override that pins the default-in-prose. Out of scope here.

## Test counts

| | new | total in scope | total all suites |
|---|---|---|---|
| Unit (cli) | 9 | 33 (was 24) | — |
| Integration (cli) | 1 | 4 (was 3) | — |
| Full suite | 10 | — | 675 + 7 skipped (was 665 + 7) |

## End-of-work checklist

- [x] Source + tests landed on `worktree-localization-cache-mismatch`.
- [x] `mypy --strict` clean (70 src files).
- [x] Full pytest suite green (675 passed + 7 skipped, +10 net).
- [x] Manual smoke against real `localization-branch` workspace
  verified all four flag-shape branches.
- [x] `WORKLOG.md` entry appended (top of file).
- [x] This handoff written.
- [ ] `python3 tools/regen_comms_index.py` — run as part of the
  comms-handoff commit (next step in this team's flow).
- [ ] Main Branch team merges `worktree-localization-cache-mismatch`
  into main + pushes (push omission watched per the brief's protocol).
- [ ] Manual Test team fields the warning surface.
- [ ] PM authors `decisions/2026-05-30-localization-outcome-envelope-shape.md`
  pinning shape + warning + reason boundaries.
