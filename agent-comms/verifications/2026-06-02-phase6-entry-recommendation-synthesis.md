---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-06-02
slug: phase6-entry-recommendation-synthesis
merged_commit: fa3be73
source_handoffs:
  - handoffs/orchestration-team-2026-06-02-phase6-entry-recommendation-synthesis.md
related:
  - tasks/orchestration-team-2026-06-01-phase6-entry-recommendation-synthesis.md
  - design/implementation-plan/delivery-phasing.md
  - design/implementation-plan/recommendation-synthesis.md
  - design/interace-contract/orchestration.md
  - design/workflows/orchestration.md
  - design/requirements-analysis/requirements-specification/groups/orchestration.md
---

# Verification: Phase 6 entry — Recommendation Synthesis (closed taxonomy v1, integrated `novetest test`, default-verb alias)

## TL;DR for Manual Test

A very large Orchestration-team slice landed at `fa3be73` (FF-merge
after a clean rebase onto `9fc71cc`). It introduces the **complete
Phase 6 surface**:

1. **`novetest/orchestration/recommendation/` engine** — 5 new src
   modules (`categories.py`, `templates.py`, `synthesizer.py`,
   `citations.py`, `fact_bundle.py`) implementing the closed 7-category
   taxonomy frozen at `recommendation_schema_version: 1`.
2. **Integrated `novetest test [target]` workflow** at
   `src/novetest/orchestration/workflows/test.py` — chains
   Run → Memory → Coverage → Regression → Localization → Synthesize.
3. **Default-verb alias** — `novetest <target>` resolves to
   `novetest test <target>` when `<target>` is NOT a reserved verb;
   `novetest run <target>` stays explicit; bare `novetest` keeps
   the help envelope.
4. **New CLI handlers package** (`src/novetest/cli/handlers/`) —
   currently just `test.py`. PM has flagged this as a forward-looking
   policy decision (handoff §Q3) on whether to migrate older verbs in
   a follow-up.

Slice closes:
- **All 4 Phase 6 DoD bullets** (PM ticks `delivery-phasing.md:249-252`)
- **The lingering Phase 1 line 96 bullet** (PM ticks
  `delivery-phasing.md:96` — empty-fact-set integrated workflow case)

After PM tick at cycle close, MVP scope shrinks to: **Phase 5**
(Replay + SQLite index) + **Phase 3 JUnit/.NET** (Open Q #4/#5 gated)
+ **Phase 7 MCP transport** (post-MVP).

## Merged commit + source

| Aspect | Value |
|---|---|
| Merge tip | `fa3be73` (FF, no merge commit) |
| Base | `9fc71cc` (prior `main` tip; marketing-PM-charter commit) |
| Worktree base | `dd02942` → rebased onto `9fc71cc` (1-commit forward, zero conflicts — marketing commit touches only `.claude/agents/` + `design/website-plan/`, zero overlap with orchestration territory) |
| Branch | `worktree-phase6-recommendation-synthesis` (post-merge cleanup pending) |
| Source handoff | `agent-comms/handoffs/orchestration-team-2026-06-02-phase6-entry-recommendation-synthesis.md` |
| Files in slice | 27 (8 new src + 3 modified src + 11 new tests + 1 modified test + 1 snapshot + 3 coordination) |
| Net source-file count | **80** (delta: +8 from baseline 72) |
| Net test count | **871 + 5** (delta: +95 vs baseline 776+5 on `9fc71cc`) |

### Files touched (verbatim from `git show --name-only fa3be73`)

**New src** (8):
- `src/novetest/orchestration/recommendation/__init__.py`
- `src/novetest/orchestration/recommendation/categories.py`
- `src/novetest/orchestration/recommendation/templates.py`
- `src/novetest/orchestration/recommendation/synthesizer.py`
- `src/novetest/orchestration/recommendation/citations.py`
- `src/novetest/orchestration/recommendation/fact_bundle.py`
- `src/novetest/orchestration/workflows/test.py`
- `src/novetest/cli/handlers/__init__.py`
- `src/novetest/cli/handlers/test.py`

**Modified src** (3):
- `src/novetest/cli/app.py`
- `src/novetest/orchestration/workflows/__init__.py`

**New tests** (11):
- `tests/unit/orchestration/recommendation/test_categories.py`
- `tests/unit/orchestration/recommendation/test_templates.py`
- `tests/unit/orchestration/recommendation/test_synthesizer.py`
- `tests/unit/orchestration/recommendation/test_citations.py`
- `tests/unit/orchestration/recommendation/test_fact_bundle.py`
- `tests/unit/orchestration/workflows/test_test_workflow.py`
- `tests/unit/cli/test_default_verb_alias.py`
- `tests/unit/cli/test_test_handler.py`
- `tests/integration/orchestration/test_test_workflow.py`
- `tests/integration/orchestration/test_recommendation_round_trip.py`
- `tests/integration/cli/test_default_verb_alias.py`

**Modified tests** (1):
- `tests/integration/cli/test_subcommand_stubs.py` (dropped pinned-as-stub `test` assertion)

**Snapshot** (1):
- `tests/integration/orchestration/__snapshots__/test_test_workflow.ambr`

**Coordination** (3): `WORKLOG.md`, the handoff, regenerated `INDEX.md`.

## Pre-merge gates (worktree, equipped host, after rebase)

| Gate | Command | Result |
|---|---|---|
| Default suite | `uv run pytest -q tests/unit tests/integration` | **871 passed, 5 skipped** (44.45 s) + 2 snapshots passed |
| mypy strict | `uv run mypy` | Success — **80 source files** |

## Post-merge gates on `main` (this is the gate that ships)

```
$ uv run pytest -q tests/unit tests/integration
… 871 passed, 5 skipped in 42.51s
2 snapshots passed.

$ uv run mypy
Success: no issues found in 80 source files
```

**Both green.** Identical to pre-merge (rebase + FF preserves
algorithmic state).

## Empirical envelope literals (captured on merged tip `fa3be73`)

All literals below were captured by Main Branch via subprocess CLI
runs against the named fixtures. Manual Test's scenarios should
match these byte-for-byte (modulo timestamp / ULID fields).

### `novetest test` envelope shape — frozen v1

```
schema: "novetest/v1"
command: "test"
ok: true | false
exit_code: 0 (no failures) | 2 (failures) | …
errors: []  (when ok)
warnings: []
data:
  run_reference: {created_at: int_ms, run_id: "01K…ULID…", schema_version: 1}
  recommendation_schema_version: 1
  stage_eligibility:
    coverage:     "available" | "unavailable" | "not_applicable"
    regression:   "available" | "unavailable" | "not_applicable"
    localization: "sbfl_per_test" | "sbfl_aggregate" | "failure_proximity"
                  | "unavailable" | "not_applicable"
    replay:       "available" | "unavailable" | "not_applicable" | "not_run"
  recommendations:
    - category: <one of 7 categories>
      priority: 1..7  (1 = highest; matches brief §1 table)
      summary: <human-readable string>
      slots: {category-specific keys, see below}
      recommendation_id: "rec_<run_id>_<sha1_8hex>"
      evidence_citations:
        - kind: <kind enum>
          run_reference: {created_at, run_id, schema_version}
          selector: {kind-specific}
          # additional kind-specific top-level fields (e.g. finding_id, mode)
```

### Per-category slot keys (frozen v1; copy from merged tip)

| Category | Priority | Slot keys |
|---|---|---|
| `regression_with_localization` | 1 | (compound — see brief §1; not exercised by current integration fixtures) |
| `investigate_location` | 2 | `file, formula, line_range, mode, primary_line, rank, score_normalized, symbol` |
| `investigate_regression` | 3 | `test_id, regression_kind, run_reference_from, run_reference_to` (mock-pinned in unit tests) |
| `coverage_gap` | 4 | `file, lines, mode, related_finding_id` (mock-pinned) |
| `flaky_suspected` | 5 | `test_id, reruns_total, reruns_failed, run_reference` (mock-pinned — Phase 5 dep) |
| `unavailable_analysis` | 6 | `reason_per_stage, run_reference, unavailable_stages` |
| `all_green` | 7 | `passed, run_reference, skipped, total_tests` |

### Per-citation-kind selector shape (captured on merged tip)

| Citation kind | Selector shape | Additional top-level fields |
|---|---|---|
| `localization_finding` | `{file: str, primary_line: int, rank: int}` | `finding_id: "loc_run_<run_id>"`, `mode: <localization mode>` |
| `regression_fact` | `{test_id: str}` | (TBD — exercise via §"Critical edge cases" probes) |
| `coverage_fact` | `{file: str, lines: [int, ...]}` | (TBD) |
| `test_result` | `{outcome: str, test_id: str}` | (TBD — verify by reading `test_categories.py`) |
| `run_reference` | `{}` (empty dict) | (none) |
| `replay_result` | (Phase 5 dep — skipped) | — |

### Recommendation ordering (frozen v1)

Sort key per brief §1: `(priority asc, category asc, primary_slot asc)`.

The `primary_slot` is **category-specific** (NOT
`recommendation_id` — see handoff §Q1 — the SHA-1 hash was the
team's first-draft bug). For `investigate_location`, it is
`f"{file}:{line_range[0] if line_range else primary_line}"`. This
explains why on `localization-branch`:

- `rec[0]` = `add@20` in `localization_branch/calculator.py` (score 0.0, rank 2)
- `rec[3]` = `divide@31` in `localization_branch/calculator.py` (score 1.0, rank 1) — **the actual bug**

The bug-site (`divide`, score 1.0) is NOT `rec[0]`. The "lex-min
file:line wins" sort is the brief's binding invariant — see open
questions Q1 in the handoff for the team's proposal to add a
`score_normalized > 0` floor in a v2 schema bump.

## Verification scenarios for Manual Test

> **Setup**: working tree at commit `fa3be73`. Confirm with:
> ```sh
> cd /home/yjshin/dev/Nove-Test
> git log -1 --oneline
> # → fa3be73 feat(orchestration): Phase 6 entry — recommendation synthesis + integrated `novetest test`
> ```

---

### Scenario A — default suite still green on your host

```sh
cd /home/yjshin/dev/Nove-Test
uv run pytest -q tests/unit tests/integration
```

**Expected**: `871 passed, 5 skipped` + `2 snapshots passed` in
roughly the same wall time as Main Branch's equipped host (~42 s).

**Why it matters**: this slice adds +95 tests across orchestration
recommendation, workflows, CLI handlers, and CLI alias coverage.
The 5 skips reflect existing cargo/java/Phase-5 guards (down from
10 because new orchestration tests are unconditional).

---

### Scenario B — mypy strict still clean

```sh
uv run mypy
```

**Expected**: `Success: no issues found in 80 source files`.

**Why it matters**: 8 new src files all pass mypy `--strict`. The
slice extensively uses `@dataclass(slots=True, frozen=True)`,
discriminated unions for citation kinds, and `__test__ = False`
guards on test-looking names — all type-stable.

---

### Scenario C — `all_green` envelope on `pytest-basic`

```sh
TMP=$(mktemp -d /tmp/test-allgreen-XXXXXX)
cp -r tests/fixtures/projects/pytest-basic/* "$TMP/"
cd "$TMP"

uv --project /home/yjshin/dev/Nove-Test run novetest init
uv --project /home/yjshin/dev/Nove-Test run novetest test tests/ \
    | python3 -m json.tool > /tmp/C-allgreen.json

python3 -c "
import json
d = json.load(open('/tmp/C-allgreen.json'))
print('schema:', d['schema'])
print('command:', d['command'])
print('ok:', d['ok'])
print('stage_eligibility:', d['data']['stage_eligibility'])
print('schema_version:', d['data']['recommendation_schema_version'])
recs = d['data']['recommendations']
print('rec count:', len(recs))
r = recs[0]
print('rec[0].category:', r['category'])
print('rec[0].priority:', r['priority'])
print('rec[0].summary:', r['summary'])
print('rec[0].slots:', r['slots'])
print('rec[0].citations[0].kind:', r['evidence_citations'][0]['kind'])
print('rec[0].citations[0].selector:', r['evidence_citations'][0]['selector'])
"
```

**Expected (verbatim from Main Branch's empirical capture on
`fa3be73`)**:

```
schema: novetest/v1
command: test
ok: True
stage_eligibility: {'coverage': 'available', 'localization': 'unavailable', 'regression': 'unavailable', 'replay': 'not_run'}
schema_version: 1
rec count: 1
rec[0].category: all_green
rec[0].priority: 7
rec[0].summary: All tests green; no action recommended (passed 3, skipped 0, total 3).
rec[0].slots: {'passed': 3, 'run_reference': '<ULID will vary>', 'skipped': 0, 'total_tests': 3}
rec[0].citations[0].kind: run_reference
rec[0].citations[0].selector: {}
```

**Why it matters**: this scenario closes the Phase 1 line 96 bullet
("all_green on empty downstream facts"). The clean run with coverage
+ no failed tests must emit exactly one `all_green` recommendation
with citation `kind: run_reference` and empty `selector: {}`.

---

### Scenario D — `investigate_location` chain on `localization-branch`

```sh
TMP=$(mktemp -d /tmp/test-locbranch-XXXXXX)
cp -r tests/fixtures/projects/localization-branch/* "$TMP/"
cd "$TMP"

uv --project /home/yjshin/dev/Nove-Test run novetest init
uv --project /home/yjshin/dev/Nove-Test run novetest test tests/ \
    | python3 -m json.tool > /tmp/D-locbranch.json

python3 -c "
import json
d = json.load(open('/tmp/D-locbranch.json'))
print('ok:', d['ok'])
print('stage_eligibility:', d['data']['stage_eligibility'])
recs = d['data']['recommendations']
print('rec count:', len(recs))
print('categories:', [r['category'] for r in recs])

# Inspect rec[0] (top investigate_location; file-line sort)
r0 = recs[0]
print('rec[0].slots:', r0['slots'])

# Find the bug-site (divide, score 1.0)
for i, r in enumerate(recs):
    if r['category'] == 'investigate_location' and r['slots'].get('symbol') == 'divide':
        print(f'BUG SITE at rec[{i}]:')
        print('  summary:', r['summary'])
        print('  slots:', r['slots'])
        print('  citation kind:', r['evidence_citations'][0]['kind'])
        print('  citation selector:', r['evidence_citations'][0]['selector'])
        print('  citation finding_id:', r['evidence_citations'][0].get('finding_id'))
        print('  citation mode:', r['evidence_citations'][0].get('mode'))
        break

# Last entry should be unavailable_analysis
ru = recs[-1]
print('rec[-1].category:', ru['category'])
print('rec[-1].slots:', ru['slots'])
"
```

**Expected**:

```
ok: False    # because tests failed; exit_code = 2
stage_eligibility: {'coverage': 'available', 'localization': 'sbfl_per_test', 'regression': 'unavailable', 'replay': 'not_run'}
rec count: 11
categories: ['investigate_location', 'investigate_location', 'investigate_location', 'investigate_location', 'investigate_location', 'investigate_location', 'investigate_location', 'investigate_location', 'investigate_location', 'investigate_location', 'unavailable_analysis']
rec[0].slots: {'file': 'localization_branch/calculator.py', 'formula': 'ochiai', 'line_range': [19, 20], 'mode': 'sbfl_per_test', 'primary_line': 20, 'rank': 2, 'score_normalized': 0.0, 'symbol': 'add'}
BUG SITE at rec[3]:
  summary: Investigate `divide`@34 in `localization_branch/calculator.py` (rank 1, ochiai=1.000, sbfl_per_test).
  slots: {'file': 'localization_branch/calculator.py', 'formula': 'ochiai', 'line_range': [31, 34], 'mode': 'sbfl_per_test', 'primary_line': 34, 'rank': 1, 'score_normalized': 1.0, 'symbol': 'divide'}
  citation kind: localization_finding
  citation selector: {'file': 'localization_branch/calculator.py', 'primary_line': 34, 'rank': 1}
  citation finding_id: loc_run_<ULID will vary>
  citation mode: sbfl_per_test
rec[-1].category: unavailable_analysis
rec[-1].slots: {'reason_per_stage': {'regression': 'no-comparable-baseline'}, 'run_reference': '<ULID>', 'unavailable_stages': ['regression']}
```

**Why it matters**: this scenario pins:

1. The brief §1 sort invariant: `primary_slot = file:line` lex order
   (handoff §1) — `add@20` lex-precedes `divide@34` even though
   `divide` has score 1.0 and `add` has 0.0. The bug-site emerges at
   `rec[3]`, not `rec[0]`.
2. The `localization_finding` citation shape with `selector.file +
   primary_line + rank` and the top-level `finding_id` +
   `mode` fields.
3. The `unavailable_analysis` slot shape with literal
   `reason_per_stage` value `"no-comparable-baseline"` (note the
   hyphen — copy verbatim).
4. The `stage_eligibility.localization` slot carries the
   localization MODE (`"sbfl_per_test"`) not just availability.

If `rec[3]`'s symbol is anything other than `divide` or the
ordering shifts, the sort invariant has regressed — file a
finding immediately. The team's handoff §Q1 flagged this
weak-ordering UX as a future v2 candidate; don't treat the
order as a defect, but DO treat a deviation from this exact
order as a regression.

---

### Scenario E — Default-verb alias activates (and does not fire for reserved verbs)

```sh
# In the same /tmp/test-allgreen-* directory or any inited workspace
cd "$TMP"  # (continue from Scenario C OR D's tmpdir; both work)

# Reuses last scenario's $TMP — set it up if not still in shell
# TMP=$(mktemp -d /tmp/test-alias-XXXXXX); cp -r .../pytest-basic/* "$TMP/"; cd "$TMP"
# uv --project /home/yjshin/dev/Nove-Test run novetest init

# Alias: novetest tests/ should resolve to novetest test tests/
uv --project /home/yjshin/dev/Nove-Test run novetest tests/ \
    | python3 -m json.tool > /tmp/E-alias.json
python3 -c "
import json
d = json.load(open('/tmp/E-alias.json'))
print('command:', d['command'])
print('schema:', d['schema'])
print('ok:', d['ok'])
print('rec count:', len(d['data']['recommendations']))
"

# Explicit run: novetest run tests/ should NOT fire the alias
uv --project /home/yjshin/dev/Nove-Test run novetest run tests/ \
    | python3 -m json.tool > /tmp/E-explicit-run.json
python3 -c "
import json
d = json.load(open('/tmp/E-explicit-run.json'))
print('command:', d['command'])
print('data keys:', list(d['data'].keys()))
"

# Bare novetest: should return help envelope
uv --project /home/yjshin/dev/Nove-Test run novetest \
    | python3 -m json.tool > /tmp/E-bare.json
python3 -c "
import json
d = json.load(open('/tmp/E-bare.json'))
print('command:', d['command'])
print('top-level data keys:', list(d['data'].keys()))
"

# Reserved verb: novetest status should route to status (not test)
uv --project /home/yjshin/dev/Nove-Test run novetest status \
    | python3 -m json.tool > /tmp/E-status.json
python3 -c "
import json
d = json.load(open('/tmp/E-status.json'))
print('command:', d['command'])
print('data keys:', list(d['data'].keys()))
"
```

**Expected**:

```
# novetest tests/
command: test
schema: novetest/v1
ok: True
rec count: 1   # all_green on pytest-basic

# novetest run tests/
command: run
data keys: ['memory_entry']    # raw run engine path, NO recommendations

# bare novetest
command: help
top-level data keys: ['onboarding', 'operating']

# novetest status
command: status
data keys: ['latest_run_reference', 'run_history_size', 'sub_reports']
```

**Why it matters**: Phase 6 DoD #4. Four orthogonal cases all
correct → alias is on AND disambiguation rule holds. Single
case fails → alias is broken.

---

### Scenario F — Determinism contract (3 consecutive `novetest test` calls byte-identical modulo run_reference)

```sh
# Stage a fresh localization-branch workspace
TMP=$(mktemp -d /tmp/test-determ-XXXXXX)
cp -r tests/fixtures/projects/localization-branch/* "$TMP/"
cd "$TMP"

uv --project /home/yjshin/dev/Nove-Test run novetest init
uv --project /home/yjshin/dev/Nove-Test run novetest test tests/ \
    | python3 -m json.tool > /tmp/F1.json
uv --project /home/yjshin/dev/Nove-Test run novetest test tests/ \
    | python3 -m json.tool > /tmp/F2.json
uv --project /home/yjshin/dev/Nove-Test run novetest test tests/ \
    | python3 -m json.tool > /tmp/F3.json

python3 -c "
import json, hashlib
def normalize(d):
    # Strip run_reference (timestamp + ULID), recommendation_ids (sha1 over run_id), and finding_ids
    out = {**d}
    out['data'] = {**out['data']}
    out['data'].pop('run_reference', None)
    recs = []
    for r in out['data'].get('recommendations', []):
        r = {**r, 'recommendation_id': '<stripped>'}
        if 'slots' in r:
            slots = {**r['slots']}
            slots.pop('run_reference', None)
            r['slots'] = slots
        citations = []
        for c in r.get('evidence_citations', []):
            c = {**c}
            c.pop('run_reference', None)
            c.pop('finding_id', None)
            citations.append(c)
        r['evidence_citations'] = citations
        recs.append(r)
    out['data']['recommendations'] = recs
    return out

s1 = json.dumps(normalize(json.load(open('/tmp/F1.json'))), sort_keys=True)
s2 = json.dumps(normalize(json.load(open('/tmp/F2.json'))), sort_keys=True)
s3 = json.dumps(normalize(json.load(open('/tmp/F3.json'))), sort_keys=True)
print('run1 sha1:', hashlib.sha1(s1.encode()).hexdigest()[:16])
print('run2 sha1:', hashlib.sha1(s2.encode()).hexdigest()[:16])
print('run3 sha1:', hashlib.sha1(s3.encode()).hexdigest()[:16])
print('all match:', s1 == s2 == s3)
"
```

**Expected**: all three sha1 hashes identical AND `all match: True`.

**Why it matters**: Phase 6 DoD #1 (determinism contract). Each
`novetest test` invocation against the SAME fixture must produce
byte-identical envelopes modulo timestamp/ULID fields. The team's
handoff §"3-consecutive-run determinism log" claims byte-identical
digest across 3 runs; this scenario reproduces the same contract
at the CLI envelope level (not just the in-memory FactBundle level).

Note: this scenario re-runs the **entire pipeline** including pytest
execution; the team's empirical determinism log used a cached
re-derive path. Both should produce identical recommendations
because the underlying facts are deterministic.

---

### Scenario G — AI agent round-trip pin (NFR-ORCH-002)

The team added two integration tests for the round-trip contract:

- `tests/integration/orchestration/test_recommendation_round_trip.py::test_investigate_location_citations_round_trip`
- `tests/integration/orchestration/test_recommendation_round_trip.py::test_every_recommendation_has_at_least_one_citation`

Manual Test can confirm both pass:

```sh
uv run pytest -v tests/integration/orchestration/test_recommendation_round_trip.py
```

**Expected**: both tests pass. The first runs `novetest test`
against `localization-branch`, picks the first `investigate_location`
recommendation, resolves every citation via the canonical retrieval
interface, and asserts the resolved Localization Finding's
`(file, primary_line, formula)` matches the recommendation's slot
values. The second pins REQ-ORCH-005 (every emitted recommendation
has ≥1 citation).

**Why it matters**: NFR-ORCH-002 is the load-bearing contract for
AI-agent traceability. If a future change breaks the
`recommendation → citation → canonical_retrieve` chain, this test
must fail loudly. Manual Test confirming green on a fresh host
validates the gate is wired correctly post-merge.

---

### Scenario H — `novetest inspect` populates recommendations field

The brief §3 noted that `inspect.py` may receive an additive call
to `synthesize_recommendation` to populate the inspect view's
`recommendations` field. Verify:

```sh
# Use any workspace with a completed run
TMP=$(mktemp -d /tmp/test-inspect-XXXXXX)
cp -r tests/fixtures/projects/localization-branch/* "$TMP/"
cd "$TMP"

uv --project /home/yjshin/dev/Nove-Test run novetest init
uv --project /home/yjshin/dev/Nove-Test run novetest test tests/ > /dev/null
uv --project /home/yjshin/dev/Nove-Test run novetest inspect \
    | python3 -m json.tool > /tmp/H-inspect.json

python3 -c "
import json
d = json.load(open('/tmp/H-inspect.json'))
print('command:', d['command'])
print('ok:', d['ok'])
print('data keys:', list(d['data'].keys()))
# Look for recommendations field (may be inside inspect_view OR data root)
for k, v in d['data'].items():
    if isinstance(v, dict) and 'recommendations' in v:
        print(f'recommendations found inside data.{k}, count:', len(v['recommendations']))
    elif k == 'recommendations':
        print(f'recommendations at data root, count:', len(v))
"
```

**Expected**: `inspect` envelope carries a `recommendations` field
(location TBD by the team's actual implementation — Main Branch did
not pre-capture this path because the brief §3 used "MAY" language).
If the field is absent, report as a finding for PM (brief gave
permissive language; team may have deferred this surface to a
follow-up — worth confirming explicit disposition).

---

## Critical edge cases worth probing (Manual Test's discretion)

The handoff is large and surfaces several deliberate forward-looking
gaps that Manual Test should be aware of:

### 1. Compound `regression_with_localization` (priority 1) not exercised in integration

Per handoff §"Per-fixture envelope captures": the
`localization-branch` 2nd-run compound case is unit-tested only;
no fixture orchestrates the 2-runs-same-bug → baseline-comparable
flow at the integration level. Manual Test could probe manually:

```sh
# Run the same fixture twice; the second run should have a comparable baseline
cd "$TMP_locbranch"
uv --project /home/yjshin/dev/Nove-Test run novetest test tests/ > /tmp/compound-1.json  # already done in Scenario D
uv --project /home/yjshin/dev/Nove-Test run novetest test tests/ > /tmp/compound-2.json

python3 -c "
import json
d = json.load(open('/tmp/compound-2.json'))
print('stage_eligibility:', d['data']['stage_eligibility'])
for r in d['data']['recommendations']:
    print(r['category'], '|', r['summary'])
"
```

**Look for**: `category: regression_with_localization` should appear
on the 2nd run IF the brief §1 compound trigger fires correctly
(Regression Fact `regressed_tests` overlaps Localization
Finding `related_failed_tests` on test ID). If it does NOT appear
and the 2nd-run envelope is identical to the 1st-run envelope, the
compound rule may be inactive at the workflow level (only
unit-tested). This isn't necessarily a defect — the team's
handoff §"Empirical verification" explicitly says the compound is
unit-pinned not integration-pinned — but it's worth confirming the
2-run behavior matches the team's expectations.

### 2. `score_normalized > 0` floor (handoff §Q1)

The 10 × `investigate_location` recommendations on
`localization-branch` is high cardinality because dense-rank ties
under SBFL push many score-0.0 entries to rank ≤ 3. The team
flagged this as a v2 candidate. Manual Test could pin the current
cardinality (10 on this fixture) so a future v2 PR has a
regression-pin to compare against.

### 3. `handlers/` package vs inline `cli/app.py` (handoff §Q3)

A new `src/novetest/cli/handlers/` package was introduced for just
`test.py`. Older verbs (init/run/status/inspect/memory/coverage/
regression/compare/localization) remain inline in `cli/app.py`
(~1200 lines). Manual Test does NOT need to probe this — PM will
decide migration policy in the next cycle. Informational only.

### 4. `selector` shape per citation kind

Main Branch's empirical capture confirmed:
- `localization_finding` → `{file, primary_line, rank}` + top-level `finding_id` + `mode`
- `run_reference` → `{}` (empty)

But did NOT exercise:
- `regression_fact` → expected `{test_id: ...}` per brief
- `coverage_fact` → expected `{file, lines}` per brief
- `test_result` → expected `{outcome, test_id}` per brief

Manual Test could exercise these by probing a 2-run scenario
(compound or split investigate_*); report observed selector shapes
to fill the empirical gap in the table above.

### 5. Bare `novetest` exit code

Per REQ-ORCH-006 the bare `novetest` returns help with exit 0.
Main Branch confirmed `command: "help"` in the envelope. Manual
Test should verify the actual process exit code (`echo $?`) is
also 0, not 1/2. Some CI matrices interpret nonzero help exits
as docs gone wrong.

---

## Phase closure context (informational for Manual Test)

Per the handoff's "Suggested next step", once Manual Test confirms
the slice, PM will tick at cycle close:

- `delivery-phasing.md:96` (Phase 1 lingering bullet)
- `delivery-phasing.md` Phase 6 DoD #1-4 (lines 249-252)

This closes **Phase 1 → 100%** and **Phase 6 → 100%**. MVP scope
shrinks to **Phase 5** (Replay + SQLite index) + **Phase 3**
JUnit/.NET adapters (Open Q #4/#5 gated) + **Phase 7** MCP
transport (post-MVP).

---

## Anything that wasn't obvious during merge (Main Branch notes)

1. **Worktree was 1 commit behind main**: orchestration team based on
   `dd02942`; main advanced to `9fc71cc` (marketing PM charter).
   Main Branch rebased the worktree onto `9fc71cc` — the rebase was
   trivially clean because the marketing commit only touches
   `.claude/agents/novetest-marketing-pm-team.md` and
   `design/website-plan/README.md`, zero overlap with orchestration
   territory. Post-rebase commit: `fa3be73`.

2. **No production-code conflict**. Marketing PM team is read-only on
   the codebase except `design/website-plan/`, so future marketing
   slices should rebase cleanly onto orchestration changes as well.
   Per CEO directive, the marketing team's worktree
   (`/home/yjshin/dev/Nove-Test/.claude/worktrees/marketing-pm-agent`)
   is NOT under Main Branch's merge management.

3. **Snapshot file is in the slice**: the `syrupy` snapshot at
   `tests/integration/orchestration/__snapshots__/test_test_workflow.ambr`
   is committed alongside the slice. Handoff §"What wasn't obvious"
   #6 flagged that syrupy's first-invocation behavior requires
   `--snapshot-update` if the file is missing — Manual Test should
   NOT need this flag because the file is on the branch.

4. **No CLI smoke regressed**: Main Branch validated D5 + D6 +
   localization-perf regression-pins by inference (all 871 existing
   tests pass, including the 166 localization tests, the 6 verb
   alias E2E subprocess tests, and the round-trip pin). Did NOT
   re-run a fresh cargo aggregate smoke (cargo binary requires
   `~/.cargo/bin` on PATH which Main Branch's shell lacks; D5/D6
   pins are already inside the unit/integration suite which all
   passed).

5. **INDEX.md regen was NOT in the slice commit** (the handoff
   manifest mentioned it was regenerated; the team committed an
   updated INDEX in the slice). Main Branch re-regenerated INDEX
   as part of the verification commit. Both versions show
   identical "Pending" content — the regen is idempotent.

6. **`recommendation_id` is deterministic** per the brief §1
   formula: `rec_<run_reference>_<sha1(category|primary_slot)[:8]>`.
   The sha1 prefix on `localization-branch` rec[3] (divide bug)
   would be stable across runs of the same fixture; only the
   `run_reference` portion changes per-run. Manual Test does NOT
   need to assert prefix stability across runs — the determinism
   test (Scenario F) covers the recommendation set as a whole.

## Final disposition gate

If Manual Test's run reports:

- ✅ Scenario A: default suite green (871 + 5) on your host
- ✅ Scenario B: mypy strict clean (80 src files)
- ✅ Scenario C: `all_green` envelope on `pytest-basic` matches
- ✅ Scenario D: `investigate_location` chain on `localization-branch`
  matches (incl. bug-site at rec[3] = divide@34 score 1.0;
  unavailable_analysis at rec[-1] with `reason_per_stage.regression
  = no-comparable-baseline`)
- ✅ Scenario E: default-verb alias activates (alias on non-reserved,
  off for `run`/reserved verbs, bare → help)
- ✅ Scenario F: 3-consecutive-run determinism (sha1 of normalized
  envelopes match)
- ✅ Scenario G: round-trip pin tests pass
- ✅ Scenario H: `inspect` populates `recommendations` field (with
  the caveat that this surface was brief-permissive — report
  whatever shape you observe)

→ then Phase 6 entry is closed PASSED. PM ticks
`delivery-phasing.md:96` + `delivery-phasing.md:249-252` at cycle
close.

If any scenario fails, write a finding under `agent-comms/findings/`
per your charter. Open questions Q1/Q2/Q3 in the handoff are
forward-looking design questions for PM — not gating for this
verification cycle.
