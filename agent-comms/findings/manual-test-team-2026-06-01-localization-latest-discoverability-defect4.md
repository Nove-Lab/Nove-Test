---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-06-01
slug: localization-latest-discoverability-defect4
verdict: passed
verifies: agent-comms/verifications/2026-06-01-localization-latest-discoverability-defect4.md
merged_commit: 4b5fd1d
related:
  - agent-comms/history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md
  - agent-comms/findings/manual-test-team-2026-06-01-localization-aggregate-fixture-redesign-and-defect3.md
  - src/novetest/localization/retrieval.py
  - src/novetest/localization/derive.py
---

# Findings: Defect 4 closed — `novetest localization latest` discovers all 3 modes (verdict: **passed**)

## TL;DR for the CEO

**The bug we shipped a fix for is fixed.** Before this slice, the `latest` shorthand verb (`novetest localization latest`) silently returned "no analyzable runs" for 3 of the 4 supported languages — even though typing the explicit run ID worked perfectly. Cargo (Rust), go test (Go), jest (JS), AND any coverage-less Python run all hit this dead end. Defect 4 was the gate inside the resolver hardcoding `coverage.mapping_granularity == "per-test"` — relaxed in this slice to match the 3-mode dispatcher that the explicit-`<run_id>` path was already using.

Empirically verified on the merged tip (`4b5fd1d`) against 3 real fixtures + 2 fresh sandboxes:

- **Scenario A** (cargo aggregate): now returns `kind: fact-set, mode: sbfl_aggregate` with `src/arithmetic.rs` at rank 1, Ochiai 0.5 — byte-for-byte matching Main Branch's predicted envelope.
- **Scenario B** (failure_proximity, pytest no-coverage): now returns `kind: fact-set, mode: failure_proximity` with `statistics.py` at rank 1.
- **Scenario C** (per-test regression-pin): unchanged from pre-Defect-4 — still returns `mode: sbfl_per_test` with `divide` symbol at rank 1, Ochiai 1.0.

**Bonus:** While walking the new "all 3 modes reachable through `latest`" surface, two pre-existing orthogonal bugs surfaced that the prior gate had been hiding. Manual Test was able to **root-cause-localize Defect 5** empirically — see §"Defect 5: triangulated to cache-read path" below. Recommend filing both as PM-triage tickets but neither blocks Defect 4 closure.

**Net surface confirmed**: 2 src files modified (gate + docstring; ZERO new src files), 72 source files stays the same (no count drift), pytest gate 762 passed + 5 skipped in 52.26s (matches Main Branch's claim byte-accurate), mypy strict clean.

## What was tested

| # | Scope | Verdict |
|---|---|---|
| Gate | `uv run pytest -q` (full project) | PASS 762 passed + 5 skipped in 52.26s |
| Gate | `uv run mypy --strict src` | PASS 0 issues in 72 source files |
| Gate | `uv run pytest tests/integration/localization/ -q` | PASS 12 passed in 7.78s |
| A | cargo aggregate via `latest` | PASS smoking gun byte-accurate |
| B | failure_proximity via `latest` | PASS all assertions match |
| C | sbfl_per_test via `latest` (regression-pin) | PASS unchanged from pre-Defect-4 |
| D | `latest` ≡ `<run_id>` cross-verb consistency | PASS only `command` field differs |
| E | `--formula` / `--top-n` flag probe | DEFECT 5 ROOT-CAUSE LOCALIZED |
| F | Passing-only run still unanalyzable | PASS `reason: run_not_analyzable` |
| G | Empty store still unanalyzable | PASS `reason: no_run_evidence` |
| H | `inspect` vs `status.sub_reports` cross-check | DEFECT 6 reproduces |
| Edge 3 | Resolver walks past passing-only newer run | PASS E2E confirms unit test |
| Edge 4 | Coverage shape transition (per-test -> no-coverage) | PASS failure_proximity selected |
| Edge 1 | Mixed-engine store | NOT-EXECUTED (see notes) |
| Edge 2 | Tombstoned run | NOT-EXECUTED (no CLI surface) |

## Detailed Scenarios

### Scenario A — Defect 4 closure proof (cargo aggregate via `latest`)

**Commands** (verbatim):
```sh
. "$HOME/.cargo/env"
rm -rf /tmp/d4-cargo
cp -r tests/fixtures/projects/localization-aggregate-only /tmp/d4-cargo
cd /tmp/d4-cargo
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run --coverage >/dev/null 2>&1
novetest localization latest
```

**Observed envelope** (truncated for length — full output captured in session log):
```json
{
  "command": "localization.latest",
  "data": {
    "localization_outcome": {
      "kind": "fact-set",
      "mode": "sbfl_aggregate",
      "confidence": "medium",
      "ecosystem": "rust",
      "engine_name": "cargo-test",
      "formula": "ochiai",
      "alternate_scores_available": ["dstar2", "op2", "tarantula"],
      "metadata": {"changed_files_count": 0, "regression_reweighted": false},
      "top_n": 10,
      "run_reference": {"run_id": "01KT0GRSK2HKK0CRNSWJWFCCQV", "...": "..."},
      "entries": [
        {
          "rank": 1,
          "score_raw": 0.5,
          "score_normalized": 0.0,
          "code_location": {
            "file": "src/arithmetic.rs",
            "kind": "file",
            "primary_line": 53,
            "evidence_lines": [53],
            "line_range": null, "symbol": null
          },
          "related_failed_tests": ["localization_aggregate_only::localization_aggregate_only$arithmetic::tests::test_divide"],
          "tied_with": [],
          "alternate_scores": {"dstar2": 0.3333333333333333, "op2": 0.25, "tarantula": 0.5}
        }
      ]
    }
  },
  "ok": true, "errors": [], "warnings": [], "schema": "novetest/v1"
}
```

**Assertion-by-assertion verification against Main Branch's expected**:

| Field | Expected | Observed | Pass? |
|---|---|---|---|
| `kind` | `"fact-set"` (not `"unavailable"`) | `"fact-set"` | YES |
| `mode` | `"sbfl_aggregate"` | `"sbfl_aggregate"` | YES |
| `confidence` | `"medium"` | `"medium"` | YES |
| `entries[0].rank` | `1` | `1` | YES |
| `entries[0].code_location.file` | `"src/arithmetic.rs"` | `"src/arithmetic.rs"` | YES |
| `entries[0].code_location.primary_line` | `53` | `53` | YES |
| `entries[0].score_raw` | `0.5` (Ochiai: 1/sqrt((1+0)*(1+3))) | `0.5` | YES |
| `entries[0].alternate_scores.dstar2` | `0.333...` | `0.3333333333333333` | YES |
| `entries[0].alternate_scores.op2` | `0.25` | `0.25` | YES |
| `entries[0].alternate_scores.tarantula` | `0.5` | `0.5` | YES |
| `top_n` | `10` | `10` | YES |

**Conclusion**: Defect 4 is closed. Pre-fix this command returned `kind: "unavailable", reason: "run_not_analyzable", detail: "no analyzable runs in store (1 candidates checked)"`. Post-fix it returns a full fact-set with the bug file at rank 1.

---

### Scenario B — failure_proximity via `latest`

**Setup**: copied `localization-no-coverage` to `/tmp/d4-pyfp`, ran `novetest run` (no `--coverage`), then `novetest localization latest`.

| Field | Expected | Observed | Pass? |
|---|---|---|---|
| `kind` | `"fact-set"` | `"fact-set"` | YES |
| `mode` | `"failure_proximity"` | `"failure_proximity"` | YES |
| `confidence` | `"low"` | `"low"` | YES |
| `entries[0].code_location.file` | ends with `"statistics.py"` | `/tmp/d4-pyfp/localization_no_coverage/statistics.py` | YES |
| `entries[0].code_location.primary_line` | `39` | `39` | YES |
| `alternate_scores_available` | `[]` | `[]` | YES |
| `entries[0].alternate_scores` | `{}` | `{}` | YES |
| `entries[0].score_raw` | `1.0` | `1.0` | YES |

**Confirmed mode quirk**: `failure_proximity` emits **absolute** file paths (e.g., `/tmp/d4-pyfp/.../statistics.py`). Scenarios A and C emit **repo-relative** paths (`src/arithmetic.rs`, `localization_branch/calculator.py`). This is a UX inconsistency Main Branch flagged — see §"Recommendations" below.

---

### Scenario C — sbfl_per_test regression-pin via `latest`

**Setup**: copied `localization-branch` to `/tmp/d4-pypt`, ran `novetest run --coverage`, then `novetest localization latest`.

| Field | Expected | Observed | Pass? |
|---|---|---|---|
| `kind` | `"fact-set"` | `"fact-set"` | YES |
| `mode` | `"sbfl_per_test"` (unchanged from pre-Defect-4) | `"sbfl_per_test"` | YES (load-bearing) |
| `confidence` | `"high"` | `"high"` | YES |
| `entries[0].rank` | `1` | `1` | YES |
| `entries[0].code_location.file` | `"localization_branch/calculator.py"` | `"localization_branch/calculator.py"` | YES |
| `entries[0].code_location.symbol` | `"divide"` | `"divide"` | YES |
| `entries[0].code_location.kind` | `"symbol"` (NOT `"file"`) | `"symbol"` | YES |
| `metadata` | `{}` (per-test specific) | `{}` | YES |
| `entries[0].tied_with` | `["entry_index_1"]` | `["entry_index_1"]` | YES |
| `entries[0].alternate_scores.op2` | `1.0` | `1.0` | YES |
| `entries[0].alternate_scores.tarantula` | `1.0` | `1.0` | YES |
| `entries[0].alternate_scores.dstar2` | `0.0` | `0.0` | YES |
| `top_n` | `10` | `10` | YES |

**Confirmed mode quirk #2**: `metadata` shape is **mode-specific**:
- `sbfl_per_test` -> `{}`
- `sbfl_aggregate` + `failure_proximity` -> `{"changed_files_count": 0, "regression_reweighted": false}`

The per-test regression-pin was the load-bearing concern — pre-Defect-4 behavior preserved.

---

### Scenario D — Cross-verb consistency

```sh
cd /tmp/d4-cargo
RUN_ID=$(novetest status 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['latest_run_reference']['run_id'])")
# RUN_ID=01KT0GRSK2HKK0CRNSWJWFCCQV

novetest localization "$RUN_ID" > /tmp/d4-explicit.json
novetest localization latest    > /tmp/d4-latest.json
diff /tmp/d4-explicit.json /tmp/d4-latest.json
```

**Observed diff** (byte-for-byte matches Main Branch's expected):
```
2c2
<   "command": "localization",
---
>   "command": "localization.latest",
```

Diff exit code: `1` (one line differs). **Only the top-level `"command"` field differs.** `derived_at`, `run_reference`, `entries`, `mode`, everything else byte-identical.

**Implication**: The persisted findings file (`<store>/.novetest/localization/findings/run_<id>/localization_findings.json`) is read back on subsequent calls — no re-derive. This is the foundation for Defect 5 below.

---

### Scenario E — `--formula` / `--top-n` flag probe -> **Defect 5 ROOT-CAUSE LOCALIZED**

I ran Probes A, B1, B2, then a **carefully-corrected Probe C** (Main Branch's documented path `/tmp/d4-cargo/.novetest/store/projects/*/localization/` does NOT exist — actual layout is `/tmp/d4-cargo/.novetest/localization/findings/run_*/localization_findings.json`).

**Probes A + B (cached path — flags IGNORED)**:

| Command | `formula` | `top_n` | `score_raw` | `entries[0].formula` |
|---|---|---|---|---|
| `latest --formula op2 --top-n 3` | `ochiai` | `10` | `0.5` | `ochiai` |
| `latest --formula dstar2 --top-n 1` | `ochiai` | `10` | `0.5` | `ochiai` |
| `latest --formula tarantula --top-n 5` | `ochiai` | `10` | `0.5` | `ochiai` |

All three flags **silently ignored**. Output identical to Scenario A's default-flags call.

**Probe C (post-delete — flags RESPECTED)**:

After `rm -rf /tmp/d4-cargo/.novetest/localization` (the real path), I re-ran `novetest localization latest --formula op2 --top-n 3`:

| Field | Pre-delete (cached) | Post-delete (fresh derive) | Diff |
|---|---|---|---|
| `formula` (top-level) | `ochiai` | **`op2`** | YES flag applied |
| `top_n` | `10` | **`3`** | YES flag applied |
| `alternate_scores_available` | `["dstar2", "op2", "tarantula"]` | **`["dstar2", "ochiai", "tarantula"]`** | YES ochiai swapped in (op2 is now primary) |
| `entries[0].formula` | `ochiai` | **`op2`** | YES flag applied |
| `entries[0].score_raw` | `0.5` (Ochiai math) | **`0.25`** (Op2 math: `1 - 3/(0+3+1) = 0.25`) | YES flag applied |

**Persisted file re-created post-derive** (`localization_findings.json` = 1929 bytes, was 1930 bytes pre-delete).

**Conclusion — Defect 5 root-cause localized**: the **cache-read code path** in `novetest localization {<run_id>,latest}` does not apply CLI flags. The first call's `--formula`/`--top-n` (or defaults if absent) get baked into the persisted findings file, and ALL subsequent calls just read it back regardless of what flags they pass. **The flag-handling logic itself works** — proven by Probe C — the bug is in the cache layer not invalidating when CLI flags don't match the persisted state.

This is a clean root-cause localization, not a "something is broken somewhere" report. PM has actionable triage data.

---

### Scenario F — Passing-only run stays unanalyzable

Bootstrapped a 2-test "all green" project under `/tmp/d4-passing`. `novetest run` -> `status=passed`. Then:

```sh
$ novetest localization latest
{
  "data": {"localization_outcome": {
    "kind": "unavailable",
    "reason": "run_not_analyzable",
    "detail": "no analyzable runs in store (1 candidates checked)",
    "run_reference": null
  }}, "ok": true
}
```

| Field | Expected | Observed | Pass? |
|---|---|---|---|
| `kind` | `"unavailable"` | `"unavailable"` | YES |
| `reason` | `"run_not_analyzable"` | `"run_not_analyzable"` | YES |
| `detail` | `"no analyzable runs in store (1 candidates checked)"` | exact match | YES |

The relaxed gate did NOT over-relax — runs with no failed tests still get correctly rejected.

---

### Scenario G — Empty store

Bootstrapped `/tmp/d4-empty` with `novetest init` (no run). Then:

```sh
$ novetest localization latest
{
  "data": {"localization_outcome": {
    "kind": "unavailable",
    "reason": "no_run_evidence",
    "detail": "no runs in store",
    "run_reference": null
  }}, "ok": true
}
```

| Field | Expected | Observed | Pass? |
|---|---|---|---|
| `reason` | `"no_run_evidence"` (distinct from F's `"run_not_analyzable"`) | `"no_run_evidence"` | YES |
| `detail` | `"no runs in store"` | exact match | YES |

The two unavailable cases are correctly distinguished by literal `reason` codes.

---

### Scenario H — `inspect` vs `status.sub_reports` cross-check -> **Defect 6 reproduces**

Reused `/tmp/d4-cargo` from Scenario A. Cross-checked all three surfaces against the same run:

```
RUN_ID=01KT0GRSK2HKK0CRNSWJWFCCQV

===STATUS sub_reports===
{'coverage': 'unavailable', 'localization': 'unavailable', 'regression': 'unavailable', 'replay': 'unavailable'}

===INSPECT===
loc.kind: fact-set | loc.mode: sbfl_aggregate
cov.kind: fact-set | cov.mapping_granularity: aggregate | cov.percent_covered: None

===localization latest (Scenario A above)===
kind: fact-set | mode: sbfl_aggregate
```

**`status.sub_reports.*` is universally `"unavailable"`** even though `inspect` AND `localization latest` BOTH return fact-sets for the same run. The on-disk state confirms the facts are real:

```sh
$ cat /tmp/d4-cargo/.novetest/localization/findings/run_*/localization_findings.json | python3 -c "..."
# 1930 bytes, has rank-1 entry for src/arithmetic.rs
$ cat /tmp/d4-cargo/.novetest/coverage/facts/run_*/coverage_facts.json | python3 -c "..."
# mapping_granularity: aggregate, summary.percent_covered: 85.71, 3 covered files
```

**Confirmed Defect 6** as Main Branch documented — `status.sub_reports.*` is disconnected from on-disk derived facts. The same pattern affects coverage too (`status` says `coverage: unavailable`; `inspect` says `cov.kind: fact-set`; on-disk file exists with 85.71% coverage).

**Sub-observation worth flagging**: `inspect` envelope reports `cov.percent_covered: None` but the on-disk coverage facts have `summary.percent_covered: 85.71`. The `inspect` surface appears to be reading the wrong field (top-level `percent_covered` vs `summary.percent_covered`). This may be a second sub-bug at the `inspect` layer — bundle into Defect 6 triage.

**Load-bearing for THIS slice**: Defect 4 closure is NOT undermined. `localization latest` AND `inspect` BOTH work correctly post-fix. The bug is in `status`'s reporting surface, not in the localization derivation.

---

### Critical Edge Cases

#### Edge 3 — Resolver walks past passing-only newer run

Built `/tmp/d4-walk` with a tunable failing/passing pytest test. Ran twice:

1. **RUN 1** (failing): `01KT0GXYT24Q25BMA3AR9N5WPK` <- assert == 99
2. **RUN 2** (passing, NEWER): `01KT0GY042NXXHSG3AQC9ZA38B` <- flipped to assert == 5

Then `novetest localization latest`:
```
kind: fact-set
mode: sbfl_per_test
resolved_run_id: 01KT0GXYT24Q25BMA3AR9N5WPK   <- walked past RUN 2, landed on RUN 1
confidence: high
entries count: 2
```

**E2E confirms the unit-test guarantee** `test_resolve_latest_walks_past_passing_only_to_first_with_failed_tests`. The CLI walks newest-first and skips passing-only runs.

#### Edge 4 — Coverage shape transition (per-test -> no-coverage)

Continuing in `/tmp/d4-walk` (already 2 runs). Flipped test back to failing. Then:

3. **RUN 3** (failing, `--coverage`, per-test): `01KT0GYEZEPF6JBYTHTZKSF0D0`
4. **RUN 4** (failing, NO `--coverage`, no-coverage): `01KT0GYG724G8CETJ7J0EP2DN1`

Then `novetest localization latest`:
```
kind: fact-set
mode: failure_proximity                      <- NOT sbfl_per_test (didn't "remember")
resolved_run_id: 01KT0GYG724G8CETJ7J0EP2DN1  <- NEWEST run picked
confidence: low
```

**Resolver is mode-agnostic** — newest analyzable wins regardless of coverage shape. The "doesn't remember the per-test path" guarantee holds.

#### Edge 1 — Mixed-engine store (NOT-EXECUTED)

**Reason**: a single `.novetest/` store ties to a single project/engine via `novetest init` resolving the engine at init time. The verification doc suggested a sibling-subdir setup, which isn't supported by current fixtures. The resolver code itself is engine-agnostic (it walks `list_run_history` and checks `not tombstoned AND has failed tests`), so the property is structurally satisfied. **Recommend deferring to a future cross-engine integration fixture** if PM wants belt-and-suspenders coverage.

#### Edge 2 — Tombstoned run (NOT-EXECUTED)

**Reason**: There is no `novetest tombstone <run_id>` CLI surface (Memory's tombstoning is internal). Hand-editing a Memory Entry would require source-modification reach which is outside Manual Test's charter. **The resolver checks `entry.tombstoned_at is not None`** (verified by reading `retrieval.py:96-97`) — unit-tested at the source level. **Recommend deferring**.

---

## Defect 5 — `--formula` / `--top-n` flags ignored on cached reads

**Surface**: `novetest localization <run_id> --formula <name> --top-n <N>` AND `novetest localization latest --formula <name> --top-n <N>`.

**Reproducer** (minimal):
```sh
cp -r tests/fixtures/projects/localization-aggregate-only /tmp/d5-repro
cd /tmp/d5-repro
. "$HOME/.cargo/env"
export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH
novetest init >/dev/null
novetest run --coverage >/dev/null 2>&1

# Call 1: implicit default -> ochiai, top_n=10 baked into persisted file
novetest localization latest > /dev/null

# Call 2: explicit op2, top_n=3 -> SHOULD apply, but does NOT
novetest localization latest --formula op2 --top-n 3 | grep -E '"formula"|"top_n"'
#   "formula": "ochiai"        <- BUG: flag silently dropped
#   "top_n": 10                <- BUG: flag silently dropped

# Proof flag-handling logic works (cache layer is the bug):
rm -rf .novetest/localization
novetest localization latest --formula op2 --top-n 3 | grep -E '"formula"|"top_n"'
#   "formula": "op2"           <- post-cache-delete, flag applied
#   "top_n": 3                 <- post-cache-delete, flag applied
```

**Root cause**: The cache-read path in the `localization` CLI surface (or in `read_localization_findings_raw`) does not invalidate when CLI flags don't match the persisted state. **The flag-handling logic itself is correct** — proven by the post-delete probe.

**Severity**: medium. Defaults always work; only users who pass `--formula` or `--top-n` AFTER a first call hit this. Workaround: delete `.novetest/localization/findings/run_<id>/` before passing alternate flags. UX surprise but not data corruption.

**Recommended next step (PM)**: file as a localization-team task. The fix surface is small — likely a hash-of-flags cache key OR re-derive-unless-flags-match-persisted check in the CLI/orchestration entry point. **Manual Test does not prescribe a fix, just hands over the data.**

## Defect 6 — `status.sub_reports.*` disconnected from on-disk state

**Surface**: `novetest status` output's `data.sub_reports` dict.

**Reproducer** (minimal — reuses Scenario A's `/tmp/d4-cargo`):
```sh
cd /tmp/d4-cargo
novetest status 2>&1 | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['sub_reports'])"
# {'coverage': 'unavailable', 'localization': 'unavailable', 'regression': 'unavailable', 'replay': 'unavailable'}

RUN_ID=$(novetest status 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['latest_run_reference']['run_id'])")
novetest inspect "$RUN_ID" 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print('loc:', d['data']['localization_outcome']['kind'])"
# loc: fact-set                <- CONTRADICTS status.sub_reports.localization

ls .novetest/localization/findings/run_$RUN_ID/localization_findings.json
# -rw------- 1 ... 1930 ... (exists, valid)
```

`status.sub_reports.localization == "unavailable"` even though the on-disk findings file exists AND both `inspect` and `localization latest` return `kind: "fact-set"` for the same run.

**Same pattern reproduces for coverage**: `sub_reports.coverage: unavailable` despite `inspect.coverage_outcome.kind: fact-set` and a valid coverage_facts.json on disk.

**Sub-observation**: `inspect`'s `coverage_outcome.percent_covered` field returns `None` while on-disk `summary.percent_covered` is `85.71`. Looks like inspect reads the wrong nested path. May be a separate `inspect`-surface field-mapping bug, or it's the same underlying disconnect at a different layer.

**Severity**: medium. The advertised `status` summary lies about engine readiness. AI agents (the primary consumers of the envelope) may treat `"unavailable"` as truth and skip downstream invocations of `localization`/`coverage` that would actually work. Manual users see contradictory signals.

**Recommended next step (PM)**: file as an orchestration-team triage. Likely root cause: `status.sub_reports.*` evaluates a stale or wrong precondition (perhaps pre-Defect-4 `mapping_granularity == "per-test"` semantics that was relaxed in `retrieval.py` but not in the `status` reporting layer).

## Other observations (non-blocking, worth tracking)

1. **Verification doc nit — Probe C path is stale**: Main Branch's documented path `/tmp/d4-cargo/.novetest/store/projects/*/localization/` does not exist. Actual layout is `/tmp/d4-cargo/.novetest/localization/findings/run_*/`. The wildcard silently matches nothing, so a naive copy-paste of Probe C from the doc would fail to invalidate the cache and falsely conclude flags-don't-take-effect at all. I caught this by inspecting `find .novetest -type f` and re-ran with the correct path; the corrected probe is what produced the Defect 5 root-cause localization. **Recommend Main Branch update their dry-run script to use the actual store layout** before next verification doc; otherwise Manual Test has to second-guess the path. This is a doc-quality nit — does NOT undermine the slice. (Only doc nit in this cycle — verification doc otherwise byte-accurate.)

2. **Two pre-existing UX inconsistencies now reachable through `latest`** (Main Branch flagged these — I confirmed both):
   - `metadata` shape asymmetry: per-test -> `{}`, aggregate/failure_proximity -> `{"changed_files_count": 0, "regression_reweighted": false}`. Either normalize one direction or document the contract.
   - File-path absoluteness asymmetry: `failure_proximity` emits absolute paths (`/tmp/d4-pyfp/.../statistics.py`); `sbfl_aggregate`/`sbfl_per_test` emit repo-relative paths (`src/arithmetic.rs`, `localization_branch/calculator.py`). Recommend normalizing to repo-relative for consistency with `inspect`'s file-link semantics. (Probably a one-line `os.path.relpath` in failure_proximity's code-location builder.)

## Recommendations for PM

1. **Close 2026-06-01 Loc Defect 4 cycle as `passed`** — load-bearing fix proven byte-accurate on merged tip `4b5fd1d`. Phase 4 §4 modes-related work narrative LANDS (matches Main Branch's task brief).

2. **File Defect 5 as a follow-up task** (localization-team): cache-read path ignores `--formula`/`--top-n` flags. Root cause already localized to "cache invalidation should consider CLI flags". Reproducer included above. Severity: medium.

3. **File Defect 6 as a follow-up task** (orchestration-team): `status.sub_reports.*` disconnected from on-disk derived state. Affects coverage and localization equally; possibly regression and replay too (both show `unavailable` in my Scenario H output too, but I didn't probe their on-disk state). Reproducer included above. Severity: medium.

4. **Doc-quality nudge to Main Branch**: their Probe C path (`/tmp/d4-cargo/.novetest/store/projects/*/localization/`) doesn't exist; actual layout is `/tmp/d4-cargo/.novetest/localization/findings/run_*/`. Update next verification doc to reflect actual store layout, OR — more durably — add a helper script `tools/locate_findings.sh <project_dir>` that prints the correct path so verification docs don't go stale on layout changes.

5. **Optional**: file the two UX normalizations (metadata shape + file-path absoluteness) as low-priority Localization polish if you want belt-and-suspenders before MVP. Both are visible-on-the-CLI but neither breaks AI-agent consumption.

## End state

- Verdict: **passed**.
- Gate: 762 passed + 5 skipped in 52.26s. mypy strict clean at 72 source files.
- Loc integration trio: 12 passed in 7.78s (new tests included).
- All 8 scenarios + 2 of 4 critical edges executed; remaining 2 edges noted as structurally-satisfied or out-of-charter.
- Two orthogonal defects (5, 6) empirically confirmed and one of them (Defect 5) root-cause-localized to the cache-read path.
- Sandboxes preserved at `/tmp/d4-cargo`, `/tmp/d4-pyfp`, `/tmp/d4-pypt`, `/tmp/d4-passing`, `/tmp/d4-empty`, `/tmp/d4-walk` for any follow-up probing PM/CEO want to do directly.

**For Manual Test follow-up authorization**: this findings file is ready to commit. Push remains gated on CEO/Main-Branch authorization per Manual Test charter.
