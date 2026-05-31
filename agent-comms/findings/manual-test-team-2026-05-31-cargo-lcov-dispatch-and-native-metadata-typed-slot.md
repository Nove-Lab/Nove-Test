---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
slug: cargo-lcov-dispatch-and-native-metadata-typed-slot
created: 2026-05-31
verdict: passed
related:
  - agent-comms/verifications/2026-05-31-cargo-lcov-dispatch-and-native-metadata-typed-slot.md
  - agent-comms/handoffs/coverage-team-2026-05-31-cargo-lcov-dispatch.md
  - agent-comms/handoffs/run-team-2026-05-31-native-result-metadata-typed-slot.md
  - agent-comms/decisions/2026-05-30-native-result-metadata-slot.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/findings/manual-test-team-2026-05-31-cargo-nextest-env-var-hotfix.md
---

# Findings — parallel cycle: cargo Coverage LCOV dispatch + NativeResult typed metadata slot

## Verdict

**`passed`** — ship both slices. Every load-bearing assertion in Main
Branch's verification doc held. **The cargo-adapter slate is now fully
closed**: Issue 1 (env-var) by `1e736cc`, Issue 2 (payload-stash) by
this cycle's Run slice `4cb5d48`, Coverage carry-forward by this
cycle's Coverage slice `53f7920`. Cargo can be marked **E2E-verified
v1**. One minor doc-level observation surfaced (verification doc
Scenario 5 glob path + field name), zero source-level findings.

## Narrative for the CEO

Two slices landed together in the same parallel cycle, both probing
the same cargo surface, both completing the cargo-adapter clean-up
arc that started with my 2026-05-30 sweep. I verified them in a
single sweep against the merged tip `d4ebafa`.

**The Coverage slice** finally makes cargo runs first-class citizens
in the Coverage engine. Before this slice, every cargo run would
parse its tests fine, run cargo-llvm-cov fine, save the LCOV artifact
to disk fine — but the orchestration layer couldn't *consume* the
LCOV, so `inspect.sub_reports.coverage` was hardcoded to `unavailable`
for cargo. Now: cargo runs produce a canonical `CoverageFactSet` via
a brand-new `lcov_parser.parse_lcov` (modeled exactly after the
existing istanbul/pytest paths), and the orchestration layer sees
coverage as `available`. `novetest coverage show`, `novetest coverage
diff`, and `novetest inspect` all read cargo coverage exactly like
they read pytest's. **The fixture's intentionally-uncovered
`classifier.rs:13` "negative" branch shows up as a single missing
line, summary reads 96.0% (24/25 statements), and a second cargo
run + `coverage diff` returns a well-formed delta envelope** — the
first end-to-end exercise of cross-cargo-run delta composition.

**The Run slice** retires the lazy `payload["nextest_version"]`
stash convention I flagged in Issue 2 of the 2026-05-30 sweep, in
favor of a typed `NativeResult.metadata: dict[str, str]` contract
slot. The normalizer now owns `native_exit_code`, refuses to let any
adapter pre-populate that key (strict-raise guard), and overlays the
adapter's own metadata on top. **Result**: `metadata.nextest_version`
now lands in the persisted `record.json` and in the live envelope —
which it *never did* pre-slice, because the normalizer used to
hardcode `metadata={"native_exit_code": ...}` and silently dropped
everything else the adapter put in its payload dict. pytest, jest,
and gotest are intentionally still `metadata: {"native_exit_code":
<int>}` only — none of them have a record-bound secondary-runner
version analogous to nextest, so they don't need to populate the
typed slot, and they don't.

**The single most important assertion** is that both slices'
fingerprints appear *in the same envelope* from a single `novetest
run --coverage` invocation. They do. I captured both proofs in one
shot from Scenario 1. Cargo adapter v1 is finally feature-complete:
Memory persists the run with full metadata, Coverage derives the
fact-set, Regression composes deltas across runs (verified back in
the env-var-hotfix findings), Inspect reports coverage as available.
**No remaining ship-blockers, no remaining design Q's, no remaining
regressions.** Time for PM to retire the cargo-adapter slate and
dispatch the post-MVP backlog.

## What was tested

Merged tip: **`d4ebafa`** (Main Branch verification commit on top of
the two source commits `4cb5d48` (Run slice) and `53f7920` (Coverage
slice)).

Host: equipped polyglot dev box, unchanged from the 2026-05-30 sweep
and 2026-05-31 hotfix verification:
- `cargo 1.96.0`
- `cargo-nextest 0.9.137`
- `cargo-llvm-cov 0.8.7`

Scope I covered:
- **All 8 verification scenarios** (Scenarios 1–8 from Main Branch's doc).
- **All 6 critical edges** (Edges 1–6; E1/E2/E3 explicitly out-of-scope per the doc, E4/E5/E6 actively probed).
- **Full unit + integration gate** on the merged tip.
- **Bonus probes**: pytest record.json metadata shape persistence; WORKLOG.md preservation across the rebase resolution.

## Pre-flight evidence

```
$ git rev-parse HEAD
d4ebafaa45500a898a26f42f46794905d5e9120c

$ cargo --version && cargo nextest --version | head -1 && cargo llvm-cov --version
cargo 1.96.0 (30a34c682 2026-05-25)
cargo-nextest 0.9.137 (75ddba7e9 2026-05-26)
cargo-llvm-cov 0.8.7

$ grep -n "_RESERVED_METADATA_KEYS\|metadata.update\|metadata: dict\[str" \
    src/novetest/run/normalizer.py src/novetest/run/types.py
src/novetest/run/types.py:110:    metadata: dict[str, str] = field(default_factory=dict)
src/novetest/run/normalizer.py:22:_RESERVED_METADATA_KEYS: frozenset[str] = frozenset({"native_exit_code"})
src/novetest/run/normalizer.py:79:    reserved_collisions = _RESERVED_METADATA_KEYS & native_result.metadata.keys()
src/novetest/run/normalizer.py:89:    metadata: dict[str, Any] = {"native_exit_code": native_result.returncode}
src/novetest/run/normalizer.py:90:    metadata.update(native_result.metadata)
```

Source pin-points all match Main Branch's verification doc verbatim.

## Gate evidence

```
$ uv run pytest -q tests/unit tests/integration
712 passed, 5 skipped in 29.05s
```

Numbers match Main Branch's claim **exactly** (712 + 5). The 5 skips
are the pre-existing Node/jest cells that require `npm`. The
`+34` net gain from the previous cycle's 678 baseline tracks
Main Branch's claim:
- Coverage slice: +31 (26 lcov_parser unit + 4 derive cargo + 1 cargo
  Coverage E2E)
- Run slice: +3 (3 metadata-overlay tests in `test_normalizer.py`)

## Scenarios — verbatim observed output

### Scenario 1 — `novetest run --coverage` proves BOTH slices in tandem

```
$ cd tests/manual-test-workspace/cargo-test-basic-coverage
$ uv run --project /home/yjshin/dev/Nove-Test novetest init   # exit 0, ok=true, store_state=ready
$ uv run --project /home/yjshin/dev/Nove-Test novetest run --coverage
$ echo exit=$?
exit=0
```

Parsed envelope (all assertions ✅):

| Assertion | Expected | Observed |
|---|---|---|
| exit code | `0` | **`0`** ✅ |
| `ok` | `True` | **`True`** ✅ |
| `command` | `"run"` | `"run"` ✅ |
| `engine_name` | `"cargo-test"` | **`"cargo-test"`** ✅ |
| `engine_version` | `"1.96.0"` (host-dep) | `"1.96.0"` ✅ |
| **`metadata`** (Run slice proof) | `{native_exit_code:0, nextest_version:"0.9.137"}` | **`{'native_exit_code': 0, 'nextest_version': '0.9.137'}`** ✅ |
| `summary_counts` | `{p:4, f:0, s:0, t:4}` | `{passed:4, failed:0, skipped:0, total:4}` ✅ |
| `artifact_paths` includes | `coverage_lcov` + `cargo_events_jsonl` | `['cargo_events_jsonl', 'coverage_lcov', 'stderr', 'stdout']` ✅ |
| **`coverage_outcome.kind`** (Coverage slice proof) | `"fact-set"` | **`"fact-set"`** ✅ |
| `coverage_outcome.mapping_granularity` | `"aggregate"` | `"aggregate"` ✅ |
| `coverage_outcome.summary.percent_covered` | `96.0` | **`96.0`** ✅ |
| `coverage_outcome.summary.covered_statements` | `24` | `24` ✅ |
| `coverage_outcome.summary.num_statements` | `25` | `25` ✅ |
| `coverage_outcome.summary.missing_statements` | `1` | `1` ✅ |
| `warnings` | `[]` | `[]` ✅ |
| `errors` | `[]` | `[]` ✅ |

`RUN_ID = 01KSYWK8PKE8YXXQDC0627VJCY` — reused in Scenarios 2–6.

**Both fingerprints in one envelope** — the load-bearing claim of the
parallel cycle held perfectly.

### Scenario 2 — `coverage show <run_id>`

```
$ uv run --project /home/yjshin/dev/Nove-Test novetest coverage show 01KSYWK8PKE8YXXQDC0627VJCY
$ echo exit=$?
exit=0
```

- `command: "coverage.show"` ✅
- `kind: "fact-set"` ✅
- `mapping_granularity: "aggregate"` ✅
- `summary.percent_covered: 96.0` ✅
- `summary.covered_statements: 24`, `num_statements: 25`, `missing_statements: 1` ✅
- `run_reference.run_id == 01KSYWK8PKE8YXXQDC0627VJCY` ✅

### Scenario 3 — `inspect <run_id>` flips `sub_reports.coverage`

```
$ uv run --project /home/yjshin/dev/Nove-Test novetest inspect 01KSYWK8PKE8YXXQDC0627VJCY
```

Observed `data.sub_reports`:
```json
{
  "coverage": "available",
  "localization": "unavailable",
  "regression": "unavailable",
  "replay": "unavailable"
}
```

**`coverage: "available"`** ✅ — was `unavailable` for cargo runs
pre-Coverage-slice. Load-bearing assertion held.

### Scenario 4 — persisted record.json keeps typed slot

`.novetest/memory/runs/2026/05/31/run_01KSYWK8PKE8YXXQDC0627VJCY/record.json`:

| Field | Expected | Observed |
|---|---|---|
| `engine_name` | `"cargo-test"` | `"cargo-test"` ✅ |
| `engine_version` | `"1.96.0"` | `"1.96.0"` ✅ |
| **`metadata`** | `{native_exit_code:0, nextest_version:"0.9.137"}` | `{"native_exit_code":0,"nextest_version":"0.9.137"}` ✅ |
| `artifact_paths` includes `coverage_lcov` | yes | yes ✅ |

The typed slot survives serialization round-trip. Run slice persists end-to-end.

### Scenario 5 — persisted coverage_facts.json proves LCOV parser

**Minor doc-path discrepancy**: verification doc's glob says
`.novetest/memory/runs/**/coverage_facts.json` but the canonical
Coverage layout puts the file at
`.novetest/coverage/facts/run_<id>/coverage_facts.json` (Coverage
engine has its own facts root, mirroring `regression/facts/`). File
exists at the canonical location; doc-level discrepancy only. Also,
the per-file entry's path field is `file_path` (not `path` as the
doc's example python implied). See "Minor observations" below.

`.novetest/coverage/facts/run_01KSYWK8PKE8YXXQDC0627VJCY/coverage_facts.json`:

```
top-level keys: ['derived_at', 'ecosystem', 'engine_name', 'files',
                 'mapping_granularity', 'metadata', 'run_reference',
                 'schema_version', 'summary']
engine_name: cargo-test                          ✅
ecosystem: rust                                  ✅
mapping_granularity: aggregate                   ✅
metadata: {"branch_arc_semantics": "lcov-line-index",
           "coverage_format": "lcov"}            ✅ exact match

files:
  src/arithmetic.rs    cov=6/6    missing_lines=[]    ✅
  src/classifier.rs    cov=6/7    missing_lines=[13]  ✅ intentional uncovered "negative"
  src/lib.rs           cov=12/12  missing_lines=[]    ✅

summary: {"covered_branches": 0, "covered_statements": 24,
          "excluded_statements": 0, "missing_branches": 0,
          "missing_statements": 1, "num_branches": 0,
          "num_statements": 25, "percent_covered": 96.0}  ✅
```

No `lcov_warnings` key in metadata ✅ (all paths inside workspace
root; conditional key correctly absent).

### Scenario 6 — `coverage diff` between two cargo runs (Coverage Open Q4)

```
$ uv run --project /home/yjshin/dev/Nove-Test novetest run --coverage   # 2nd run
$ RUN_ID_2 = 01KSYWNXKYPJB8EC3KVB86RF4H
$ uv run --project /home/yjshin/dev/Nove-Test novetest coverage diff \
    01KSYWK8PKE8YXXQDC0627VJCY 01KSYWNXKYPJB8EC3KVB86RF4H
$ echo exit=$?
exit=0
```

`data.coverage_delta`:
- `kind: "delta"` ✅
- `baseline_granularity: "aggregate"`, `target_granularity: "aggregate"` ✅
- `baseline_run_reference.run_id == 01KSYWK8PKE8YXXQDC0627VJCY` ✅
- `target_run_reference.run_id == 01KSYWNXKYPJB8EC3KVB86RF4H` ✅
- `summary_before == summary_after` (identical fixture → identical
  coverage; 96.0% / 24-of-25 stmts both sides) ✅
- `file_deltas: []`, `files_added: []`, `files_removed: []` ✅ (no
  per-file deltas as expected for identical runs)

**Coverage handoff Open Q4 ("not exercised in own E2E") is now
closed** by this scenario. `compare_coverage_facts` consumes two
cargo `CoverageFactSet`s end-to-end without issue.

### Scenario 7 — `novetest run` (no `--coverage`) — typed slot on non-coverage path

```
$ cd tests/manual-test-workspace/cargo-test-basic
$ uv run --project /home/yjshin/dev/Nove-Test novetest init
$ uv run --project /home/yjshin/dev/Nove-Test novetest run
$ echo exit=$?
exit=3
```

- `ok: True` ✅
- `status: "failed"` ✅ (1 intentional failure)
- `summary_counts: {failed:1, passed:2, skipped:0, total:3}` ✅
- **`metadata: {native_exit_code:100, nextest_version:"0.9.137"}`** ✅
  - `native_exit_code: 100` = libtest "1+ tests failed"
  - **`nextest_version` typed slot survives on the non-coverage path** ✅
- `artifact_paths: ['cargo_events_jsonl', 'stderr', 'stdout']` (no
  `coverage_lcov` ✅ — not requested)
- `coverage_outcome: NOT IN ENVELOPE` ✅ (correctly omitted when
  `--coverage` is not requested)

### Scenario 8 — non-cargo engine regression check (pytest)

I used `pytest-coverage` fixture.

```
$ cd tests/manual-test-workspace/pytest-coverage
$ uv run --project /home/yjshin/dev/Nove-Test novetest init
$ uv run --project /home/yjshin/dev/Nove-Test novetest run --coverage
$ echo exit=$?
exit=0
```

- `engine_name: "pytest"` ✅
- **`metadata: {'native_exit_code': 0}`** ✅ — single key, `nextest_version`
  correctly absent. The pytest adapter doesn't populate `NativeResult.metadata`
  (no record-bound secondary-runner version analogous to nextest); the
  normalizer-owned `native_exit_code` is the only key. Regression-pinning
  shape held.
- `coverage_outcome.kind: "fact-set"` ✅ (existing JSON-path flow unchanged)
- `summary.percent_covered: 86.67%` (10/11 + 3/4 branches; pytest's
  own fixture, not the cargo one)
- `artifact_paths: ['coverage_json', 'coverage_xml', 'pytest_json_report',
  'stderr', 'stdout']` — `coverage_json`/`coverage_xml` keys preserved
  (no `coverage_lcov`); pytest path entirely untouched by the Coverage
  slice's cargo-only branch.

## Critical edges

### Edge 1 — reserved-key guard (`metadata["native_exit_code"]`)

Out of scope per Main Branch (unit-tested at
`test_metadata_overlay_rejects_reserved_native_exit_code_key`). Source
grep confirms `_RESERVED_METADATA_KEYS = frozenset({"native_exit_code"})`
at `normalizer.py:22` and the guard at `normalizer.py:79`. Confirmed
present, not exercised at E2E (no adapter naturally sets that key).
✅ noted.

### Edge 2 — Coverage availability accepts both `coverage_json` and `coverage_lcov`

Implicitly covered:
- Scenario 1/3 (cargo): `coverage_lcov` → `coverage: available` ✅
- Scenario 8 (pytest): `coverage_json` → `coverage: available` (confirmed via
  observed `coverage_outcome.kind: "fact-set"`; the same `_COVERAGE_ARTIFACT_KEYS`
  tuple gating accepts pytest's `coverage_json`) ✅

### Edge 3 — LCOV path-outside-workspace handling

Out of scope per Main Branch (would need contrived fixture). Smoke
fixture's three files are all under `src/`; persisted
`coverage_facts.json.metadata` correctly **does not** include
`lcov_warnings` key (conditional key, correctly absent). ✅ noted.

### Edge 4 — BRDA-absent (cargo-llvm-cov default)

```
$ python3 -c "import json; \
  print(json.load(open('.novetest/coverage/facts/run_01KSYWK8PKE8YXXQDC0627VJCY/coverage_facts.json'))['summary']['num_branches'])"
0
```

**`num_branches: 0`** ✅ — cargo-llvm-cov 0.8.7 still ships BRDA-absent
default; smoke fixture exercises the BRDA-ABSENT code path. (Future-
proofing: if anyone upgrades cargo-llvm-cov and `num_branches > 0`
suddenly appears on this same fixture, that's the BRDA-PRESENT path
firing — a real signal worth investigating.)

### Edge 5 — cache round-trip on second `coverage show`

```
$ uv run --project /home/yjshin/dev/Nove-Test novetest coverage show \
    01KSYWK8PKE8YXXQDC0627VJCY > /tmp/cov2.json
$ diff <(... pretty-print /tmp/cov.json ...) <(... pretty-print /tmp/cov2.json ...)
(empty diff)
```

✅ Envelope byte-identical on the second `coverage show`.
`get_coverage_facts` cache hit produces deterministic output.

### Edge 6 — `metadata` never empty

```
$ python3 -c "<glob every record.json, assert non-empty + has 'native_exit_code'>"
Found 2 records:
  run_01KSYWK8PKE8YXXQDC0627VJCY: metadata={'native_exit_code': 0, 'nextest_version': '0.9.137'}  ok=True
  run_01KSYWNXKYPJB8EC3KVB86RF4H: metadata={'native_exit_code': 0, 'nextest_version': '0.9.137'}  ok=True
```

Plus the pytest record (from Scenario 8's workspace): `metadata:
{'native_exit_code': 0}` — single key, never empty.

✅ All 3 persisted records this verification touched satisfy the
"never `metadata: {}`" invariant.

## Bonus probes

### Bonus 1 — WORKLOG.md rebase resolution preserved both entries

Per Main Branch's merge notes #1–2, the only conflict during merge
was WORKLOG.md (both teams added top-of-file entries at the same
insertion point). I read the top 50 lines of WORKLOG.md from the
merged tip: the topmost section is the Run team's
`phase3 / native-result-metadata-typed-slot` entry, followed by the
Coverage team's `phase3 / cargo-lcov-dispatch` entry. Both bodies
look intact (full-paragraph entries, not truncations). The rebase
resolution preserved both teams' narratives.

### Bonus 2 — pytest record.json persistence

Beyond the live envelope check in Scenario 8, I confirmed the
persisted `record.json` for the pytest run also has `metadata:
{'native_exit_code': 0}` — same single-key shape, never empty.
This pins the "pytest/jest/gotest adapters don't populate `metadata`
yet" claim across the persistence layer, not just the live envelope.

## Minor observations (not blockers; PM may file follow-ups if desired)

### Obs 1 — Verification doc Scenario 5 glob path is wrong

The doc says:
```python
cf = sorted(glob.glob(".novetest/memory/runs/**/coverage_facts.json", recursive=True))[-1]
```

Actual canonical location:
```
.novetest/coverage/facts/run_<id>/coverage_facts.json
```

(Coverage facts live in the Coverage engine's own facts root, not
under Memory's runs/ tree.) The verification doc's example python
would have raised `IndexError: list index out of range` (which it
did for me on first try; I adapted by `find`-ing the actual file).

**Suggested follow-up**: if Main Branch wants verification scripts
to be copy-paste-runnable as a UX commitment, this glob should be
`'.novetest/coverage/facts/**/coverage_facts.json'`. Trivial fix
for future verification docs; no source change needed.

### Obs 2 — Verification doc Scenario 5 field name is `file_path`, not `path`

The doc's example loop uses `f['path']` but the actual JSON shape
is `f['file_path']`. Same UX-of-verification-doc concern; doc-level
nit only.

### Obs 3 — Both observations are documentation-only

No source bugs. No behavioral regressions. No follow-up tasks for
the dev teams. These are workflow polish items for Main Branch's
verification-doc authoring template.

## Issues found

**None at the source/behavioral level.** Only the two documentation
observations above (Obs 1, Obs 2), both attributable to verification
doc draft polish, not the merged code.

## Recommendations for PM

1. **Close 2026-05-31 cycle as `passed`.** Both parallel slices verified
   green. Suggested cycle summary heading:
   `comms: close 2026-05-31 cycle — parallel slice (cargo LCOV + typed metadata) passed; cargo slate retired`.

2. **Retire the cargo-adapter slate.** All three follow-ups from the
   2026-05-30 sweep are now resolved:
   - Issue 1 (env-var) by `1e736cc` + `5a6f4fe` (previous cycle).
   - Issue 2 (payload-stash) by `4cb5d48` (this cycle's Run slice).
   - Coverage carry-forward (`inspect.sub_reports.coverage` flip) by
     `53f7920` (this cycle's Coverage slice).

   Cargo adapter v1 is feature-complete and verified end-to-end at
   every consumer surface I could reach: `run`, `run --coverage`,
   `inspect`, `coverage show`, `coverage diff`, `regression compare`
   (the last covered in 2026-05-31 hotfix findings Bonus 3).

3. **Dispatch the post-MVP backlog.** Per Main Branch's note in §"Trigger-(b) closure context": the natural next step is post-MVP work — Phase 4 SBFL aggregate mode, JUnit/dotnet adapters per Q4/Q5 of the supported-engine matrix. No urgent cargo work remains.

4. **Optional: tighten verification-doc template for Main Branch.**
   Obs 1 + Obs 2 above (glob path + field-name discrepancies) are
   minor doc-authoring nits that future verifications could avoid
   if the verification template suggested re-running the doc's own
   example snippets against the merged tip as part of the doc's
   own validation pass. Not urgent; no immediate task.

5. **No follow-up tasks needed for Manual Test.** The Run + Coverage
   slate is complete. Future cargo work (build-failure heuristic
   polish at `cargo_adapter.py:263`, BRDA-PRESENT path validation
   when cargo-llvm-cov upgrades) is well-separated and doesn't
   require manual re-verification of these slices.

## Artifacts retained

- `tests/manual-test-workspace/cargo-test-basic-coverage/.novetest/`:
  two coverage runs (`01KSYWK8PKE8YXXQDC0627VJCY`,
  `01KSYWNXKYPJB8EC3KVB86RF4H`) with full artifact + facts trees.
- `tests/manual-test-workspace/cargo-test-basic/.novetest/`: one
  no-coverage cargo run (Scenario 7).
- `tests/manual-test-workspace/pytest-coverage/.novetest/`: one
  pytest non-cargo regression run (Scenario 8).
- `/tmp/run.json`, `/tmp/cov.json`, `/tmp/cov2.json`, `/tmp/inspect.json`,
  `/tmp/run2.json`, `/tmp/diff.json`, `/tmp/run_no_cov.json`,
  `/tmp/run_py.json` — captured envelopes; ephemeral.

All scratch contents are git-ignored under
`tests/manual-test-workspace/.gitignore`; nothing committed.
