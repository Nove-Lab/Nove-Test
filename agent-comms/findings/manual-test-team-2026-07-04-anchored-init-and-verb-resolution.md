---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: resolved
created: 2026-07-04
slug: anchored-init-and-verb-resolution
related:
  - agent-comms/verifications/2026-07-04-anchored-init-and-verb-resolution.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/questions/main-branch-team-2026-07-04-windows-dotdotdot-normalization-ci-red.md
---

# Findings: anchored init + verb walk-up + pin dispatch (D1–D7 — Wave 2, 3/3)

## Verdict: **passed**

(One caveat inherited from Main Branch's addendum, not from my testing: go's
`./...` target pass-through is KNOWN-RED on Windows until the routed
fast-follow lands. This host is Linux — I cannot exercise the Win32 quirk;
all POSIX-observable behavior below is green.)

## Narrative (for the CEO)

This slice is the biggest user-facing change of the cycle: `novetest init`
now records *which* test engine the user consented to (**the pin**), every
command finds its workspace by walking **up** from wherever it is invoked
(like git does), and novetest **never again guesses** an engine at run time.
I exercised the real CLI on freshly built throwaway projects for every
outcome in the decision table: the happy path (one obvious engine → pinned
silently), the "nothing here" path (init refuses, creates **nothing**, and
politely lists sub-projects it can see), and the "two engines" path (init
refuses, creates **nothing**, and demands an explicit `--engine` choice).
All refusal paths left the filesystem untouched — that was the CEO-level
promise of this design ("novetest never initializes a directory you are not
standing in") and it holds everywhere I poked, including `$HOME`, where the
discovery scan itself is refused. Running commands from deep subdirectories
works, one-off engine overrides run without silently re-pinning, old
pin-less stores upgrade themselves invisibly, and `reset` refuses to wipe a
store it would not be able to re-create. No regressions found.

## Commands run (verbatim) + observed output

`REPO=/home/yjshin/dev/Nove-Test; PY=$REPO/.venv/bin/python` throughout;
all workspaces are fixture copies under `/tmp`.

### Anchor A — single-marker init (pytest-basic copy) ✅

```
cd /tmp/mt-a && $PY -m novetest init      # exit 0
  data.pinned_engine: {"ecosystem": "python", "engine_name": "pytest"}
$PY -m novetest status                    # exit 0, identical pinned_engine
```

### Anchor B — markerless dir, one child candidate ✅

```
cd /tmp/mt-b && $PY -m novetest init      # exit 4
  errors[0].code: no-engine-detected
  data: {"candidates":[{"ecosystem":"python","engine_name":"pytest","path":"childpy"}],"scan_refused":false}
ls -a /tmp/mt-b                           # only childpy — NOTHING created
```

Message text matched the verification anchor word-for-word, candidate path
is POSIX-form relative.

### Anchor C — dual marker, both READY ✅ (adapted: go toolchain absent on this host)

go is not installed here, so `pyproject.toml + go.mod` is NOT a both-READY
pair on this host (see Observation 1). Reproduced with a both-READY pair
(pytest + cargo-test; cargo 1.96.0 + cargo-nextest 0.9.137 present):

```
# /tmp/mt-dual = cargo-test-basic fixture + pytest-basic's pyproject/tests
cd /tmp/mt-dual && $PY -m novetest init   # exit 2
  errors[0].code: engine-ambiguous
  errors[0].message: Multiple viable engines detected (pytest, cargo-test); no Project Store was created. Choose one explicitly: `novetest init --engine <name>`.
  data.candidates: [{python/pytest, "."}, {rust/cargo-test, "."}]   # nothing created
$PY -m novetest init --engine pytest      # exit 0, pinned pytest
```

### D2 — walk-up resolution ✅

```
cd /tmp/mt-a/pytest_basic/deep/nested && $PY -m novetest status   # exit 0, parent pin resolved
cd /tmp/mt-nostore && $PY -m novetest run                          # exit 2, errors[0].code: uninitialized
```

### D3 — target semantics ✅

```
cd /tmp/mt-a/pytest_basic/deep/nested && $PY -m novetest run
  run record: target_expression '' | target_type workspace | 3 passed   # bare = workspace-scoped from any cwd
cd /tmp/mt-a && $PY -m novetest run tests/test_math_utils.py
  target_expression 'tests/test_math_utils.py' | 3 collected/passed
cd /tmp/mt-a/pytest_basic/deep/nested && $PY -m novetest run tests/test_math_utils.py
  target_expression 'tests/test_math_utils.py' | 3 collected/passed     # SAME series as the root ask ✅
```

Explicit relative targets are interpreted **anchor-relative** (the
documented D3 contract); a cwd-relative `../../../tests/test_math_utils.py`
from the subdir passes through **verbatim** (documented "we do not
pre-validate" branch) — see Observation 2 for the consequence.

### D3 — transient override, no re-pin ✅

```
cd /tmp/mt-dual && $PY -m novetest test                    # pytest pin: 3 passed
$PY -m novetest run --engine cargo-test                    # exit 3 — REAL cargo-nextest run,
  run record: engine cargo-test | 2 passed / 1 failed of 3 # exactly the fixture's contract counts
$PY -m novetest status                                     # pin STILL {"python","pytest"} ✅
```

`--engine foo` on init / run / test → `invalid-flag`, exit 2, all three. ✅

### D6 — lazy migration ✅

Stripped `pinned_engine` from `/tmp/mt-a/.novetest/store.json` by hand →
next `novetest status` exit 0, envelope shows the pin, and `store.json` has
the field silently backfilled.

### Reset semantics ✅

```
cd /tmp/mt-a/pytest_basic/deep/nested && $PY -m novetest reset --confirm  # exit 0
  → re-inited at the ANCHOR (/tmp/mt-a/.novetest; no store in the subdir); pin carried (status: pytest)
  → reset envelope has NO pinned_engine key (byte-stable, as documented — flagged below)
# legacy pin-less store at an AMBIGUOUS anchor (mt-dual copy, pin stripped):
$PY -m novetest reset --confirm                                            # exit 2
  errors[0].code: engine-ambiguous
  message: "...the store was NOT wiped. Run `novetest init --engine <name>`...then retry"
  store file count before/after: 15/15 — intact ✅
```

(Without `--confirm` reset correctly stops at `confirm-required`, exit 2 —
the 2026-06-24 destructive-verb guard still holds.)

### Edge cases ✅

- **Re-pin in place**: `init --engine cargo-test` on the pytest-pinned
  mt-dual → exit 0, pin updated, run artifacts 2→2 (history retained),
  exactly one `.novetest/` in the tree.
- **D4 bounds**: markerless dir with candidates at depth 1/2/3 + a
  `node_modules/` plant + a symlink to a real project →
  `candidates: ["a/d2py","d1py"]` only (depth-3 excluded, skip list
  honored, symlink NOT followed).
- **`$HOME`**: `novetest init` → exit 4, `scan_refused: true`,
  `candidates: []`, nothing created, message cites decision D4.
- **Markerless + 0 candidates**: `candidates: []`, `scan_refused: false`,
  actionable message ("no candidate projects were found within the bounded
  discovery scan (depth <= 2); cd into your project directory…").
- **≥2 markers, 0 READY** (`package.json` + `.csproj`; node & dotnet absent)
  → `engine-ambiguous` exit 2, NOT no-engine-detected, nothing created. ✅

### E2E suite ✅

```
env -u PYTHONPATH uv run pytest -q tests/integration/test_anchored_pin_e2e.py
  → 6 passed, 2 snapshots passed (8.27s)
```

## Issues found

**None blocking.** No regressions. Windows `./...` KNOWN-RED is already
triaged and routed (`questions/main-branch-team-2026-07-04-windows-dotdotdot-normalization-ci-red.md`);
untestable on this POSIX host.

## Observations for PM (behavior nuances, not defects)

1. **Viability = marker + toolchain-READY, so init outcomes are
   host-dependent.** `pyproject.toml + go.mod` on a host WITHOUT go →
   exit 0, silently pins pytest (exactly one *viable* engine). The D1
   decision table keys its wording on *markers*; the implementation (per
   the task brief) keys on READY candidates. Reasonable, but the same repo
   init'd on two machines can pin without a word on one and demand
   `--engine` on the other. The user-doc pass (already flagged by Main
   Branch) should state this rule explicitly.
2. **Zero-collected explicit target → `status: "passed"`, exit 0.**
   `novetest run ../../../tests/test_math_utils.py` from a subdir (verbatim
   pass-through, resolves nowhere from the anchor) and
   `novetest run does/not/exist.py` from the root both yield
   `collected: 0, total: 0, status: passed`. This is **pre-existing Run
   engine behavior** (reproduces from the root, independent of this slice),
   but subdir invocation makes it easier to hit. An agent can believe a
   test passed that never ran — the exact "silent wrongness" the
   anchored-pin decision was written to kill. Suggest a follow-up: warning
   or distinct status when an explicit target collects zero tests.
3. **Ambiguity message says "Multiple viable engines detected" even when
   zero are toolchain-ready** (jest+xunit case). Behavior matches D1;
   wording could confuse ("viable" ≠ runnable here). Cosmetic.
4. **Reset success envelope carries no `pinned_engine`** — confirmed as
   deliberately byte-stable. Mild asymmetry vs init/status; agrees with the
   handoff's own PM-follow-up flag. No consumer harm observed in practice.

## Recommendations for PM

1. Close this slice as verified on POSIX; keep the Windows `./...`
   fast-follow open (already routed) and re-run the CI matrix after it lands.
2. Fold Observations 1–2 into the already-planned user-doc realignment task
   (Observation 2 could alternatively become a small Run-team task).
3. No action needed on 3–4 beyond the existing follow-up candidate list.

*(Process note: `Write` tool was blocked by the background-session isolation
guard; findings written via Bash heredoc per GOTCHAS.md — no deliverable
impact.)*
