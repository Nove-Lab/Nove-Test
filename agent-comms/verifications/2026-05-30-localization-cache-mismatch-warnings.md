---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
slug: localization-cache-mismatch-warnings
created: 2026-05-30
related:
  - agent-comms/handoffs/orchestration-team-2026-05-30-localization-cache-mismatch-warnings.md
  - agent-comms/tasks/orchestration-team-2026-05-30-localization-cache-mismatch-warnings.md
  - agent-comms/findings/manual-test-team-2026-05-29-orchestration-localization-cli.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
---

# Verification: Localization cache-args-ignored warnings

## Merged commits

- `5fa2381` — `feat(orchestration): warn on Localization cache-args-ignored`
- `73141a0` — `comms: handoff for Localization cache-args-ignored warnings`

Rebased onto `64f7bd9` (Manual Test cargo E2E sweep queue) for clean linear
history. Zero conflicts during rebase — divergent main commit was pure comms
(INDEX.md + a new task brief); the worktree's INDEX delta auto-merged.
Fast-forward merge into `main`.

## Source handoff consumed

- `agent-comms/handoffs/orchestration-team-2026-05-30-localization-cache-mismatch-warnings.md`
  (orchestration-team, 2026-05-30).

## Scope of the slice

Closes Manual Test §2 (cache-hit silent-ignore) from
`findings/manual-test-team-2026-05-29-orchestration-localization-cli.md`
per Option B chosen in the parallel-cycle close: **warn rather than
re-derive**, so the cache-as-source-of-truth contract holds AND the user
receives a clear, actionable signal.

- Both Localization CLI verbs (`novetest localization <run_id>` and
  `novetest localization latest`) now emit an envelope-level
  `warnings[]` entry with code `localization-cache-args-ignored` when
  the user-explicit `--formula` / `--top-n` flags disagree with the
  cached `LocalizationFinding`'s stored values.
- `--formula` and `--top-n` defaults shift to `None` sentinels at the
  handler signature; resolved to `DEFAULT_FORMULA="ochiai"` /
  `DEFAULT_TOP_N=10` immediately. Explicit-vs-defaulted detection is via
  the `None` sentinel.
- `localization_outcome` block bytes are **byte-identical** to commit
  `385e2dc` — only the envelope-level `warnings` tuple changes.
  `_localization_outcome_payload` was not touched.
- `inspect <run_id>` was **not** modified; it never invokes the warning
  helper, so `inspect` envelopes still carry an empty `warnings: []`.

**Detection model — "peek-after-derive".** Instead of reading the cache
file first, the handler lets `derive_localization_findings` /
`derive_latest_localization` return either a fresh-derive or a cache-hit
`LocalizationFinding`, then compares `outcome.formula` / `outcome.top_n`
against the user's requested values. A fresh derive always matches
(engine writes the request straight onto the payload); a cache hit
returns the cached values verbatim. Detection is therefore implicit and
the engine code is untouched.

## Test-gate result on the merged tip

```
uv run pytest -q tests/unit tests/integration → 675 passed, 7 skipped
uv run mypy                                    → Success: no issues found in 70 source files (strict)
```

The 7 skips are pre-existing env-conditional integration tests (Node /
jest paths + Rust / cargo paths). Baseline `64f7bd9` was 665+7 → **+10
net** new tests, matching the handoff's claim of +6 unit / +3
latest-reinforcement / +1 integration.

## Wire shapes pinned by inspecting the merged code

All shapes below are pinned by `grep` against the merged source at
`src/novetest/cli/app.py:855-927` (`_build_localization_cache_mismatch_warning`)
AND independently validated end-to-end by the integration test
`tests/integration/cli/test_localization_e2e.py:254-316`
(`test_localization_latest_warns_when_cached_flags_ignored`), which
passed in the gate run above.

### Envelope top-level shape (sort_keys=True → alphabetic in JSON)

```json
{
  "command": "localization" | "localization.latest",
  "data": { "localization_outcome": { ... } },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": [
    {
      "code": "localization-cache-args-ignored",
      "message": "<see below>",
      "details": { ... }
    }
  ]
}
```

Key facts to copy/paste into your scenario commands:

- `warnings` is at the **envelope top level**, NOT inside `data`. The
  outcome under `data.localization_outcome` is unchanged from the
  385e2dc baseline.
- Exactly **one** warning entry per mismatched invocation. Multiple
  mismatched flags (formula+top_n) still produce a single warning whose
  message and details cover both.
- `outcome.formula` / `outcome.top_n` reflect the **cached** values
  (i.e. what the cache was originally derived with), NOT the requested
  values. This is the desired behavior — the cache is the source of
  truth; the warning surfaces that your request was honored only as a
  request and the cached values won out.
- Exit code is **0** (warning, not error). Warnings never set
  `ok: false`.

### Warning message (verbatim format string, `src/novetest/cli/app.py:906-910`)

```
requested --formula='{requested_formula}' --top-n={requested_top_n} but cached findings were derived with --formula='{cached_formula}' --top-n={cached_top_n}; delete cache ({cache_path}) and re-run to override
```

Concrete sample after a default-ochiai derive followed by
`localization latest --formula dstar2`:

```
requested --formula='dstar2' --top-n=10 but cached findings were derived with --formula='ochiai' --top-n=10; delete cache (.novetest/localization/findings/run_<RUN_ID>/localization_findings.json) and re-run to override
```

### Warning details (verbatim, `src/novetest/cli/app.py:914-926`)

```json
{
  "requested": {
    "formula": "<requested str>",
    "top_n": <requested int>,
    "formula_explicit": <bool>,
    "top_n_explicit": <bool>
  },
  "cached": {
    "formula": "<cached str>",
    "top_n": <cached int>
  },
  "cache_path": ".novetest/localization/findings/run_<RUN_ID>/localization_findings.json"
}
```

- `requested.formula_explicit` / `requested.top_n_explicit` are gating
  signals — when `false`, that flag's mismatch alone never triggers the
  warning. The warning's existence implies AT LEAST ONE explicit flag
  triggered the comparison.
- `cache_path` is a **template-computed** project-relative path. The
  handler does NOT probe disk for the file. If you delete the cache
  file at this path (or `rm -rf .novetest/localization/`) and re-run
  the verb, the warning will not fire (cache miss → fresh derive →
  outcome matches request).
- `requested.formula` / `requested.top_n` are the **resolved** values
  after the `None`-sentinel resolution. So if you pass `--formula
  dstar2` without `--top-n`, `requested.top_n == 10` (the default), but
  `requested.top_n_explicit == false`.

## Verification scenarios — for Manual Test

All scenarios use the same setup. The fastest reproduction path
mirrors `tests/integration/cli/test_localization_e2e.py`'s module-scoped
fixture (a single seeded ochiai-derived store reused across scenarios).

### Setup (run once)

```bash
# Pick a tmp workspace
WORKSPACE=$(mktemp -d -t novetest-loc-warn-XXXX)
cp -r tests/fixtures/projects/localization-branch "$WORKSPACE/loc-branch"
cd "$WORKSPACE/loc-branch"

# Initialize Project Store + run pytest with per-test coverage
uv run --project /home/yjshin/dev/Nove-Test novetest init
uv run --project /home/yjshin/dev/Nove-Test novetest run --coverage tests/

# Capture the run_id for later scenarios
RUN_ID=$(uv run --project /home/yjshin/dev/Nove-Test novetest memory list --output json | jq -r '.data.runs[0].run_reference.run_id')
echo "RUN_ID=$RUN_ID"

# Seed the cache with default ochiai by calling latest verb once with no flags
uv run --project /home/yjshin/dev/Nove-Test novetest localization latest --output json | jq '.data.localization_outcome.formula'
# → "ochiai"  (cache primed)
```

### Scenario 1 — `latest` with mismatched `--formula` only (handoff §smoke row 1)

```bash
uv run --project /home/yjshin/dev/Nove-Test novetest localization latest --formula dstar2 --output json
```

Assertions to copy:
- `.ok == true`, exit code `0`.
- `.data.localization_outcome.formula == "ochiai"` (the cache, NOT
  `dstar2`).
- `.warnings | length == 1`.
- `.warnings[0].code == "localization-cache-args-ignored"`.
- `.warnings[0].details.requested.formula == "dstar2"`.
- `.warnings[0].details.requested.formula_explicit == true`.
- `.warnings[0].details.requested.top_n_explicit == false`.
- `.warnings[0].details.cached.formula == "ochiai"`.
- `.warnings[0].details.cached.top_n == 10`.
- `.warnings[0].details.cache_path` ends with
  `/run_${RUN_ID}/localization_findings.json`.

### Scenario 2 — `latest` with mismatched `--top-n` only (handoff §smoke row 3)

```bash
uv run --project /home/yjshin/dev/Nove-Test novetest localization latest --top-n 3 --output json
```

Same assertions but inverted explicit flags: `formula_explicit ==
false`, `top_n_explicit == true`, `requested.top_n == 3`, `cached.top_n
== 10`.

### Scenario 3 — `latest` with BOTH flags mismatched (handoff §smoke row 4)

```bash
uv run --project /home/yjshin/dev/Nove-Test novetest localization latest --formula op2 --top-n 5 --output json
```

Single warning still emitted. `formula_explicit == true`,
`top_n_explicit == true`, both `requested.*` and `cached.*` populated.
Message string contains BOTH requested and cached values.

### Scenario 4 — `latest` with no flags (control: no warning)

```bash
uv run --project /home/yjshin/dev/Nove-Test novetest localization latest --output json | jq '.warnings'
# → []
```

`.warnings == []`. Outcome is the cached ochiai.

### Scenario 5 — Explicit-run verb with mismatch

```bash
uv run --project /home/yjshin/dev/Nove-Test novetest localization "$RUN_ID" --formula tarantula --output json
```

Same envelope structure as `latest`, only `command == "localization"`
instead of `localization.latest`.

### Scenario 6 — Cache-clearing roundtrip (cache miss → no warning → re-prime)

```bash
rm -rf .novetest/localization/
uv run --project /home/yjshin/dev/Nove-Test novetest localization latest --formula dstar2 --output json | jq '{warnings, fmt: .data.localization_outcome.formula}'
# → {"warnings": [], "fmt": "dstar2"}    (fresh derive, dstar2 honored, no warning)

# Re-run with same flag → still no warning (cache now matches request)
uv run --project /home/yjshin/dev/Nove-Test novetest localization latest --formula dstar2 --output json | jq '.warnings'
# → []
```

Demonstrates the brief's promise: "delete cache and re-run to override"
in the warning's message is literal and works.

### Scenario 7 — `inspect` is unaffected

```bash
uv run --project /home/yjshin/dev/Nove-Test novetest inspect "$RUN_ID" --output json | jq '.warnings'
# → []
```

`inspect` reads from cache via `get_localization_findings` and never
constructs a request, so the warning helper is unreachable from this
path. Confirms slice scope was honored.

### Scenario 8 — Defaulted-only-vs-cache-diff is silent (the §1 §3 contract)

After seeding cache at `--top-n 3` (delete cache first to re-seed):

```bash
rm -rf .novetest/localization/
uv run --project /home/yjshin/dev/Nove-Test novetest localization latest --top-n 3 --output json | jq '.warnings'
# → []  (cache now at top_n=3)

uv run --project /home/yjshin/dev/Nove-Test novetest localization latest --output json | jq '.warnings'
# → []  (top_n_explicit=false → no warn even though cached top_n=3 ≠ default 10)
```

Defaulted flag never warns even if cached value differs.

## Critical edge cases worth probing

1. **`localization` with `--formula INVALID` mismatch path.** Brief
   §4 case (e): invalid flag short-circuits to exit-2 `invalid-flag`
   BEFORE the engine runs. The warning helper is never called. Try
   `novetest localization "$RUN_ID" --formula nonsense` and confirm
   `.ok == false`, exit `2`, `.errors[0].code == "invalid-flag"`,
   `.warnings == []`. The validation guard precedes the derive call —
   see `_validate_localization_flags` invocation at
   `cli/app.py:783` / `:831`.

2. **`localization-cache-args-ignored` warning on a tombstoned run.**
   Tombstoned runs surface `LocalizationUnavailable` (not
   `LocalizationFinding`) → the helper returns `None` →
   `.warnings == []`. To reproduce, locate a tombstoned run via
   `memory list --include-tombstoned` and re-derive with
   `localization "$TOMBSTONED_ID" --formula op2`. Expect
   `.data.localization_outcome.kind == "unavailable"` and empty
   `warnings`.

3. **`latest` over an empty store.** `derive_latest_localization`
   returns `LocalizationUnavailable(reason="no_run_evidence",
   run_reference=None)` → helper returns `None`. Try in a fresh
   `mktemp -d` workspace with `novetest init` but no runs. Expect
   `localization_outcome.kind == "unavailable"`,
   `.warnings == []`.

4. **`cache_path` template vs reality.** The path in the warning is
   templated, not probed. The on-disk path is at
   `.novetest/localization/findings/run_<run_id>/localization_findings.json`
   (pinned by `localization/persistence.py`). After running scenario 1,
   verify the file actually exists at exactly that path — the warning
   says "delete cache (...)" and the path must match what the user can
   `ls` / `rm`.

5. **NDJSON output mode.** With
   `NOVETEST_OUTPUT=ndjson novetest localization latest --formula dstar2`,
   confirm the warning is emitted on the single NDJSON line as
   `"warnings":[{...}]` (envelope serializer uses the same
   `to_dict()` path for both pretty and NDJSON modes — see
   `cli/output.py:88-96`). This guards against the warning being lost
   on the wire for AI consumers in streaming mode.

6. **Cyclopts help shows `Default: None`.** Run `novetest localization
   --help`. Both `--formula` and `--top-n` will render `Default: None`
   in the auto-generated help (a known consequence of the `None`-sentinel
   trick). The docstrings should still state the real defaults
   ("`--formula` defaults to `'ochiai'`"). Confirm the docstrings carry
   the truth and flag this if the discrepancy seems user-hostile (the
   handoff §"Open questions for PM" item 2 calls this out as a
   freeze-decision discussion point, not a blocker).

## Notes for the freeze decision (PM pickup)

Two items flagged by the orchestration team as input for
`decisions/2026-05-30-localization-outcome-envelope-shape.md`:

1. **Brief vs implementation: cache_path layout.** The brief at lines
   124-128 references `findings.json` (no `localization_` prefix) and
   an unprefixed `<run_id>` dir. The implementation uses the **actual**
   production layout `run_<run_id>/localization_findings.json`. Manual
   Test scenarios above are pinned against the production layout.

2. **Single warning per invocation.** The current shape is "one
   warning whose details cover both flags". The freeze decision
   should confirm this vs. emitting two separate warnings (one per
   mismatched flag). Implementation pins **one**.

## End-of-Main-Branch checklist

- [x] Worktree rebased onto `main` tip (`64f7bd9`) cleanly — no
      conflicts.
- [x] Both gates green on the merged tip (`73141a0`): 675 passed + 7
      skipped, mypy strict clean across 70 source files.
- [x] Source handoff consumed.
- [x] Verification doc written (this file) with envelope shapes pinned
      to merged source AND cross-validated by the integration test.
- [x] INDEX.md regenerated and consistent post-merge.
- [ ] Push to `origin/main` after this commit (per CEO authorization
      "머지푸시진행해" in the dispatch message).
- [ ] Worktree `/home/yjshin/dev/novetest-loc-cache` removed and
      branch `worktree-localization-cache-mismatch` deleted after push.
