---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-06-23
slug: command-surface-licenses-enumeration
related:
  - agent-comms/history/2026-06-22-novetest-licenses-cli-verb.md  # parent cycle (#2b)
---

# `command_surface.py` enumeration for `licenses` — close the top-level discoverability gap

## Mission

Add a single `CommandSpec(name="novetest licenses", ...)` entry to
`src/novetest/orchestration/onboarding/command_surface.py::_OPERATING`,
then regenerate the protected snapshot
`tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr`.

This closes the **Nit #1 surfaced by Manual Test on 2026-06-22** (see
`agent-comms/history/2026-06-22-novetest-licenses-cli-verb.md` §"Load-
bearing learning #4"): the `licenses` verb is fully operational, but
`novetest --help --output json` does NOT enumerate `licenses` in
`data.operating`, so AI agents discovering the command surface
programmatically miss it. This atomic 1-commit cycle closes that gap.

The parent cycle's brief explicitly deferred this work because it
forbade `.ambr` regen of `test_help_envelope_no_store`. This cycle is
**dedicated** to that regen — the snapshot edit is the entire point,
NOT a side-effect.

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md` — project-wide rules.
2. `.claude/agents/novetest-orchestration-team.md` — your charter.
3. `agent-comms/history/2026-06-22-novetest-licenses-cli-verb.md`
   — parent cycle context, esp. §"Load-bearing learning #4" (the gap
   you are closing) and §"What landed" (verb shape).
4. `src/novetest/orchestration/onboarding/command_surface.py` — the
   file you edit. 153 lines, single `_OPERATING` tuple of 14 entries.
   `_ONBOARDING` tuple holds 3 entries (`--version`, `--help`, `init`).
5. `tests/integration/cli/test_help_envelope_no_store.py` — the test
   whose snapshot you regen.
6. `tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr`
   — the file you regen (do NOT hand-edit; use `--snapshot-update`).

## Scope (CEO-confirmed)

This is a focused 1-commit atomic cycle:
- 1 src/ file MOD (`command_surface.py`)
- 1 snapshot file MOD (`test_help_envelope_no_store.ambr`)
- 0 new tests (snapshot regen IS the test)
- 0 decision docs, 0 README touch, 0 `pyproject.toml`

Karpathy "Surgical Changes" applies maximally — `git diff main`
should show exactly 2 files modified, nothing else.

## Data contract (PIN VERBATIM)

### New `CommandSpec` entry

```python
CommandSpec(
    name="novetest licenses",
    summary="List third-party components Nove Test redistributes or links to.",
    group="orchestration",
    available_in_phase=0,
),
```

### Field rationale (pinned)

| Field | Value | Why |
|---|---|---|
| `name` | `"novetest licenses"` | Mirrors the existing `_OPERATING` entry naming convention (subcommand path prefixed with `novetest `). |
| `summary` | `"List third-party components Nove Test redistributes or links to."` | One-sentence, ≤80 chars, matches `licenses_cmd` docstring's first sentence in `cli/app.py`. |
| `group` | `"orchestration"` | Matches the parent verb's territorial owner. Existing groups in the file: `onboarding`, `run`, `memory`, `orchestration`, `coverage`, `regression`, `localization`, `replay`. `licenses` is a meta/info verb that Orchestration team owns (cli/ + orchestration/licenses/). |
| `available_in_phase` | `0` | The verb does NOT require a Project Store (no `.novetest/` dependency); like `--version` and `--help`, it works on any clean working directory at any phase. Phase 0 marks "available since foundations." |

### Placement in `_OPERATING`

Append to the **end** of the tuple (after `replay`):

```python
_OPERATING: tuple[CommandSpec, ...] = (
    # ... existing 14 entries ...
    CommandSpec(
        name="novetest replay",
        summary="Re-execute a stored run and classify reproducibility.",
        group="replay",
        available_in_phase=5,
    ),
    CommandSpec(
        name="novetest licenses",
        summary="List third-party components Nove Test redistributes or links to.",
        group="orchestration",
        available_in_phase=0,
    ),
)
```

**Why end-of-tuple**: matches the "newest-at-end" convention the file
has accumulated (verbs are added in chronological order, NOT
alphabetical or strict-phase-sorted). No reordering — the protected
snapshot would diff more invasively if existing entries shuffled.

### Resulting `data.operating` shape

After regen, `novetest --help --output json` envelope's
`data.operating` list grows from 14 entries to **15** entries, with
the new entry at index 14 (last). All 14 existing entries remain
byte-identical (same name/summary/group/availableInPhase values, same
order).

`data.onboarding` unchanged (3 entries).
`schemaVersion` unchanged (`1`).
`schema` (top-level) unchanged (`"novetest/v1"`).

## Files to write / modify

### 1. MODIFY — `src/novetest/orchestration/onboarding/command_surface.py`

Append the new `CommandSpec` to the `_OPERATING` tuple per "Placement"
above. Single addition, no reorder of existing entries.

### 2. MODIFY (via `--snapshot-update`) — `tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr`

Regenerate via syrupy:

```bash
uv run pytest tests/integration/cli/test_help_envelope_no_store.py --snapshot-update
```

Then **immediately re-run without `--snapshot-update`** to verify the
new snapshot stabilizes:

```bash
uv run pytest tests/integration/cli/test_help_envelope_no_store.py
```

Must pass without further regen. Inspect `git diff` on the .ambr to
confirm the diff is **additive only** (one new `licenses` entry; zero
modifications to existing entries).

## Files NOT to touch

- `src/novetest/cli/app.py` — already registers `licenses_cmd`; do not
  re-edit.
- `src/novetest/orchestration/licenses/__init__.py` — already pins
  `LICENSE_ENTRIES`; do not re-edit.
- `src/novetest/cli/renderers/licenses.py` — text renderer; do not
  re-edit.
- Any other `.ambr` snapshot — do not regen other snapshots; if any
  other test triggers `--snapshot-update`, that's a regression. Run
  `git status --porcelain | grep ambr` after regen — should show
  exactly 1 modified `.ambr` file (the one above).
- `NOTICES.md` — frozen.
- `pyproject.toml` — frozen.
- README — frozen.
- `agent-comms/decisions/**` — accumulate forever.

## Verification commands (must-pass before reporting done)

```bash
# 1. mypy --strict GREEN (no new modules; should match 112 source files baseline)
uv run mypy --strict src/novetest

# 2. Full suite GREEN (snapshot count may shift by +N if your snapshot regen
#    creates additional snapshot files; pass count should be ≥ baseline 1327)
uv run pytest -q tests/unit tests/integration

# 3. Snapshot stability — re-run without --snapshot-update
uv run pytest tests/integration/cli/test_help_envelope_no_store.py
# Must pass; no further regen needed.

# 4. Empirical CLI smoke — licenses appears in data.operating
uv run novetest --help --output json | python3 -c "
import sys, json
e = json.load(sys.stdin)
op = e['data']['operating']
assert len(op) == 15, f'Expected 15 operating entries, got {len(op)}'
licenses_entries = [c for c in op if c['name'] == 'novetest licenses']
assert len(licenses_entries) == 1, f'Expected exactly 1 licenses entry, got {len(licenses_entries)}'
spec = licenses_entries[0]
assert spec['summary'] == 'List third-party components Nove Test redistributes or links to.'
assert spec['group'] == 'orchestration'
assert spec['availableInPhase'] == 0
print('OK: licenses enumerated at index', op.index(spec), 'of', len(op))
"

# 5. Existing entries unchanged — byte-identity for the 14 pre-existing entries
uv run novetest --help --output json | python3 -c "
import sys, json
e = json.load(sys.stdin)
op = e['data']['operating']
expected_existing = ['novetest test', 'novetest run', 'novetest memory list',
                     'novetest memory show', 'novetest memory delete',
                     'novetest inspect', 'novetest status', 'novetest coverage show',
                     'novetest coverage diff', 'novetest regression compare',
                     'novetest regression latest', 'novetest compare',
                     'novetest localization', 'novetest replay']
got_existing = [c['name'] for c in op[:14]]
assert got_existing == expected_existing, f'Existing entries reordered! Expected {expected_existing}, got {got_existing}'
print('OK: 14 pre-existing entries in original order')
"

# 6. Surgical scope check
git diff main --name-only
# Must print exactly these 2 lines:
#   src/novetest/orchestration/onboarding/command_surface.py
#   tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr
```

## Definition of Done (7 bullets — PM ticks at cycle close)

- [ ] **#1 `CommandSpec` appended** — 15th entry at end of `_OPERATING`
      tuple in `command_surface.py`; 4 fields verbatim per "Data
      contract" §"New CommandSpec entry".
- [ ] **#2 Snapshot regenerated** — exactly 1 `.ambr` file modified
      (`test_help_envelope_no_store.ambr`); diff is additive only (no
      pre-existing entries reordered/modified).
- [ ] **#3 No new tests** — `git diff main --name-only` shows exactly 2
      files (the two above).
- [ ] **#4 mypy --strict GREEN** — 112 source files unchanged.
- [ ] **#5 Full suite GREEN** — pytest pass count ≥ 1327 baseline
      (from 2026-06-22 verification at HEAD `438eb71`); snapshot count
      may grow by 0 (regen-in-place) or +1 (depending on syrupy
      bookkeeping).
- [ ] **#6 Envelope contract verified** — verification command #4 +
      #5 above both print OK.
- [ ] **#7 Charter discipline held** — no `src/novetest/cli/`,
      `src/novetest/orchestration/licenses/`, `NOTICES.md`,
      `pyproject.toml`, or `README.md` touch.

## Karpathy guidelines (mandatory invocation)

Before editing any file in `src/` or regenning the snapshot, invoke
the `andrej-karpathy-skills:karpathy-guidelines` skill via the Skill
tool. Apply all four:

1. **Think Before Coding** — confirm placement (end-of-tuple), fields
   verbatim, regen mechanism (`--snapshot-update`), zero collateral
   damage to other snapshots or tests.
2. **Simplicity First** — one `CommandSpec` append. No refactor of
   `_OPERATING` to a registry pattern. No new helper. No new group.
   No `licenses`-specific docstring on `describe_command_surface()`.
3. **Surgical Changes** — exactly 2 files in diff. Run `git status
   --porcelain` before staging — confirm scope.
4. **Goal-Driven Execution** — DoD #6 (envelope shows the entry) is
   the binding empirical gate. Verify before handoff.

## Reporting back to PM (in your handoff)

Standard handoff at `agent-comms/handoffs/orchestration-team-2026-06-23-command-surface-licenses-enumeration.md`. Include:

- "DoD bullets believed closed" list (cite each).
- Verbatim output of verification commands #4 and #5 (empirical proof
  of envelope contract).
- `git diff main --name-only` output (verbatim 2 lines).
- `git status --porcelain | grep ambr` output (verbatim 1 line — the
  regenned snapshot).
- Confirmation that running pytest WITHOUT `--snapshot-update` after
  the regen still passes (snapshot stability).

## Parallel cycle awareness

**Zero other cycles in flight** as of brief authoring (INDEX shows all
transient channels empty). No file-footprint coordination needed.

If a Marketing PM cycle starts in parallel: zero overlap — Marketing PM
edits `design/website-plan/` only; this cycle edits `src/` + `tests/`.

## Estimated effort

| Step | Time |
|---|---|
| Read 5 pre-flight files | ~15 min |
| Append `CommandSpec` (1 edit) | ~2 min |
| Regen snapshot + verify stability | ~5 min |
| Run verification commands 1-6 | ~3 min |
| Draft handoff | ~10 min |
| Total | **~35 min wall time** |

Karpathy "Goal-Driven Execution" applies — DoD is unambiguous, so the
loop is tight.

## Why this matters

1. **AI agents discovering Nove Test programmatically can now find
   `licenses` via the canonical surface** (`novetest --help --output
   json`), without needing to consult README or release notes.
2. **The "every verb must be enumerable in top-level surface"
   invariant holds again** — Manual Test's Nit #1 was the only
   exception to this invariant; closing it eliminates a future "the
   user/agent doesn't know X exists" defect class.
3. **Atomic cycle pattern reaffirmed** — this is the cleanest possible
   1-commit cycle (2 files, 1 verb, 1 snapshot). Future "one-line
   completion of a deferred follow-up" cycles can use this brief as a
   template.

The cycle closes a 2-day-old surface gap with maximal surgical
precision. Mechanical work, low risk, high signal (validates the
"deferred follow-up resolution" pattern for future cycles).
