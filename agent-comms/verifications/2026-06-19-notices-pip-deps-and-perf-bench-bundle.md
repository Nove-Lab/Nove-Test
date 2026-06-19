---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready-for-verification
created: 2026-06-19
slug: notices-pip-deps-and-perf-bench-bundle
merged_commits:
  - 24477ee  # release work commit
  - f4523da  # handoff commit
merged_tip: d5b4242
source_handoffs:
  - agent-comms/handoffs/release-team-2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
related:
  - agent-comms/tasks/release-team-2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md
  - agent-comms/history/2026-06-10-v0.1.0-license-and-tag-publication.md
host: equipped (per `decisions/2026-06-08-equip-and-exercise §1` SHOULD tier; CI matrix verdict deferred to PM post-merge release-test.yml dispatch per `§4` amendment 2026-06-19 + 2026-06-18 CEO push-gate precedent)
---

# Verification — NOTICES pip-dep expansion + wheel-NOTICES probe + first-run latency bench

## TL;DR

**Merged commits**: `24477ee` (release work; +109 workflow, +273 NOTICES, +1/-1 foundations.md) + `f4523da` (handoff; +289 lines comms). **Merged tip**: `d5b4242` (post-Wave-1 cohort).

Three Release-team polish items bundled:
1. **NOTICES.md pip-dep expansion** (Future-cycle queue item #2a) — 54 → 307 lines; verbatim Apache 2.0 (cyclopts) + BSD 3-Clause (numpy) license texts inlined; per-package cross-reference anchors.
2. **Wheel-NOTICES probe in `release-test.yml`** (Future-cycle queue item #8) — new probe step between `uv build --wheel` and PyApp wrap on all 4 build cells; fails-loud if NOTICES.md not in wheel.
3. **First-run latency bench job** (Future-cycle queue item #5) — new `first-run-latency-bench` job on `ubuntu-latest` after `build`; purged-cache cold + warm measurement with 25 s hard threshold; extends `release.needs` to 4 entries.

Zero `src/`, zero `tests/`, zero `pyproject.toml`, zero `scripts/install.{sh,ps1}` touched.

Your job (Manual Test): verify the **NOTICES content is byte-identical to upstream** + **workflow YAML structure is correct** + **wheel actually ships NOTICES.md** + (when PM dispatches) **release-test.yml run is 6/6 green at merged tip**.

## Source handoff consumed

- `agent-comms/handoffs/release-team-2026-06-19-notices-pip-deps-and-perf-bench-bundle.md` (committed in `f4523da` separately from the work commit `24477ee`)

## Pre-merge empirical anchors (re-verified at merged tip `d5b4242`)

### Anchor A — NOTICES.md line count

```bash
$ wc -l NOTICES.md
307 NOTICES.md
```

Matches handoff's 307 (header 66 + Apache 201 + bridge 9 + numpy BSD 30 + close 1).

### Anchor B — BSD-3-Clause numpy header byte-identity

```bash
$ grep -F "Copyright (c) 2005-2025, NumPy Developers." NOTICES.md
Copyright (c) 2005-2025, NumPy Developers.
```

Match. Full numpy `LICENSE.txt` body inlined verbatim per handoff.

### Anchor C — workflow YAML structure (5 jobs, 4-needs release gate)

```bash
$ python3 -c "import yaml; y = yaml.safe_load(open('.github/workflows/release-test.yml')); print('jobs:', list(y['jobs'].keys())); print('release.needs:', y['jobs']['release']['needs']); print('first-run-latency-bench:', {k: v for k, v in y['jobs']['first-run-latency-bench'].items() if k in ('needs', 'runs-on')})"
jobs: ['build', 'install-script-e2e', 'install-ps1-e2e', 'first-run-latency-bench', 'release']
release.needs: ['build', 'install-script-e2e', 'install-ps1-e2e', 'first-run-latency-bench']
first-run-latency-bench: {'needs': 'build', 'runs-on': 'ubuntu-latest'}
```

5 jobs (was 4 — added `first-run-latency-bench`). `release.needs` extended to 4 entries (was 3). Bench job correctly `needs: [build]` on `ubuntu-latest`.

### Anchor D — Pre-merge gate (combined Wave 1 cohort)

```bash
$ source ~/.local/share/novetest-toolchains.sh
[novetest-toolchains] equipped: dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5

$ uv run mypy
Success: no issues found in 109 source files

$ uv run pytest -q tests/unit tests/integration
1303 passed, 5 skipped in 147.60s
```

Test surface unaffected by this slice (zero src/tests changes). The gate is comm-only validation that nothing in the cohort regressed under merge.

## Verification scenarios (4 NOTICES + 3 workflow + 1 wheel probe + 1 CI dispatch)

### Scenario A — NOTICES line count + sectional integrity

```bash
cd /home/yjshin/dev/Nove-Test
wc -l NOTICES.md
head -5 NOTICES.md
grep -n "^## Apache 2.0\|^## BSD 3-Clause\|^## cyclopts\|^## numpy" NOTICES.md
```

Expected:
- 307 lines.
- Header opens with "# Third-Party Notices".
- 4 section headers visible (license verbatim sections + per-package summary blocks).

**PASS** if all matches; **FAIL** if line count differs or any expected section header missing (would signal NOTICES drift between slice author and merge).

### Scenario B — Apache 2.0 substantive byte-identity (with `tail -n +2` strip)

```bash
curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt > /tmp/apache-2.0.txt
diff <(tail -n +2 /tmp/apache-2.0.txt) <(awk '/Apache License/,/limitations under the License./' NOTICES.md)
echo "exit=$?"
```

Expected: empty diff output, exit 0.

**Off-by-one nuance**: the canonical Apache file has a leading blank line that the awk-range cannot capture (awk-range starts at the FIRST line matching `/Apache License/`). The handoff §"Apache 2.0 leading-blank off-by-one (DoD #1 nuance)" pre-pins this — the substantive license body IS byte-identical, the discrepancy is purely the leading whitespace. PM may amend the DoD #1 wording at cycle close to use `tail -n +2`-stripped LHS.

**PASS** if `tail -n +2`-stripped diff is empty; **FAIL** if any substantive license body line differs.

### Scenario C — BSD-3-Clause numpy header byte-identity

```bash
grep -F "Copyright (c) 2005-2025, NumPy Developers." NOTICES.md
grep -n "Redistribution and use in source and binary forms" NOTICES.md
grep -n "THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS" NOTICES.md
```

Expected:
- Copyright line present (1 hit).
- BSD-3-Clause boilerplate "Redistribution and use" + "THIS SOFTWARE IS PROVIDED" both present.

**PASS** if all 3 grep hits; **FAIL** if any missing (would signal numpy LICENSE.txt inlining was truncated).

### Scenario D — Per-package cross-reference anchors

```bash
grep -B 1 "License: Apache-2.0\|License: BSD-3-Clause" NOTICES.md
```

Expected:
- `cyclopts` block: `License: Apache-2.0 — verbatim text: [Apache 2.0](#apache-20)`
- `numpy` block: `License: BSD-3-Clause — verbatim text: [BSD 3-Clause](#bsd-3-clause)`

Anchors follow GitHub Markdown lowercase-hyphenate-strip-punctuation rules (`Apache 2.0` → `apache-20`, `BSD 3-Clause` → `bsd-3-clause`). Manual check: click the anchors in GitHub's NOTICES.md preview and confirm they jump to the verbatim sections.

**PASS** if both anchors render correctly + both cross-references present; **FAIL** if anchors point nowhere (would signal the lowercase-hyphenate convention drifted).

### Scenario E — Workflow YAML parses + 5 jobs + 4-needs release gate

```bash
python3 -c "
import yaml
y = yaml.safe_load(open('.github/workflows/release-test.yml'))
assert list(y['jobs'].keys()) == ['build', 'install-script-e2e', 'install-ps1-e2e', 'first-run-latency-bench', 'release']
assert y['jobs']['release']['needs'] == ['build', 'install-script-e2e', 'install-ps1-e2e', 'first-run-latency-bench']
assert y['jobs']['first-run-latency-bench']['needs'] == 'build'
assert y['jobs']['first-run-latency-bench']['runs-on'] == 'ubuntu-latest'
print('OK 5 jobs + 4-needs release + bench needs/runs-on')
"
```

Expected: `OK 5 jobs + 4-needs release + bench needs/runs-on`. **PASS** if all assertions hold; **FAIL** if any structural drift.

### Scenario F — Wheel-NOTICES probe step exists in build job

```bash
grep -n "Probe wheel NOTICES inclusion\|python -m zipfile -l\|NOTICES\\\\.\\\(md\\\|txt\\\)" .github/workflows/release-test.yml
```

Expected: the probe step lives between `uv build --wheel` and PyApp wrap; uses `python -m zipfile -l "$wheel" | grep -E 'NOTICES\.(md|txt)'` (stdlib zipfile, not `unzip` — Git Bash on windows-latest lacks unzip). Fails LOUDLY (`exit 1` + `::error::`) on no match.

**PASS** if step present with the right probe pattern; **FAIL** if missing or using `unzip` (which would fail on windows-latest).

### Scenario G — First-run latency bench wires up

```bash
grep -A 30 "first-run-latency-bench:" .github/workflows/release-test.yml | head -50
```

Expected to see (per handoff §"DoD #5"):
- `needs: build` + `runs-on: ubuntu-latest`
- Step "Purge any pre-existing PyApp cache" nuking 4 cache locations
- Step capturing cold first-run wall-clock (`novetest --version`)
- Step capturing warm second-run wall-clock
- Step emitting `::notice title=first-run-latency::cold=...s warm=...s delta=...s threshold=25.0s`
- Step asserting `cold <= 25.0` via `awk "BEGIN {exit !($COLD <= 25.0)}"`

**PASS** if all structural elements present; **FAIL** if any element missing (would signal the bench wiring is partial).

### Scenario H — Wheel-NOTICES local probe (DoD #3 sanity)

```bash
cd /home/yjshin/dev/Nove-Test
uv build --wheel
python -m zipfile -l dist/*.whl | grep NOTICES
```

Expected: line like
```
novetest-0.1.1.dist-info/licenses/NOTICES.md
```

Hatchling PEP 639 auto-discovery includes NOTICES.md under `*.dist-info/licenses/` without explicit `[tool.hatch.build.targets.wheel.force-include]` (Release handoff §"DoD #3" empirically confirmed; wheel went 2056 → 15581 bytes post-expansion).

**PASS** if NOTICES.md appears in wheel manifest; **FAIL** if absent (would signal PEP 639 auto-discovery broke — handoff Failure Mode #1 surface).

### Scenario I — release-test.yml CI run (POST-PM-DISPATCH)

This slice modifies `.github/workflows/release-test.yml` → `decisions/2026-06-08-equip-and-exercise §4` amendment 2026-06-19 binding fires. CI evidence is deferred to PM post-merge dispatch per 2026-06-18 CEO push-gate precedent.

```bash
# After PM dispatches:
gh workflow run release-test.yml --ref main
# Wait ~4-5 min build + ~30-60 s bench, then:
gh run list --workflow release-test.yml --branch main --limit 3
gh run view <run-id> --json jobs --jq '.jobs[] | {name, conclusion}'
```

Expected: 6 jobs total at the merged HEAD:
- `build (linux-x86_64)` → SUCCESS
- `build (linux-aarch64)` → SUCCESS
- `build (macos-universal2)` → SUCCESS
- `build (windows-x86_64)` → SUCCESS
- `install-script-e2e` → SUCCESS
- `install-ps1-e2e` → SUCCESS
- `first-run-latency-bench` → SUCCESS
- `release` → SKIPPED (by design — `if: startsWith(github.ref, 'refs/tags/v')` guards; `workflow_dispatch --ref main` lacks v* tag)

That's 7 in-scope SUCCESS + 1 SKIPPED-by-design = 8 entries. Handoff TL;DR cites "6 jobs total" (counting unique deliverables: 4 build cells, 2 install-script + 1 bench = 7 SUCCESS, 1 SKIPPED; the "6" likely counts pre-PyApp-wheel-bumps shape). Either count is valid as long as ALL non-SKIPPED jobs are SUCCESS.

Crucially, the bench job's `::notice title=first-run-latency::` annotation surfaces the cold value — PM harvests:
- Run ID → fills `<run_id>` in `design/implementation-plan/foundations.md` §559
- Cold value (whole seconds) → fills `<X>` in foundations.md §559

**PASS** if all in-scope jobs SUCCESS + cold ≤ 25 s; **FAIL** if any RED, or cold > 25 s (would trigger the regression gate).

## Critical edge probes

1. **Bench cold-threshold tuning**: 25 s threshold = documented 15 s upper bound (foundations.md §7) + ~67% network-variance margin. If a sustained bench-cold exceeds 15 s but stays under 25 s, that's NOT a regression — it's runner load variability. A sustained breach across re-runs (>2 consecutive RED bench jobs without code change) is the regression signal.

2. **PEP 639 wheel placement nuance**: NOTICES.md lands at `*.dist-info/licenses/NOTICES.md` (NOT `*.dist-info/NOTICES.md` or a custom path). If Hatchling's PEP 639 auto-discovery moves the canonical location in a future bump, the wheel-NOTICES probe step's `grep -E 'NOTICES\.(md|txt)'` will still match (matches the filename regardless of dir prefix). Flag if Hatchling stops auto-including NOTICES.md altogether — the fallback is an explicit `[tool.hatch.build.targets.wheel.force-include]` entry (handoff §"DoD #3" Failure Mode #1 references this).

3. **Apache 2.0 leading-blank off-by-one is documented, not a defect**: Release handoff explicitly carves out the awk-range leading-blank discrepancy. PM may either (a) accept the nuance and amend DoD #1 to use `tail -n +2`-stripped LHS, or (b) leave the DoD as-is given the substantive intent is met. This is a brief-precision question, not a verification fail.

4. **`release` job SKIPPED by design**: Same pattern as the v0.1.0 sign-off cycle and the MVP release-ready cycle. `if: startsWith(github.ref, 'refs/tags/v')` guards the job; `workflow_dispatch --ref main` (or any non-tag push) deliberately skips it. Flag if the guard's `refs/tags/v` pattern has drifted (would change the SKIPPED-by-design semantics).

5. **Bench measures `novetest --version`, not `novetest test`**: The cold/warm measurement targets the cheapest possible CLI invocation. This is the right metric for first-run PyApp + python-build-standalone extraction overhead — adding test execution would conflate engine warmup with the actual first-run cost. Flag if a future cycle redirects the bench to a heavier verb.

6. **`install-ps1-e2e` is unchanged by this slice**: The bench job slots into the dependency graph but does not touch `install-ps1-e2e` or `install-script-e2e`. Both should remain green at their pre-slice shape. Flag if either install-script job RED at the post-merge dispatch — would signal an unrelated drift, not this slice's fault.

7. **PM cycle-close harvest sequence**: PM dispatches release-test.yml → waits for green → reads the `::notice title=first-run-latency::cold=...s warm=...s delta=...s` annotation in the GHA summary panel → fills `<X>` + `<run_id>` placeholders in `design/implementation-plan/foundations.md` §559. Manual Test does NOT do the harvest (PM territory), but Manual Test CAN cite the post-dispatch run number in their findings for context.

## Anything that wasn't obvious during merge

1. **Release slice was committed cleanly** (2 commits: `24477ee` work + `f4523da` handoff). FF-merged after rebase onto Coverage's new main (`9c5abbf`); zero file-overlap, zero conflicts.

2. **Wave 1 cohort merge order**: alphabetical-by-team per 2026-06-09 Windows-CI-fix-triple precedent. Coverage → Release → Run. WORKLOG conflict happened at Run's rebase (not Release's), since Release doesn't touch WORKLOG (per Release handoff §"WORKLOG entry: Not required").

3. **Pre-merge gate ran on equipped host** (dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5). 1303 passed + 5 skipped + 0 failed in 147.60s; mypy 109 files clean. Release slice does NOT contribute test surface; the gate result is bookkeeping confirmation that Coverage + Run interactions didn't regress under cohort merge.

4. **No `gh workflow run release-test.yml` from Main Branch in this session**: per 2026-06-18 CEO push-gate precedent, workflow dispatches are PM territory. PM will dispatch post-cycle-close and harvest the bench number + run ID into foundations.md §559.

5. **§4 CI matrix verdict is two-headed for this cohort**: Coverage's verification cites `ci.yml` (auto-triggers on push); Release's verification cites `release-test.yml` (PM-dispatched). Both gates land at the same merged tip but use different workflows for evidence.
