---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-05-30
slug: localization-cache-mismatch-warnings
related:
  - agent-comms/history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
  - src/novetest/cli/app.py
  - src/novetest/cli/output.py
  - src/novetest/localization/derive.py
---

# Task: emit envelope-level `warnings[]` when `novetest localization` cache-hit ignores CLI-passed `--formula` / `--top-n`

## TL;DR

`novetest localization <run_id>` and `novetest localization latest` currently
return cached `LocalizationFinding` data when a previous run already derived
findings for the resolved run — **silently ignoring** the CLI-passed
`--formula` and `--top-n` flags if they differ from the cached values. Manual
Test surfaced this as Issue §2 in
`findings/manual-test-team-2026-05-29-orchestration-localization-cli.md`.
The resolution agreed at cycle close (history file §"Localization CLI slice
raised three issues") is **Option B**: emit a warning rather than re-derive,
so the cache-as-source-of-truth contract holds AND the user receives a clear,
actionable signal.

You add ONE envelope-level warning emission path. You DO NOT change the
`localization_outcome` block shape, DO NOT change cache-hit return values,
DO NOT change cache invalidation rules. Existing 12/9/6/3-key
`LocalizationFinding` shape and the `kind ∈ {"fact-set", "unavailable"}`
discriminator stay byte-identical.

## Scope (what this slice DOES)

1. **Detect cache-vs-request mismatch** in the orchestration layer for both
   `novetest localization <run_id>` and `novetest localization latest`.
   "Mismatch" means: cached findings exist AND the user explicitly passed
   `--formula` and/or `--top-n` AND the passed value differs from the cached
   value. If the user did not pass the flag (Cyclopts default in effect), no
   mismatch is detected for that flag.
2. **Emit a single `EnvelopeWarning`** (top-level envelope `warnings`) with
   the code, message shape, and details payload pinned below.
3. **Return the cached findings unchanged** in `localization_outcome.data`.
   Cache is still source of truth; the warning is the disclosure channel.
4. **Add unit tests** covering: mismatch on `--formula` only; mismatch on
   `--top-n` only; mismatch on both; match-passthrough (no warning); user
   omitted the flag (no warning); no cache exists (no warning, fresh
   derivation proceeds with passed flags).
5. **Add one integration test** in `tests/integration/cli/test_localization_e2e.py`
   that runs `novetest localization latest --formula dstar2` after a
   prior `novetest localization latest` that defaulted to ochiai on the
   `localization-branch` fixture, asserts the warning appears in the JSON
   envelope verbatim, and asserts the cached ochiai findings are returned
   unchanged.

## Out of scope (what this slice does NOT do)

- **No envelope-shape freeze decision document.** PM authors
  `agent-comms/decisions/2026-05-30-localization-outcome-envelope-shape.md`
  at cycle close, pinning all five items from history §"What the next cycle
  is" (12/9/6/3-key shape; `kind` discriminator; cache-vs-request mismatch
  warning shape from THIS slice; `REASON_NO_RUN_EVIDENCE` semantic
  boundaries; bogus-run_id → `not-found` routing). You produce the
  implementation; PM pins the contract.
- **No `localization_outcome.warnings[]` block-level slot.** The warning
  lives at the top-level envelope `warnings` tuple (existing
  `Envelope.warnings: tuple[EnvelopeWarning, ...]` at
  `src/novetest/cli/output.py:52`). Do NOT introduce a parallel per-block
  warnings slot — the top-level slot is the canonical channel and the freeze
  will cite this design.
- **No cache invalidation logic change.** Cache-as-source-of-truth holds.
  Re-deriving on mismatch would silently churn artifacts and contradict the
  v1 contract. The `details` payload (below) explicitly tells the user how
  to override (delete the cache).
- **No change to bogus-run_id routing.** Issue §1 from the same findings
  doc is already resolved (Option A — `not-found` envelope error); PM pins
  the boundary in the freeze decision. You do not touch that code path.
- **No change to existing `localization_outcome` keys, key ordering, or
  `kind` discriminator values.** Freeze cites them byte-identical to current
  output of commit `385e2dc`.

## Concrete file map (pinned)

| File | Line(s) | Role |
|---|---|---|
| `src/novetest/cli/app.py` | 749-784 | `localization_run()` Cyclopts handler — branch where you detect mismatch and pass warning into envelope |
| `src/novetest/cli/app.py` | 786-811 | `localization_latest()` Cyclopts handler — same as above |
| `src/novetest/cli/app.py` | 814-837 | `_localization_outcome_payload()` — DO NOT MODIFY (this is the keys/discriminator surface the freeze pins) |
| `src/novetest/cli/output.py` | 36-43 | `EnvelopeWarning` dataclass — use as-is |
| `src/novetest/cli/output.py` | 46-63 | `Envelope` dataclass and `Envelope.warnings: tuple[EnvelopeWarning, ...]` slot — use as-is |
| `src/novetest/localization/derive.py` | 140-147 | cache-hit branch that loads `cached_raw` via `read_localization_findings_raw()` and returns `LocalizationFinding.from_dict(cached_raw)` without comparing CLI args — you LIFT the comparison into the orchestration layer (do not push it into `derive.py`; engine stays pure) |
| `tests/unit/cli/test_localization.py` | — | unit tests for `localization_run()` |
| `tests/unit/cli/test_localization_latest.py` | — | unit tests for `localization_latest()` |
| `tests/integration/cli/test_localization_e2e.py` | — | E2E test (add ONE new case) |

The orchestration layer's mismatch comparison can live inline in the two
Cyclopts handlers OR in a small helper module under
`src/novetest/orchestration/` if you prefer encapsulation. Either is
acceptable; pick the form that minimizes new surface area. Do NOT add the
comparison inside `src/novetest/localization/derive.py` — `derive.py` is the
engine and stays unaware of CLI argument provenance.

## Warning contract (PIN VERBATIM — the freeze decision will cite this)

The warning is emitted to the **top-level envelope `warnings` tuple** (i.e.,
`Envelope.warnings = (EnvelopeWarning(...),)`), NOT inside the
`localization_outcome` data block.

### `code`

```
localization-cache-args-ignored
```

(kebab-case; consistent with project warning/error code style.)

### `message`

Format string with placeholders filled at runtime:

```
requested --formula='{requested_formula}' --top-n={requested_top_n} but cached findings were derived with --formula='{cached_formula}' --top-n={cached_top_n}; delete cache (.novetest/localization/findings/<run_id>/findings.json) and re-run to override
```

Notes:
- The exact phrase "delete cache and re-run to override" is from the history
  file §"Cache-hit silent-ignore"; the parenthesized path hint is a clarity
  add — it points the user at the concrete artifact to remove.
- If only one of `--formula` or `--top-n` differs, the message MUST still
  list both as `requested` and `cached`. The mismatch detection is per-flag,
  but the user-facing message gives full context.
- If the user passed only `--formula` (no `--top-n`), `requested_top_n`
  reflects the value the engine actually used (Cyclopts default); same for
  the other direction. This keeps the message a complete narrative of
  request-vs-cache.

### `details`

```python
{
    "requested": {
        "formula": str,           # e.g., "dstar2"
        "top_n": int,             # e.g., 5
        "formula_explicit": bool, # True if user passed --formula; False if defaulted
        "top_n_explicit": bool,   # True if user passed --top-n; False if defaulted
    },
    "cached": {
        "formula": str,           # primary formula recorded in cached LocalizationFinding
        "top_n": int,             # entry count or top-n recorded in cached LocalizationFinding
    },
    "cache_path": str,            # relative path from project root, e.g., ".novetest/localization/findings/<run_id>/findings.json"
}
```

The `_explicit` booleans are critical for AI consumers — they let downstream
agents distinguish "user explicitly asked for X but got Y" from "user took
the default and the cache happens to differ" (the latter is also worth
warning about, but the agent may treat it differently).

## DoD (definition of done for this slice)

- [ ] `Envelope.warnings` includes ONE `EnvelopeWarning` with the pinned
      shape when, for either `localization` verb, cached findings are
      returned AND at least one of `--formula` / `--top-n` differs.
- [ ] No warning is emitted when cached findings are returned and both
      flags match the cached values.
- [ ] No warning is emitted when no cache exists (fresh derivation path
      proceeds with passed flags as before).
- [ ] No warning is emitted when the user omitted both flags (Cyclopts
      defaults in effect AND those defaults happen to match the cached
      values — the common no-op re-inspect case).
- [ ] Unit tests cover the six branches enumerated in Scope §4.
- [ ] One integration test added to
      `tests/integration/cli/test_localization_e2e.py` covering the
      end-to-end re-inspect-with-different-formula scenario on
      `localization-branch`.
- [ ] `localization_outcome` block bytes are unchanged for the cache-hit
      path (only `warnings` at the envelope level changes).
- [ ] `mypy --strict` on touched files; ruff clean.
- [ ] Full test suite green (`uv run pytest -q`).

## Coordination notes

- The CLI command file `src/novetest/cli/app.py` is also touched by the
  Orchestration team's `inspect` aggregator code, but no other team has
  in-flight changes there in this cycle (INDEX is clean as of 2026-05-30).
  Coordinate with no one on this slice.
- This is the **5th application of the project's `engine → CLI → freeze`
  cadence**: 1) regression-outcome v1, 2) localization-finding-shape v1,
  3) localization-finding-shape v2 (top-n key rename), 4) regression-facts
  layout, 5) localization-outcome envelope (this cycle). PM writes the
  freeze decision at cycle close after your handoff lands; you do NOT write
  it.

## Handoff format

When your worktree is ready to merge, write:

```
agent-comms/handoffs/orchestration-team-2026-05-30-localization-cache-mismatch-warnings.md
```

The handoff MUST include:

1. **DoD bullets believed closed**: which of the 9 DoD checkboxes above
   you consider satisfied (PM verifies and ticks at cycle close — you do
   not tick `delivery-phasing.md` yourself).
2. **Phase 4 §4 implications**: this slice does NOT close any
   `delivery-phasing.md` Phase 4 §4 DoD bullet directly (those are #2
   modes + #3 perf, both untouched here), but the warning shape becomes
   load-bearing for any future Localization slice that touches the
   envelope.
3. **Commit SHA(s)** and a one-paragraph summary of what changed.
4. **Test counts**: unit / integration / total; how many new tests this
   slice adds.
5. **Open questions for PM**: anything you encountered that the freeze
   decision should clarify but this brief did not anticipate.

## End-of-work checklist (per PM charter)

Per `CLAUDE.md` §Multi-Agent Coordination Harness and your team charter:

1. Append `WORKLOG.md` entry per format.
2. Write the handoff (above).
3. Run `python3 tools/regen_comms_index.py` to refresh `INDEX.md`.
4. Stage `WORKLOG.md`, the new `agent-comms/` files, and `INDEX.md`
   alongside source. The `PreToolUse` hook will block the commit if any
   of `src/` or `tests/` is staged but `WORKLOG.md` is not.
