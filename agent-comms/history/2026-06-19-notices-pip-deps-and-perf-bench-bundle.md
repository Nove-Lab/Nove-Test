---
from: novetest-pm-team
to: all
type: history
created: 2026-06-19
slug: notices-pip-deps-and-perf-bench-bundle
cycle_window: 2026-06-19 (Wave 1 of 3 parallel cycles, FF-merge order Coverage → Release → Run)
related:
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-06-10-license-apache-2.0-with-cla.md
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md  # Future-cycle queue #2a / #5 / #8 source
  - agent-comms/history/2026-06-10-v0.1.0-license-and-tag-publication.md
  - design/implementation-plan/foundations.md
---

# NOTICES pip-dep expansion + first-run latency bench + wheel-NOTICES probe

## TL;DR

Three Release-team polish items bundled into one cycle: (1) inline
verbatim Apache 2.0 and BSD 3-Clause license texts in `NOTICES.md` so the
wheel's attribution surface is byte-identical to upstream canonical texts;
(2) add a `first-run-latency-bench` job to `release-test.yml` that times
the PyApp binary's first `--version` invocation against the foundations.md
§559 documented "5-15 s" budget on every release-test run; (3) add a
wheel-NOTICES inclusion probe step that fails the build if `NOTICES.md`
ever stops shipping in the wheel.

**Closes Future-cycle queue items #2a + #5 + #8.**

Manual Test verdict: **PASSED** — 8 scenarios + 7 critical edges, two
documentation observations (license-text sub-section depth + wheel-size
14× growth) both intentional / not regressions.

The release-test.yml dispatch + bench-data harvest was deferred to PM
cycle-close per the verification doc's own §"Scenario I (POST-PM-DISPATCH)"
sequencing. **PM-dispatched run `27832686990`** is the binding empirical
evidence; bench numbers captured in §"First-run latency bench: empirical
result" below.

## Cycle arc (Wave 1, parallel with Coverage workspace-relpath and Run v1-metadata-sunset)

| Event | Commit |
|---|---|
| PM dispatch prep | `42f6a32` |
| Release code (NOTICES + workflow + foundations placeholder) | `24477ee` |
| Release handoff (ready-for-merge) | `f4523da` |
| Main Branch FF-merge + verification routing | `af3d4fb` |
| Manual Test PASSED findings filed | _(at cycle close)_ |
| PM dispatch of release-test.yml on main | run `27832686990` |
| PM cycle-close (this entry + foundations.md §559 finalization + transient cleanup) | _(this commit)_ |

## What landed

### Source changes (3 files)

| File | Change | LOC |
|---|---|---|
| `NOTICES.md` | 54 → 307 lines; verbatim Apache 2.0 + BSD 3-Clause texts inlined under `## License texts` parent section with `### Apache 2.0` / `### BSD 3-Clause` subsections; per-package cross-reference anchors (`License: Apache-2.0 — verbatim text: [Apache 2.0](#apache-20)`) | +253 |
| `.github/workflows/release-test.yml` | New `build` step "Probe wheel NOTICES inclusion" (`python -m zipfile -l` + grep `NOTICES\.(md\|txt)` + `::error::` on miss); new top-level job `first-run-latency-bench` (needs: build, ubuntu-latest) with cache-purge → cold timing → warm timing → `::notice title=first-run-latency::cold=...s warm=...s delta=...s threshold=25.0s` annotation → 25 s assertion gate; `release.needs` extended to `[build, install-script-e2e, install-ps1-e2e, first-run-latency-bench]` | +109 / −1 |
| `design/implementation-plan/foundations.md` §559 | Placeholder appended for PM to fill in `<X>` (cold seconds) + `<run_id>` post-dispatch | +1 / −1 |

### Wheel artifact verification (local)

Manual Test ran `uv build --wheel` locally and confirmed the wheel ships:

| File | Path in wheel | Size |
|---|---|---|
| `NOTICES.md` | `novetest-0.1.1.dist-info/licenses/NOTICES.md` | **15,581 bytes** (post-expansion; was 2,056 bytes pre-expansion) |
| `LICENSE` | `novetest-0.1.1.dist-info/licenses/LICENSE` | 11,339 bytes |
| `THIRD_PARTY_NOTICES.txt` (vendored JUnit) | `novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt` | 913 bytes |

Wheel size: 2,796,998 bytes (2.8 MB). Hatchling's PEP 639 auto-discovery
handles NOTICES.md inclusion without explicit `[tool.hatch.build.targets.wheel.force-include]`.

### First-run latency bench: empirical result

Dispatch: `gh workflow run release-test.yml --ref main` at 2026-06-19T14:50:34Z.
Run `27832686990` SUCCESS in ~6 min (8 jobs: 4 build cells + install-script-e2e
+ install-ps1-e2e + first-run-latency-bench + draft-release-skip-by-design).

| Metric | Value | Budget |
|---|---|---|
| **cold** first `novetest --version` wall | **10.456 s** | foundations.md §559 documents 5-15 s; bench asserts ≤ 25 s |
| **warm** second `novetest --version` wall | **0.285 s** | n/a (warm-cache reference) |
| **delta** (cold − warm) | **10.171 s** | this is the PyApp CPython download + extract cost |

Within the 5-15 s documented budget. The bench is now gated on every
release-test run (release.needs extension).  updated
in cycle-close commit with the binding citation.

## Load-bearing learnings (4)

### 1. PEP 639 wheel-license auto-discovery is the canonical mechanism

The wheel-NOTICES probe step's `python -m zipfile -l | grep NOTICES\.(md|txt)`
pattern is path-agnostic by design — it matches the filename regardless of
the `*.dist-info/licenses/` directory prefix. This means future Hatchling
canonical-path changes (e.g., a hypothetical PEP-639 update) still pass
the probe. **Failure mode**: if Hatchling ever stops auto-including
NOTICES.md altogether (configuration regression or upstream policy change),
the fallback is to add `NOTICES.md` to `pyproject.toml::[tool.hatch.build.targets.wheel.force-include]`.

The probe is the safety net for both regression modes.

### 2. Apache 2.0 leading-blank off-by-one (DoD wording nuance)

The canonical Apache LICENSE-2.0.txt file is 202 lines, of which line 1
is blank. The DoD's natural diff command `diff <(curl ...) <(awk '/Apache License/,/.../' NOTICES.md)` returns 1 line (`1d0\n<\n`) regardless of how
the verbatim text is embedded in NOTICES.md — the awk pattern matches
starting from the first occurrence of "Apache License", which on the
canonical file is line 2 (after the leading blank). Substantive byte-identity
is provable via `diff <(tail -n +2 /tmp/apache-2.0.txt) <(awk ...)`,
which returns empty.

**Future brief authors**: when DoD includes "byte-identical to upstream
canonical text", call out the `tail -n +2`-stripped LHS form explicitly,
OR phrase the requirement as "substantive body byte-identical (leading
blank line of canonical file is documented OK)".

### 3. The §4 amendment CI matrix criterion's SHOULD-tier vs MUST-tier split

This slice modifies `.github/workflows/release-test.yml` which IS path/OS-sensitive
per the §4.1 #2 enumeration. The MUST tier fires. ci.yml run `27831589304`
provided the cross-OS sanity-check anchor (10/10 GREEN). The new release-test.yml
job is itself ubuntu-latest-only by design (PyApp's CPython download path
is identical cross-OS modulo URL templating) — its empirical evidence is
the dispatched run `27832686990`.

**Pattern**: when a slice introduces a NEW single-OS CI job alongside
existing cross-OS jobs, the verification doc cites BOTH (the ci.yml run for
cross-OS sanity + the release-test.yml run for the new job's empirical
evidence). The handoff's deferral of release-test.yml dispatch to PM is
the 2026-06-18 CEO push-gate precedent — Manual Test does not autonomously
dispatch workflows.

### 4. Wheel-size growth is the load-bearing tradeoff for Apache 2.0 §4(d)

NOTICES.md grew from 2,056 bytes to 15,581 bytes (~7.6×) in the wheel.
The total wheel grew from previous ~2.78 MB to 2.80 MB (~0.6%, within
noise). The growth IS the intended tradeoff for clean Apache 2.0 §4(d)
compliance — every wheel includes the full verbatim license texts for
redistribution scenarios.

**Trade-off pinned**: future similar attribution-expansion cycles should
expect ~10-20 KB NOTICES.md growth per inlined license; the marginal wheel
size impact is < 1% and operationally negligible.

## Phase 0 DoD bullets re-validated (no new ticks)

This cycle adds zero new Phase 0 DoD ticks (Future-cycle queue items, not
Phase 0 binding). Empirically re-validated:

- `ci.yml` 10/10 GREEN on `27831589304` at SHA `167a261`
- `release-test.yml` run `27832686990` on main HEAD `3eb78cf` — empirical
  bench result captured per §"First-run latency bench"
- Wheel-NOTICES probe operationally green (local `uv build --wheel` +
  CI build cells)

## Future-cycle queue impact

- **#2a NOTICES pip-dep expansion** ← CLOSED by this cycle (verbatim
  Apache 2.0 + BSD 3-Clause texts inlined; PEP 639 auto-discovery confirmed)
- **#5 first-run latency bench post-numpy** ← CLOSED by this cycle (bench
  job operational; budget assertion gating release.needs)
- **#8 Wheel-NOTICES probe codification** ← CLOSED by this cycle (probe
  step in build job; loud `::error::` on miss)
- **#2b `novetest --licenses` CLI verb** ← Wave 2 follow-up; brief filed
  separately when CEO opens the cycle. NOTICES.md is now the canonical
  source the verb will read from.

## Cycle transcript (commits)

- `42f6a32` — PM: Wave 1 parallel dispatch
- `9c5abbf` — Coverage: workspace_relpath utility promotion (parallel)
- `24477ee` — Release: NOTICES + bench + probe bundle code
- `f4523da` — Release: handoff (ready-for-merge)
- `d5b4242` — Run: v1 metadata-channel sunset (parallel)
- `af3d4fb` — Main Branch: verification routing to Manual Test
- _(this commit)_ — PM: cycle-close (3-history bundle + foundations.md §559 finalization + transient cleanup + INDEX regen)

## Closure

The wheel's license-attribution surface is now byte-identical to upstream
canonical texts. The first-run latency budget is empirically gated on every
release. The wheel-NOTICES inclusion is structurally probed. Future-cycle
queue items #2a + #5 + #8 are operationally closed.

**Companion entries**: `2026-06-19-workspace-relpath-utility-promotion.md`
(closes #6) and `2026-06-19-v1-metadata-channel-sunset.md` (closes #3)
close the Wave 1 cohort.

The next natural cycle is **Wave 2 #2b `novetest --licenses` CLI verb** —
Orchestration team territory; reads from the NOTICES.md surface this cycle
landed.
