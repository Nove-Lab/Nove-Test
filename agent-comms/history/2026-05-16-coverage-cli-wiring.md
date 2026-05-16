---
from: novetest-pm-team
to: all
type: history
status: resolved
created: 2026-05-16
slug: coverage-cli-wiring
---

# History: `--coverage` wiring (Phase 2 entry — second wave)

Single-slice cycle: Orchestration team wired `--coverage` end-to-end on
`novetest run`, closing Phase 2 DoD #1 (with a wording adjustment to "run"
since `test` is still a stub).

## Cycle summary

| Slice | Commit on main | Verdict |
|---|---|---|
| Orchestration: `--coverage` CLI flag + workflow plumbing + auto-derive + envelope projection | `10300bb` | passed — cleanest slice merge in this project's life per Manual Test |

## What closed

- **Phase 2 DoD #1 ticked** with text adjusted from
  `novetest test --coverage` to `novetest run --coverage`. Rationale:
  `test` verb remains a stub pending Phase 6 recommendation synthesizer
  + alias work; user-experienced value (structured per-test coverage via
  a single CLI command) is delivered today through `run --coverage`. When
  `test` is promoted to a real handler later (Phase 6), it will alias to
  this same path and the DoD will be doubly satisfied — no re-edit
  needed.
- **`data.coverage_outcome` envelope shape v1 frozen** in
  `agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md`.
  Discriminator `kind: "fact-set" | "unavailable"` + per-kind required
  fields + omission-not-null rule.

## What stayed open

- Phase 2 DoD #2 (`coverage show` / `coverage diff` verbs) — natural
  next slice. Will exercise the `kind: "unavailable"` branch end-to-end
  at the CLI surface for the first time.
- Phase 2 DoD #3 (`inspect` Coverage section) — follows DoD #2.
- Phase 2 DoD #4 (NFR-COV-002 50k-location perf) — needs a perf fixture
  proposal + `performance-engineer` recruit.
- Phase 0 DoD #1, #2, #3 — Release team's GHA observation cycle still
  running in parallel; tracked separately, will close in its own
  cleanup.

## Load-bearing learnings

### 1. Cyclopts 4.11 alias pattern — `Annotated[bool, Parameter(name=[...])]`

For boolean flags with a short alias, the canonical Cyclopts 4.11 form
is:

```python
coverage: Annotated[bool, Parameter(name=["--coverage", "-c"])] = False
```

This emits a single canonical help entry
(`--coverage -c --no-coverage`). The alternative `alias="-c"` keyword on
the `Parameter` constructor also works but produces two separate help
entries — less polished UX. Future CLI verb authors (especially
`coverage show` / `coverage diff` / `inspect` authors) should default to
the `name=[...]` form.

### 2. `uv run --with novetest` env doesn't include dev-deps

When a user consumes `novetest` as a wheel via `uv run --with novetest`,
only runtime deps are pulled. The `pytest-cov` / `pytest-json-report` /
`coverage[toml]` triple that the pytest adapter assumes is NOT in the
user's venv. Inside CI / dev work this is invisible because the dev
venv has all three.

The current envelope handles this gracefully:
`errors[0].code == "adapter-missing-plugin"` with a structured
`install_hint`. But the hint names only the first-noticed missing plugin
(`pytest-cov`); a user would iterate N times to install all three.

**Follow-up for any future getting-started doc:** name the dev-deps
triple verbatim once. Don't make users discover them one error at a
time.

### 3. `capsys` vs monkeypatching `sys.stdout` in CLI unit tests

When unit-testing a Cyclopts handler that emits via
`emit_envelope(...) → print(...)`, use pytest's `capsys` fixture, NOT
`monkeypatch.setattr(sys, "stdout", StringIO())`. Pytest's own capture
mechanism already redirects stdout; a second monkeypatch on top of it
silently fights with pytest's restore logic — the envelope still emits
but lands in pytest's capture target, not your `StringIO`. First-attempt
debugging is painful because nothing logs an error.

Discovered during `tests/unit/cli/test_run_cmd.py` authoring. Worth a
note for any future CLI handler unit test author (especially the
upcoming `coverage show` / `coverage diff` verb slices).

### 4. Verification-doc signature staleness — third occurrence

Manual Test caught a third instance of stale verification-doc signatures
this cycle: `data.memory_entry.run_reference.run_id` was the doc's
suggested envelope path, but the actual nesting is
`data.memory_entry.entry_id` (or
`data.memory_entry.run_record.run_reference.run_id`). A user copy-pasting
the verification command hits `KeyError`.

Past two occurrences: `compare_coverage_facts` and `run_pytest`
signatures in the previous cycle's verifications. Pattern is now
recurrent enough to warrant a structural response.

**PM action items** (carried forward to next cycle's monitoring):

- Main Branch verification template should pin envelope/API paths from
  a freshly-loaded run, not from memory or the task spec.
- PM should spot-review verification docs before they reach Manual Test
  (one extra step, ~5 min, catches this class of bug at zero cost).
- If 4th stale-signature occurrence happens in the next cycle, escalate
  to structural fix (test-the-doc smoke that exercises the verification
  commands verbatim).

## Process notes

- **Cleanest slice merge to date** per Manual Test's closing assessment.
  Single fast-forward, no conflicts, no surprises, 9 new tests, mypy
  clean, all 5 verification scenarios + 6 edge cases pass.
- **Cross-charter touch in `run/engine.py` worked smoothly.** PM
  pre-authorized Option A in the task spec; Orchestration documented
  the touch in the handoff; Run team raised no objection. Pattern is
  reusable: for narrow signature extensions where the underlying kwarg
  is already-extant in the adjacent module, PM can grant cross-charter
  authorization in the task itself rather than serializing through a
  prep slice.
- **Manual Test surfaced an unreachable-branch test gap** — the
  `kind: "unavailable"` projection is locked by a unit test but cannot
  be exercised end-to-end via any user-typed command today. The natural
  cure is the next slice (`coverage show`) which has a valid path to
  hit it. PM tracks this as a known gap, not a defect.

## Follow-ups carried forward (PM queue)

1. **Next slice candidate (recommended):** `coverage show` / `coverage diff`
   CLI verbs. Closes Phase 2 DoD #2. The handler can lean on
   `coverage.get_coverage_facts` / `coverage.compare_coverage_facts`
   directly; envelope projection extends the now-frozen
   `coverage_outcome` shape from
   `decisions/2026-05-16-coverage-outcome-envelope-shape.md`. First
   slice where `kind: "unavailable"` becomes reachable end-to-end.
2. **Phase 2 DoD #3 — `inspect` Coverage section.** Composes Memory +
   Coverage + (future) Regression + Localization + Replay. Sized small
   if scoped to Coverage only.
3. **Phase 2 DoD #4 — NFR-COV-002 50k-location perf.** Needs a perf
   fixture proposal first. PM recruits `performance-engineer` when this
   slice approaches.
4. **Getting-started doc (deferred until docs surface exists).** Dev-deps
   triple (`pytest-json-report`, `pytest-cov`, `coverage[toml]`) needed
   for `--coverage` smoke when consuming `novetest` as a wheel.
5. **Verification-doc discipline.** PM spot-review next verification
   before Manual Test pickup. If 4th stale-signature occurrence happens,
   escalate to structural fix.
6. **Release GHA observation cycle (in flight, separate cleanup).** Still
   running in parallel; will close Phase 0 DoD #1, #2, #3 when complete.

## References

Transient comms files (task, handoff, verification, findings) deleted in
the same commit as this entry; commit `10300bb` is the authoritative
source-diff anchor.

Permanent decisions touched or created this cycle:

- `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` —
  referenced; the persisted shape this slice now hits end-to-end.
- `agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md` —
  NEW; freezes the envelope projection of that shape.
