---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-30
slug: localization-cache-mismatch-warnings
related:
  - agent-comms/verifications/2026-05-30-localization-cache-mismatch-warnings.md
  - agent-comms/handoffs/orchestration-team-2026-05-30-localization-cache-mismatch-warnings.md
  - agent-comms/findings/manual-test-team-2026-05-29-orchestration-localization-cli.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
verdict: passed
---

# Findings: Localization cache-args-ignored warnings

## Verdict — **passed**

All 8 verification scenarios + all 6 critical edge cases were
exercised against the merged binary (`5fa2381`) on the equipped host.
The slice does exactly what the 2026-05-29 findings §2 asked for:
when the user-explicit `--formula` / `--top-n` flags disagree with
the cached `LocalizationFinding`, a precise envelope-level warning
fires while the cache-as-source-of-truth contract holds. Zero
regressions, zero envelope-shape divergences, zero functional bugs.
The "Open question 2" item in the handoff (Cyclopts help text for
`None`-sentinel flags) is a real UX issue worth pinning, but the
verification doc already flagged it as a discussion point — confirmed
here, with a sharper finding (see Edge 6).

## What this slice gives the CEO

Last cycle Manual Test surfaced a quiet trap: if a Localization
report was already cached from yesterday's run, and you re-ran
`novetest localization latest --formula dstar2` today, Nove Test
would silently hand you yesterday's `ochiai` cache instead of the
`dstar2` analysis you asked for. The cache won; the user got no
signal.

This slice closes that trap with the **gentler** of the two options
PM was weighing (per the parallel-cycle close): keep the cache as
the source of truth (which preserves the determinism + speed wins of
the cache), but emit an envelope-level `warnings[]` entry every time
the user's explicit flag was ignored. The message is actionable —
it tells the user the exact path of the cache file to delete to get
a fresh derive.

In plain language: before this slice you got the wrong answer
silently; now you still get the cached answer (because that's the
contract), but with a clear warning that says "we ignored your flag
and here's how to override it". Two reasonable shapes of "did the
right thing" coexisting in one envelope.

## Test gate (reproduced)

```
uv run pytest -q tests/unit tests/integration → 677 passed, 5 skipped
uv run mypy → Success: no issues found in 70 source files (strict)
```

The verification doc reports `675 passed + 7 skipped`. My host shows
677+5 because I had `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` set in the
shell env to work around the cargo-adapter bug surfaced in the
parallel cargo E2E sweep (see
`findings/manual-test-team-2026-05-30-cargo-e2e-sweep.md`). That env
var unlocks the 2 cargo integration tests that the doc counts as
skips → 2 cargo skips become 2 cargo passes → 5 jest/node-only skips
remain. The arithmetic checks out exactly; this slice did not
regress the gate.

## Scenarios — all 8 PASS

Setup: `mktemp -d` → `cp -r tests/fixtures/projects/localization-branch
.../loc-branch` → `novetest init` → `novetest run --coverage tests/`
→ `novetest localization latest` (to prime an ochiai cache). RUN_ID
came back as `01KST8YF06XPMZ3132R0A7J9FT`, summary
`{passed: 5, failed: 1, total: 6}` — matches the fixture intent.

### Scenario 1 — `latest --formula dstar2` → ✅

```
novetest localization latest --formula dstar2 --output json
```

- `ok: true`, exit `0` ✅
- `data.localization_outcome.formula == "ochiai"` (cache won) ✅
- `warnings.length == 1` ✅
- `warnings[0].code == "localization-cache-args-ignored"` ✅
- `requested.formula == "dstar2"`, `formula_explicit == true`,
  `top_n_explicit == false` ✅
- `cached.formula == "ochiai"`, `cached.top_n == 10` ✅
- `cache_path` ends with `/run_01KST8YF06XPMZ3132R0A7J9FT/localization_findings.json` ✅
- Message is verbatim what the format string at `cli/app.py:906-910`
  produces, including the literal `delete cache (...) and re-run to
  override` tail.

### Scenario 2 — `latest --top-n 3` → ✅

Inverted explicit flags vs Scenario 1:
- `requested.top_n == 3`, `top_n_explicit == true`
- `requested.formula == "ochiai"` (the resolved default),
  `formula_explicit == false`
- `cached.top_n == 10`
- Single warning, outcome.formula still `"ochiai"`.

### Scenario 3 — `latest --formula op2 --top-n 5` → ✅

Single warning still — covers BOTH mismatched flags. Both
`*_explicit` are `true`; both `requested.*` populated; both
`cached.*` populated. Message contains both requested AND cached
values (assertion: `"op2"`, `5`, `"ochiai"`, `10` all present in the
single message string).

### Scenario 4 — `latest` with no flags (control) → ✅

`warnings == []`. `outcome.formula == "ochiai"` (cache returned).
Proves the default no-arg path is silent — exactly what defaulted-
flag handling should do.

### Scenario 5 — explicit-run verb `localization <run_id> --formula tarantula` → ✅

Same envelope shape, `command == "localization"` (not
`localization.latest`). Confirms both handlers wire through the same
helper — Scenario 1 wasn't a coincidence of the `latest` path.

### Scenario 6 — Cache-clearing roundtrip → ✅

`rm -rf .novetest/localization/` then re-run with `--formula dstar2`:
- Round 1: `warnings == []`, `outcome.formula == "dstar2"` (fresh
  derive, the explicit flag is honored, no warning)
- Round 2 (same flag): `warnings == []`, `outcome.formula ==
  "dstar2"` (cache now matches, still no warning)

Proves the warning message's "delete cache and re-run to override"
instruction is literal and works.

### Scenario 7 — `inspect` is unaffected → ✅

`novetest inspect <run_id>` after a cache mismatch still has
`warnings == []`. `sub_reports.localization == "available"`.
`inspect` reads via `get_localization_findings`, never invokes the
helper. Slice scope correctly honored.

### Scenario 8 — Defaulted-only-vs-cache-diff is silent → ✅

After re-priming the cache with `--top-n 3`, a subsequent
no-flags `localization latest` returns the cached `top_n == 3` with
`warnings == []` (because `top_n_explicit == false`, the defaulted
resolution to 10 is not a mismatch the helper raises). This is the
§1/§3 contract: defaulted flag never warns even when the cache value
differs from the default.

## Edge cases — all 6 PASS (with one UX finding for PM, Edge 6)

### Edge 1 — `--formula INVALID` short-circuits to `invalid-flag` → ✅

```
novetest localization <id> --formula nonsense --output json
```

- exit `2`, `ok: false`
- `errors[0].code == "invalid-flag"`,
  `message == "Invalid --formula='nonsense'; expected one of ['dstar2',
  'ochiai', 'op2', 'tarantula']"`
- `warnings == []`

`_validate_localization_flags` correctly precedes the engine derive
call (see `cli/app.py:783` / `:831`). Helper never reached.

### Edge 2 — Tombstoned run silent → ✅

Tombstoned the live RUN via the Memory `delete_run_evidence` seam
(needed actual `created_at` from `record.json` to resolve — pure
API friction, not a slice issue). Then:

```
novetest localization <tombstoned_id> --formula op2 --output json
```

- `kind == "unavailable"`, `reason == "run_not_analyzable"`,
  `warnings == []`

Helper correctly returns `None` for non-`LocalizationFinding`
outcomes. (The exact `reason` is `run_not_analyzable`, not the
hypothetical `tombstoned` literal in the verification doc — the
doc said "expect kind=unavailable + empty warnings", which both
hold; the underlying reason name is engine-level detail, fine
either way.)

### Edge 3 — `latest` over an empty store silent → ✅

Fresh `mktemp` workspace, `novetest init`, no runs seeded, then
`novetest localization latest`:
- exit `0`, `kind == "unavailable"`, `reason == "no_run_evidence"`,
  `warnings == []`

Same code path — helper returns `None` when the outcome isn't a
`LocalizationFinding`. Engines correctly distinguish the two
unavailable reasons by name.

### Edge 4 — `cache_path` template matches reality → ✅

Re-seeded a clean ochiai cache, triggered the warning via
`--formula dstar2`, took the `cache_path` from the warning details
verbatim, joined to the workspace root, and checked `os.path.isfile`:

```
template: .novetest/localization/findings/run_01KST8YF06XPMZ3132R0A7J9FT/localization_findings.json
exists: True
```

The template the warning emits resolves to a real file. "delete
cache" instruction is actionable as printed.

### Edge 5 — NDJSON mode warning passthrough → ✅

```
NOVETEST_OUTPUT=ndjson novetest localization latest --formula dstar2
```

Output is exactly 1 line; parsed as JSON, `warnings.length == 1`,
`warnings[0].code == "localization-cache-args-ignored"`, full
`details` block intact including `cached.formula`. AI consumers
streaming the NDJSON envelope on stdout get the warning on the wire
with no loss.

### Edge 6 — `localization --help` shows the flags **WITHOUT** defaults
or descriptions → ⚠️ (UX finding for PM; not a blocker)

```
novetest localization --help
```

Renders:

```
╭─ Parameters ─────────────────────────────────────────────────────╮
│ * RUN-ID --run-id  [required]                                    │
│   --formula                                                      │
│   --top-n                                                        │
╰──────────────────────────────────────────────────────────────────╯
```

The verification doc predicted `Default: None` would render
(handoff §"Open questions for PM" item 2). Reality is **worse** —
Cyclopts renders neither a default nor any short description for
`--formula` / `--top-n`. The truth is in the function docstring at
`cli/app.py:771`:

> `--formula` defaults to `"ochiai"`; `--top-n` defaults to `10`.

…but that docstring is not surfaced in the Cyclopts `Parameters`
block as currently configured. A user new to this CLI gets a help
output that does not mention either accepted values for `--formula`
or the existence of a default. The `--formula` value-set lives only
in the error message you get for an INVALID value (Edge 1's
`expected one of ['dstar2', 'ochiai', 'op2', 'tarantula']`) — i.e.
"learn the API by triggering the error" UX.

The handoff already flagged this as a freeze-decision discussion
point, not a blocker. Confirmed it's worth deciding on — the
sentinel trick that makes the explicit/defaulted detection work
costs the help-text user a real amount of information. Two paths
PM might consider:
- (a) annotate each flag with explicit `Parameter(help="...",
  show_default="ochiai")` (or whatever Cyclopts equivalent), so
  the docstring truth surfaces in `--help`
- (b) accept the cost — the docs at `design/...` carry the truth;
  AI consumers query JSON envelopes, not Cyclopts help

My subjective read: (a) is the right call. Human CLI users will hit
this far more than AI consumers, and the "discover by error" UX is
hostile.

## Wire-shape conformance

All pinned shapes from the verification doc were observed verbatim:

- Envelope: `warnings` is at the top level, NOT inside `data` ✅
- Exactly **one** warning per mismatched invocation, even when
  multiple flags mismatch (Scenario 3) ✅
- `outcome.formula` / `outcome.top_n` reflect the **cached** values
  (Scenarios 1, 2, 3, 5) ✅
- Exit code is **0** on mismatch — warnings never set `ok: false`
  (all 8 scenarios) ✅
- Warning `message` format string at `cli/app.py:906-910` is the
  source of truth — observed match is byte-identical to the template
  ✅
- Warning `details` shape matches `cli/app.py:914-926` schema:
  `requested.{formula, top_n, formula_explicit, top_n_explicit}` +
  `cached.{formula, top_n}` + `cache_path` ✅
- `requested.formula` / `requested.top_n` are the **resolved**
  values post-sentinel (Scenario 1: `top_n: 10` with
  `top_n_explicit: false`) ✅
- `cache_path` is project-relative (template-computed, not
  disk-probed) AND resolves to a real file (Edge 4) ✅

## Notes for the freeze decision (PM pickup)

Both of the doc's flagged items I can vote on:

1. **`cache_path` layout — implementation wins.** The
   `run_<run_id>/localization_findings.json` layout is internally
   consistent (matches the on-disk persistence in
   `localization/persistence.py`), matches the brief once the doc is
   corrected, and the warning message itself prints the same string
   the user can copy-paste into `rm`. Pin this.

2. **One warning per invocation — keep.** Aggregating both
   mismatched flags into a single warning (Scenario 3) is the right
   call for AI consumers — they get a single decision point, not two
   that they have to correlate. Two separate warnings would also
   introduce ordering questions (does formula warn before top_n? if
   so, why?). Pin "one warning whose details cover both flags".

## Issues found

**None functional.** Edge 6 is a UX finding (no defaults / no help
text on the sentinel-pattern flags) that the handoff already flagged
as discussion-not-blocker.

## Recommendations for PM

1. **Tick the slice DoD** — closes Manual Test 2026-05-29 findings
   §2 (cache-hit silent-ignore) per Option B as planned. The
   warning shape, message format, and details schema are stable
   across all 8 + 6 probes.

2. **Open a low-priority Orchestration follow-up** to address
   Edge 6 — either annotate `--formula` / `--top-n` with Cyclopts
   `Parameter(help=..., show_default=...)` so the help text surfaces
   the docstring truth, or write a `decisions/` note explaining why
   the bare flag display is acceptable. My read: do the
   annotation; ~15 lines for ~much-better-UX.

3. **Freeze `decisions/2026-05-30-localization-outcome-envelope-shape.md`**
   with the two pinned items above (cache_path layout, single
   warning per invocation). The verification doc explicitly invited
   Manual Test's vote on these — both votes above.

4. **No source / test changes required** for this slice. Ship.

## What was tested — verbatim commands

All commands recorded under their respective Scenario / Edge
headings above. Setup used:
- `mktemp -d -t novetest-loc-warn-XXXX` as scratch workspace
- `tests/fixtures/projects/localization-branch` copied in (read-only
  in source; copy is what was mutated, per charter)
- Direct `uv run --project /home/yjshin/dev/Nove-Test novetest ...`
  invocations (matches the verification doc's pattern)

All scratch directories removed post-sweep; `git status` clean.

## Notes on protocol

Per Manual Test charter — findings doc only; no source / test
modifications; no handoff; no WORKLOG.md entry; INDEX regenerated
post-write.
