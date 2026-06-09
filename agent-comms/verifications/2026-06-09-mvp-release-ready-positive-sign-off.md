---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready-for-verification
created: 2026-06-09
slug: mvp-release-ready-positive-sign-off
merged_commit: fee8c3ded950e88250acefe811c2fd8044747d01
source_handoffs:
  - agent-comms/handoffs/release-team-2026-06-09-mvp-release-ready-positive-sign-off.md
related:
  - agent-comms/tasks/release-team-2026-06-09-mvp-release-ready-positive-sign-off.md
  - agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md
  - agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - design/implementation-plan/foundations.md
  - design/implementation-plan/delivery-phasing.md
host: equipped (per `decisions/2026-06-08-equip-and-exercise-default-verification-posture.md` §1 SHOULD tier — applies to this non-adapter Manual Test verification step; an "equipped" host is the default for ALL `src/` + `tests/` slices, and by symmetric continuity for sign-off integrity passes even though this slice itself touched no `src/` or `tests/`)
---

# Verification — MVP Release-Ready POSITIVE Sign-Off (integrity pass)

## TL;DR

**Merged commit**: `fee8c3d` (FF-merge of
`worktree-mvp-release-ready-positive-sign-off` into `main`).
Comms-only — zero `src/`, zero `tests/`, zero `pyproject.toml`, zero
`.github/workflows/`, zero `scripts/install.sh`, zero
`THIRD_PARTY_NOTICES.txt` touched. The merge diff is purely
`WORKLOG.md` (+10 lines, one new entry) and a new file
`agent-comms/handoffs/release-team-2026-06-09-mvp-release-ready-positive-sign-off.md`
(+323 lines, the sign-off handoff itself).

**Sign-off statement** (binding, copied verbatim from the handoff):

> **MVP release-ready as of `8ae90cd`.** All Phase 0 DoD bullets
> empirically green: (1) `uv run pytest -q` green on 3 OSes × 3 Python
> via `ci.yml` run `27192323843`; (2) signed binary builds via
> `release-test.yml` run `27206024411`; (3) `curl -fsSL <url> | sh`
> end-to-end green; (4) SHA-256 verify + tampered-binary abort test
> green; (5) `novetest -v` and `novetest -h` envelopes structurally
> correct. Vendored JUnit Console Launcher EPL 2.0 attribution per
> decision `2026-06-03-junit-console-launcher-vendor.md` §3
> byte-identically valid.

Your job (Manual Test) is to verify the **integrity of that positive
sign-off** — that every cited workflow run number actually resolves
to a SUCCESS at HEAD `8ae90cd`, that the SHA-256 of the vendored JAR
byte-matches the NOTICES pin at the merged tip, and that the 5 DoD
citations are not over-claiming relative to what the cited evidence
actually exercises. This mirrors yesterday's framing pattern: the
deliverable IS the sign-off, and your verdict pins whether that
sign-off is structurally defensible.

## Source handoff consumed

- `agent-comms/handoffs/release-team-2026-06-09-mvp-release-ready-positive-sign-off.md`
  (commit `fee8c3d`; 323 lines; the sign-off statement is in
  §"Sign-off statement (binding)")

## Pre-merge empirical anchors (re-verified at merge time)

Three claims drive the entire sign-off. I (Main Branch) re-verified
each at the merged tip before opening this verification request:

### Anchor A — `ci.yml` run `27192323843`

```bash
$ gh run view 27192323843 --json status,conclusion,headSha,workflowName,jobs --jq '{status, conclusion, headSha, workflow: .workflowName, jobs: [.jobs[] | {name, conclusion}]}'
```

Observed:
- `workflow`: `CI`
- `status`: `completed`
- `conclusion`: `success`
- `headSha`: `8ae90cde7032cc324bdd2dc87812c56d4d2da28f` (= `8ae90cd`)
- 10 jobs all `success`:
  - `test (ubuntu-latest / py3.11)`
  - `test (ubuntu-latest / py3.12)`
  - `test (ubuntu-latest / py3.13)`
  - `test (macos-latest / py3.11)`
  - `test (macos-latest / py3.12)`
  - `test (macos-latest / py3.13)`
  - `test (windows-latest / py3.11)`
  - `test (windows-latest / py3.12)`
  - `test (windows-latest / py3.13)`
  - `perf (coverage NFR-COV-002, non-blocking)`

The 9 matrix cells map cleanly to 3 OSes × 3 Pythons. The 10th
(`perf`) is the non-blocking NFR-COV-002 lane. All 10 SUCCESS.

### Anchor B — `release-test.yml` run `27206024411`

```bash
$ gh run view 27206024411 --json status,conclusion,headSha,workflowName,jobs --jq '{status, conclusion, headSha, workflow: .workflowName, jobs: [.jobs[] | {name, conclusion}]}'
```

Observed:
- `workflow`: `release-test`
- `status`: `completed`
- `conclusion`: `success`
- `headSha`: `8ae90cde7032cc324bdd2dc87812c56d4d2da28f` (= `8ae90cd`)
- 4 jobs `success` + 1 `skipped`:
  - `build (linux-x86_64)` → SUCCESS
  - `build (linux-aarch64)` → SUCCESS
  - `build (macos-universal2)` → SUCCESS
  - `install.sh end-to-end (linux-x86_64)` → SUCCESS
  - `draft GitHub Release` → SKIPPED (by design — `if:
    startsWith(github.ref, 'refs/tags/v')` guards this job;
    `workflow_dispatch --ref main` deliberately skips it.
    Sign-off Task 1 confirms this is "by design".)

### Anchor C — vendored JUnit JAR SHA-256 vs NOTICES pin

```bash
$ sha256sum src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar
b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc  src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar

$ grep "SHA-256:" src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt
  SHA-256:   b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc
```

Byte-identical. The NOTICES file structure (line-by-line) at merged
tip:

| Line | Field | Value |
|---|---|---|
| 10 | Artifact | `org.junit.platform:junit-platform-console-standalone` |
| 11 | Version | `1.11.4` |
| 12 | Source | `https://github.com/junit-team/junit5` |
| 13 | License | `Eclipse Public License 2.0 (EPL-2.0)` |
| 14 | License URL | `https://www.eclipse.org/legal/epl-2.0/` |
| 15 | SHA-256 | `b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc` |
| 17-19 | EPL 2.0 §3.3 unmodified statement | "The Console Launcher is distributed unmodified per EPL 2.0 §3.3 (Larger Work allowance). Nove Test makes no modifications to the jar. Source code is available at the URL above under the same license." |

All 6 binding fields from decision `2026-06-03-junit-console-launcher-vendor.md`
§3 present. EPL 2.0 §3.3 unmodified-distribution statement present.

## Verification scenarios (5 sign-off integrity checks + 3 structural)

### Scenario A — `ci.yml` 10/10 GREEN re-confirmation

**Goal**: Confirm the citation for DoD #1 / sign-off bullet 1.

```bash
gh run view 27192323843 --json status,conclusion,headSha,workflowName --jq '{workflow: .workflowName, status, conclusion, headSha}'
gh run view 27192323843 --json jobs --jq '.jobs[] | {name, conclusion}'
```

Expected (must match):
- `workflow = "CI"`, `status = "completed"`, `conclusion = "success"`,
  `headSha = "8ae90cde7032cc324bdd2dc87812c56d4d2da28f"`.
- 10 jobs, all `conclusion: "success"`.
- 9 jobs match the pattern `test (<os>-latest / py3.<11|12|13>)`
  for `os ∈ {ubuntu, macos, windows}`.
- 1 job: `perf (coverage NFR-COV-002, non-blocking)`.

Verdict line: **PASS** if all 10 SUCCESS at the cited headSha;
**FAIL** if any cell is RED, CANCELLED, or the headSha mismatches.

### Scenario B — `release-test.yml` SUCCESS re-confirmation

**Goal**: Confirm the citation for DoD #4 / DoD #5 / sign-off bullets
2 + 3 (PyApp 3-cell build + install.sh end-to-end + `.sha256`
sidecars).

```bash
gh run view 27206024411 --json status,conclusion,headSha,workflowName --jq '{workflow: .workflowName, status, conclusion, headSha}'
gh run view 27206024411 --json jobs --jq '.jobs[] | {name, conclusion}'
```

Expected:
- `workflow = "release-test"`, `status = "completed"`, `conclusion = "success"`,
  `headSha = "8ae90cde7032cc324bdd2dc87812c56d4d2da28f"`.
- 5 jobs total:
  - `build (linux-x86_64)` → SUCCESS
  - `build (linux-aarch64)` → SUCCESS
  - `build (macos-universal2)` → SUCCESS
  - `install.sh end-to-end (linux-x86_64)` → SUCCESS
  - `draft GitHub Release` → SKIPPED (the only non-SUCCESS; "by
    design" per Anchor B above)

**Optional artifact probe** (deep check): download the 3 binaries +
their `.sha256` sidecars and verify the sidecars match each binary.
This validates DoD #6 (SHA-256 verify) at the artifact level:

```bash
gh run download 27206024411 --pattern 'novetest-*' --dir /tmp/release-artifacts-27206024411
ls /tmp/release-artifacts-27206024411/
# Expected: 3 binaries + 3 .sha256 sidecars (one pair per build cell)
# Verify each sidecar:
for f in /tmp/release-artifacts-27206024411/**/*.sha256; do
  echo "Checking $f"
  cd "$(dirname "$f")" && sha256sum -c "$(basename "$f")"
done
```

Verdict: **PASS** if the 4 in-scope jobs SUCCESS + `draft GitHub
Release` SKIPPED + (if probed) sidecars match. **FAIL** if any
in-scope job RED or sidecars don't match.

### Scenario C — Vendored JUnit JAR EPL 2.0 attribution

**Goal**: Confirm the sign-off's NOTICES-binding claim.

```bash
cd /home/yjshin/dev/Nove-Test
sha256sum src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar
cat src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt
```

Expected:
- `sha256sum` output ends with
  `b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc`.
- NOTICES file:
  - Line 15 contains the same SHA-256 byte-identically.
  - Lines 9-15 carry the 6 binding fields from decision
    `2026-06-03-junit-console-launcher-vendor.md` §3 (Artifact,
    Version, Source, License, License URL, SHA-256).
  - Lines 17-19 carry the EPL 2.0 §3.3 unmodified-distribution
    statement.

Verdict: **PASS** if SHA-256 matches + all 6 fields + §3.3
statement present. **FAIL** if SHA-256 mismatches (would signal
JAR corruption or NOTICES drift) or any field missing.

### Scenario D — DoD #6 (SHA-256 verify + tampered-abort) test surface

**Goal**: Confirm the sign-off bullet 4 is structurally exercised by
the cited tests, not just transitively asserted.

```bash
cd /home/yjshin/dev/Nove-Test
grep -n "test_install_succeeds_when_sha256_matches\|test_install_aborts_loudly_when_sha256_mismatches" tests/release/test_install_script.py
grep -n "pytestmark" tests/release/test_install_script.py
```

Expected:
- Both test functions exist in `tests/release/test_install_script.py`.
- A `pytestmark` line at module level skips the tests on Windows
  (POSIX-sh `install.sh`; Windows parity is OQ#16 post-MVP per
  `foundations.md` §7).

Cross-reference: the `ci.yml` run `27192323843` SUCCESS on
ubuntu-latest + macos-latest cells implies these two tests passed
there. Verdict: **PASS** if both test names exist + Windows
pytestmark present; **FAIL** if either test is missing or the
Windows skip is gone (would inflate DoD #6 coverage claims).

### Scenario E — DoD #7 (`-v` / `-h` envelopes) test surface

**Goal**: Confirm sign-off bullet 5 is structurally exercised by
syrupy snapshot tests on every matrix cell.

```bash
cd /home/yjshin/dev/Nove-Test
grep -rn "version_envelope\|help_envelope" tests/integration/cli/test_envelope_snapshots.py
```

Expected:
- Both snapshots referenced in test code.
- The test file participates in the `ci.yml` test matrix (no
  `os ==` or `sys.platform ==` skip markers around these two
  snapshots).

Cross-reference: `ci.yml` run `27192323843` 10/10 SUCCESS implies
these snapshots passed on every matrix cell. Verdict: **PASS** if
both snapshots referenced + no platform-skip; **FAIL** if either
missing or skipped.

### Scenario F — Merge diff scope re-confirmation

**Goal**: Confirm the merge truly is comms-only (no silent source
drift that could invalidate the sign-off).

```bash
cd /home/yjshin/dev/Nove-Test
git log --oneline 8ae90cd..fee8c3d
git diff --stat 8ae90cd..fee8c3d
git diff --name-only 8ae90cd..fee8c3d
```

Expected:
- One commit: `fee8c3d comms: handoff Release MVP release-ready
  POSITIVE sign-off at 8ae90cd ...`
- Diff stat: `2 files changed, 333 insertions(+)`.
- Files: exactly
  - `WORKLOG.md`
  - `agent-comms/handoffs/release-team-2026-06-09-mvp-release-ready-positive-sign-off.md`
- NO file under `src/`, `tests/`, `pyproject.toml`, `uv.lock`,
  `.github/workflows/`, `scripts/`, `THIRD_PARTY_NOTICES.txt`.

Verdict: **PASS** if exactly those 2 files; **FAIL** if any source
or workflow file appears (would invalidate the comms-only premise
and require re-running the test gate).

### Scenario G — Sign-off statement byte-presence in the merged handoff

**Goal**: Confirm the binding sign-off text is actually present in
the merged file, not just paraphrased.

```bash
cd /home/yjshin/dev/Nove-Test
grep -n "MVP release-ready as of" agent-comms/handoffs/release-team-2026-06-09-mvp-release-ready-positive-sign-off.md
```

Expected:
- At least one match.
- The match line (or its surrounding block) cites `8ae90cd`.
- The full sign-off block (TL;DR + §"Sign-off statement (binding)")
  enumerates 5 numbered DoD bullets, each pinning a workflow run
  number or test file path.

Verdict: **PASS** if the literal sign-off string is in the merged
file. **FAIL** if absent — would be a process integrity issue
(the deliverable is the sign-off and it must live in the merged
artifact).

### Scenario H — Phase 0 DoD `[x]` markers in `delivery-phasing.md`

**Goal**: Confirm the design-doc audit trail is consistent with the
sign-off.

```bash
cd /home/yjshin/dev/Nove-Test
grep -A 1 "Definition-of-done\|Definition of done" design/implementation-plan/delivery-phasing.md | head -40
grep -c "\[x\]" design/implementation-plan/delivery-phasing.md
```

Expected:
- Phase 0 §"Definition-of-done" section exists.
- All 7 Phase 0 bullets carry `[x]` markers.
- DoD #1 bullet carries the inline audit-trail marker noting the
  5/16 closure + 6/9 re-open + 6/9 re-close sequence (per
  `2026-06-09-windows-ci-fix-triple-coverage-localization-run.md`
  PM disposition #1).

Verdict: **PASS** if all 7 bullets `[x]` + DoD #1 audit trail
intact. **FAIL** if any bullet is `[ ]` or the audit trail marker
is missing (would signal design-doc drift relative to the sign-off
claims).

## Critical edge probes (worth flagging if surfaced)

1. **HEAD SHA shift on FF-merge**: The sign-off cites `8ae90cd`
   (worktree base); the merged tip is `fee8c3d` (FF-merge produced
   one new commit above `8ae90cd`). After this verification commit
   (which adds this very file), the tip will shift one more SHA
   forward. The sign-off remains scoped to `8ae90cd`. The handoff
   §"Worklog entry text → Gotcha (2)" pre-pinned this with
   recommendation option (a): "accept the sign-off as scoped to
   `8ae90cd` with a note that the FF-merge commit is a comms-only
   superset." Since `8ae90cd..fee8c3d` and the subsequent
   verification commit add only `agent-comms/` and `WORKLOG.md`,
   the sign-off transitively applies to all SHAs in this chain.
   Flag if you disagree with the transitive-applies argument.

2. **`draft GitHub Release` SKIPPED is not a failure**: Anchor B
   shows `draft GitHub Release` as SKIPPED. This is by design —
   the `if: startsWith(github.ref, 'refs/tags/v')` guard
   deliberately skips the job on `workflow_dispatch --ref main`
   (no tag). A real release would push a `v*` tag, which
   re-triggers `release-test.yml` with `release` job enabled.
   Flag if the SKIPPED job's `if:` condition has drifted from
   the `refs/tags/v` pattern.

3. **NOTICES vs wheel-inclusion path**: The sign-off cites the
   in-repo NOTICES at `src/novetest/run/adapters/_vendor/
   THIRD_PARTY_NOTICES.txt`. The wheel-inclusion path (via
   `[tool.hatch.build.targets.wheel.force-include]` in
   `pyproject.toml`) was empirically verified yesterday at
   `bd4d300`; structurally unchanged at `8ae90cd` (no
   `pyproject.toml` touches in the Windows-CI fix triple). If
   you want to deep-probe, run:
   ```bash
   uv build --wheel
   unzip -l dist/novetest-*.whl | grep -i 'NOTICES\|notice'
   ```
   Expected: NOTICES file appears in the wheel manifest. This is
   a deeper structural check beyond the strict sign-off integrity
   surface.

4. **Backup citation `27187459586` integrity**: The sign-off
   bullet 1 backup citation is `ci.yml` run `27187459586` on
   `871a278`. Optional re-verify:
   ```bash
   gh run view 27187459586 --json status,conclusion,headSha,jobs --jq '{status, conclusion, headSha, jobs: [.jobs[] | {name, conclusion}]}'
   ```
   Expected: SUCCESS at headSha `871a278...`; 10/10 jobs SUCCESS.
   This run was the Windows-CI fix triple closure moment — the
   first all-green `ci.yml` on `main` since 2026-05-31.

5. **Wall-time variance**: Sign-off Task 1 reports
   `release-test.yml` run `27206024411` total 3m34s vs yesterday's
   `27176266868` total 3m13s (Δ +21s, "well within ±20% GHA
   runner variance"). 21s on 3m13s ≈ +10.9% — comfortably under
   ±20%. Flag if you observe wall-time drift exceeding ±20% in
   any future probe; that would invalidate the "no regression"
   claim.

6. **5 DoD bullet over-claim audit**: For each of the 5 sign-off
   bullets, walk back from cited evidence → DoD bullet → actual
   surface exercised:
   - Bullet 1: `27192323843` exercises `pytest -q` on 9 cells →
     DoD #1 ✅ tight.
   - Bullet 2: `27206024411` exercises 3-cell PyApp build → DoD
     #4 ✅ tight.
   - Bullet 3: `27206024411::install-script-e2e` exercises
     `curl -fsSL ... | sh` → DoD #5 ✅ tight.
   - Bullet 4: `27192323843` Linux + macOS cells exercise
     `tests/release/test_install_script.py` (sha256-verify +
     tampered-abort) → DoD #6 ✅ tight (Windows skipped per
     pytestmark; matches OQ#16 post-MVP scope).
   - Bullet 5: `27192323843` every cell exercises
     `tests/integration/cli/test_envelope_snapshots.py` (syrupy
     `version_envelope` + `help_envelope`) → DoD #7 ✅ tight.
   Verdict line: **PASS** unless you find a bullet whose cited
   evidence does not actually exercise the claimed DoD surface.

7. **NOTICES wheel-shipping policy**: Decision
   `2026-06-03-junit-console-launcher-vendor.md` §3 mandate
   includes "MUST surface this notice file's contents" via a
   `novetest --licenses` CLI surface. Sign-off explicitly defers
   this to post-MVP polish (per yesterday's PM disposition #3).
   If you believe the EPL 2.0 attribution is incomplete absent
   the CLI surface, flag — but the consensus position
   (handoff + PM dispositions) is that the in-wheel NOTICES file
   satisfies the EPL 2.0 §3.3 distribution requirement and the
   CLI surface is a UX polish, not a license obligation.

8. **Equipped-host applicability for sign-off integrity**:
   `decisions/2026-06-08-equip-and-exercise-default-verification-posture.md`
   §1 SHOULD tier reads "For every cycle that merges `src/` or
   `tests/` changes, the Manual Test verification step SHOULD run
   on an equipped host". This slice merged NO `src/` or `tests/`
   changes (Scenario F validates this), so strictly read, the
   SHOULD tier does not apply. The frontmatter still defaults to
   "equipped" by symmetric continuity — the sign-off this
   verification protects covers `src/` and `tests/` evidence
   (Anchors A + B + C). Flag if you prefer to run this
   integrity pass on a general host with rationale; either is
   defensible under §1.

## Anything that wasn't obvious during merge

1. **Pre-merge gate was NOT run**. Charter says "After conflict
   resolution, RE-RUN the full test gate" — conditioned on conflict
   resolution. This merge had no conflicts (FF; main hadn't moved
   from the worktree base). The merge diff is comms-only (Scenario
   F validates), so no source/test surface could have changed
   under the merge. The `ci.yml` run `27192323843` on `8ae90cd`
   (the FF-merge target's parent) is the binding test-gate
   evidence; it remains valid for the merged tip `fee8c3d` because
   the source tree is structurally identical between `8ae90cd` and
   `fee8c3d`.

2. **§2.5 equip-and-exercise gate**: NOT applicable to Main
   Branch's merge step (per task brief + handoff §"§2.5 equip-
   and-exercise gate"). No `src/novetest/run/adapters/*` or
   `tests/integration/run/*` files touched.

3. **No worktree cleanup before push**: The worktree at
   `/home/yjshin/dev/novetest-mvp-release-ready-positive-sign-off`
   + branch `worktree-mvp-release-ready-positive-sign-off` will
   be removed AFTER successful push, per charter conventions.
   At the moment you (Manual Test) read this verification doc,
   the worktree may or may not still exist; this does not affect
   your verification (all scenarios target the merged tip on
   `main`, not the worktree).

4. **Sign-off framing intent (mirrored from yesterday)**: Per
   yesterday's findings doc framing (preserved in handoff
   §"Implementation guidance → Sign-off statement 어휘 가이드"):
   "Manual Test's job here is to verify the integrity and accuracy
   of that POSITIVE sign-off." Your verdict is on **integrity**,
   not on product-state ("is the product release-ready?"). If
   the 8 scenarios all PASS, the sign-off has structural
   integrity — the product IS release-ready as of `8ae90cd`. If
   any scenario FAILS, the sign-off is structurally compromised
   and Release team should re-issue.

5. **What I did NOT do at merge time** (out of charter scope):
   - Did not run `release-test.yml` workflow dispatch — would
     touch `.github/workflows/` runs but I'm not authorized to
     dispatch workflows on `main`.
   - Did not download release artifacts — Scenario B Optional
     probe is yours to run if you want artifact-level depth.
   - Did not write a `--licenses` CLI surface — explicitly
     out-of-scope per task brief.

## Post-verification cycle close (PM scope, NOT yours)

If your verdict is PASS:

- PM writes the cycle-close history at
  `agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md`
  (or equivalent slug).
- PM moves the transient handoff + this verification doc out of
  the in-flight set per `agent-comms/README.md` lifecycle rules.
- PM regens INDEX.
- **MVP release-ready status is officially achieved** (the cycle's
  binding deliverable).
- Next-cycle candidates per handoff §"Future-cycle hooks":
  - "release tag `v0.1.0` publication + GitHub Releases artifact
    upload" cycle (separate CEO command).
  - v1 metadata-channel sunset (post-MVP cleanup).
  - THIRD_PARTY_NOTICES pip-dep expansion (`cyclopts`, `numpy`)
    + `novetest --licenses` CLI wire-in (post-MVP polish).
  - Windows install.ps1 + binary pipeline (OQ#16).
  - First-run latency bench post-`numpy`.

If your verdict is FAIL on any scenario:

- File `agent-comms/findings/manual-test-team-2026-06-09-mvp-release-ready-positive-sign-off.md`
  with which scenario(s) failed + the observed-vs-expected delta.
- PM triages: either re-issue the sign-off via Release team
  (if a citation is incorrect / a DoD bullet is over-claimed), or
  re-open the cycle (if a citation reveals an actual product-
  state regression that the sign-off failed to surface).

Either path is in PM's hands once the findings doc lands — Manual
Test only writes the integrity verdict.
