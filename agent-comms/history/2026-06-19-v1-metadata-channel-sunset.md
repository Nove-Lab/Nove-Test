---
from: novetest-pm-team
to: all
type: history
created: 2026-06-19
slug: v1-metadata-channel-sunset
cycle_window: 2026-06-19 (Wave 1 of 3 parallel cycles, last in FF-merge order Coverage → Release → Run)
related:
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md  # Amendment 2026-06-19 v1 sunset
  - agent-comms/history/2026-06-07-parallel-pair-envelope-warnings-and-dotnet-cobertura-derive.md  # Option C v2 surface that this cycle sunsets v1 of
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md  # Future-cycle queue #3 source
---

# v1 `coverage_unavailable_kind/_message` metadata channel sunset (dotnet adapter)

## TL;DR

Removed the v1 bridge metadata keys (`coverage_unavailable_kind` +
`coverage_unavailable_message`) from the dotnet adapter, now that the
Option C envelope `warnings[]` projection has been the operational
user-visible surface for 12 days (since 2026-06-07). Bookkeeping
cleanup; canonical surface unchanged.

**Closes Future-cycle queue item #3.**

The 2026-06-06 decision §"Acceptance criteria for Option C slice" #2
declared a one-release-cycle backward-compat window for the v1 keys.
That window closed cleanly today. Decision-file Amendment 2026-06-19
records the sunset in the source decision document; audit-trail
literal references in the §"Reserved metadata keys for v1" historical
table are preserved unchanged.

Manual Test verdict: **PASSED** — 8 scenarios + 8 critical edges, zero
blocking defects.

## Cycle arc (Wave 1, parallel with Coverage workspace-relpath and Release NOTICES+bench bundle)

| Event | Commit |
|---|---|
| PM dispatch prep | `42f6a32` |
| Run code+tests+WORKLOG+handoff (last in FF-merge order) | `d5b4242` |
| Main Branch FF-merge + verification routing | `167a261` |
| Manual Test PASSED findings filed | _(at cycle close)_ |
| PM cycle-close (this entry + transient cleanup) | _(this commit)_ |

## What landed

### Source changes (1 src + 3 tests + 1 decision)

| File | Change | LOC |
|---|---|---|
| `src/novetest/run/adapters/dotnet_adapter.py` | Remove 2 local-var decls + 2 assignments + 4-line metadata write; generalize 4 docstring/comment references to drop literal key names | −98 / +5 |
| `tests/unit/run/adapters/test_dotnet_adapter.py` | Migrate 5 assertion sites; rename `TestEnvelopeSafetyNet` class members from `test_metadata_carries_*` to `test_warnings_carry_*` | ~+45 / ~−30 |
| `tests/integration/run/test_dotnet_coverage.py` | Migrate 1 happy-path negative assertion (filter on `result.warnings` instead of `metadata`) | +7 / −7 |
| `tests/integration/run/test_dotnet_warnings.py` | Migrate 1 CLI-smoke positive assertion to **negative-proof** "bridge keys MUST be absent" — binds the sunset | +10 / −13 |
| `agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md` | Append "Amendment 2026-06-19" section with pre/post surface table, scope, backward-compat posture, empirical sunset evidence | +74 |

Zero changes to other adapters, the orchestration projection
(`workflows/run.py`), the `AdapterWarning` dataclass, or `NativeResult.warnings`
shape. The canonical Option C surface is byte-identically unchanged.

### Pre/post surface table (from decision file Amendment 2026-06-19)

| Surface | Pre-sunset | Post-sunset |
|---|---|---|
| `RunRecord.metadata.coverage_unavailable_kind` | populated when Coverlet absent | **absent** |
| `RunRecord.metadata.coverage_unavailable_message` | populated when Coverlet absent | **absent** |
| `NativeResult.warnings` (`AdapterWarning` tuple) | populated | populated (unchanged) |
| `envelope.warnings[]` (`EnvelopeWarning` projection) | populated | populated (unchanged) |
| `envelope.warnings[0].code` | `engine-misconfigured` | `engine-misconfigured` (unchanged) |
| `envelope.warnings[0].details` | `{coverlet_floor, csproj}` | `{coverlet_floor, csproj}` (unchanged) |

### Empirical CLI smoke (verbatim envelope)

Manual Test captured against `tests/fixtures/projects/dotnet-test-basic`
copied to `/tmp/nv-verify-run` (Coverlet absent — canonical "coverage
requested but unavailable" scenario):

```json
{
  "command": "run",
  "ok": false,
  "warnings": [
    {
      "code": "engine-misconfigured",
      "message": "coverage was requested but `coverlet.collector` is not in the project's package graph; add <PackageReference Include=\"coverlet.collector\" Version=\"6.0.2\" /> (or later 6.0.x) to the .csproj. Coverage data was not collected for this run.",
      "details": {"coverlet_floor": "6.0.2", "csproj": "MathLib.Tests.csproj"}
    }
  ],
  "data": {
    "memory_entry": {
      "run_record": {
        "metadata": {
          "dotnet_sdk_version": "8.0.421",
          "native_exit_code": "...",
          "xunit_version": "2.6.0"
        }
      }
    },
    "coverage_outcome": {"kind": "unavailable", "...": "..."}
  }
}
```

**bridge keys present in `metadata`? FALSE** — the binding negative
proof of the sunset.

## Load-bearing learnings (3)

### 1. The "one-release-cycle backward-compat window" pattern works cleanly

The 2026-06-06 decision pre-committed to a one-release-cycle deprecation
window. The window expired 12 days later (2026-06-07 + ~12 days = 2026-06-19).
The sunset was executed as a discrete bookkeeping cycle, not a feature
change. Surface deletion was clean because:

- The canonical surface (`envelope.warnings[]` via `AdapterWarning`
  projection) was already operational and exercised in production for
  12 days
- The bridge keys were **additive** to the canonical surface — every
  adapter site that wrote the bridge ALSO emitted the canonical `AdapterWarning`
- Tests migrated from "positive bridge-present" to "negative bridge-absent"
  + "positive envelope-warnings-present" — a clean assertion shape that
  binds the sunset and prevents regression

**Pattern recommendation**: future backward-compat windows for
additive-bridge surfaces should follow the same shape — write the new
canonical surface AND the bridge in the v1 cycle; sunset the bridge in
v2 after one release window; preserve the audit-trail literal references
in the source decision file (`agent-comms/decisions/`) but sanitize
source/test references.

### 2. Strict-DoD docstring/comment generalization is a pre-emptive cleanup step

Brief author should include "generalize docstring/comment literal
references to drop the to-be-removed key names" as an explicit migration
sub-step, not as a post-edit cleanup pass. Run team needed to generalize
4 docstring/comment sites in `dotnet_adapter.py` + 2 test-site comments to
satisfy DoD #1's strict grep (zero matches in src/ + tests/). Naming them
in the brief surface inverse upfront avoids late re-edits.

**Pattern for future similar briefs**: when a slice's DoD includes a
strict grep for absence-of-token, list the docstring/comment sites that
need to drop the token alongside the actual code-write sites.

### 3. Manual Test toolchain-sourcing discipline for adapter cycles

Manual Test's first run of the dotnet integration tests returned `4 skipped`
(SDK not on PATH). Re-run with `source ~/.local/share/novetest-toolchains.sh`
returned `4 passed in 18.72s`. This is per §2.5 binding gate and the
2026-06-04 equip-and-exercise decision — the equipped host is the load-bearing
verification surface for adapter cycles, but Manual Test must explicitly
source the toolchain shim BEFORE running adapter integration tests, or
expect skips that look like passes-but-aren't.

**Procedural note for future Manual Test sessions**: standard runbook for
adapter-touching cycles is: `source ~/.local/share/novetest-toolchains.sh`
→ verify `dotnet --version` / `java --version` echoes the equipped version
→ run integration tests. Skipping the first step risks "ghost passes."

## Phase 0 DoD bullets re-validated (no new ticks)

This cycle adds zero new Phase 0 DoD ticks (Future-cycle queue item, not
Phase 0 binding). Empirically re-validated on equipped host:

- mypy `--strict` GREEN (109 source files — unchanged)
- pytest 1300 passed / 5 skipped / 0 failed on equipped host (chronic dotnet
  failure does NOT manifest on equipped host — that's §2.5 binding evidence)
- `ci.yml` 10/10 GREEN on `27831589304` at SHA `167a261` (cross-OS witness)

## Future-cycle queue impact

- **#3 v1 metadata-channel sunset** ← CLOSED by this cycle (canonical
  sunset path queued in 2026-06-09 MVP sign-off history)

## Cycle transcript (commits)

- `42f6a32` — PM: Wave 1 parallel dispatch
- `9c5abbf` — Coverage: workspace_relpath utility promotion (parallel)
- `24477ee` — Release: NOTICES + bench + probe bundle code (parallel)
- `f4523da` — Release: handoff (parallel comms)
- `d5b4242` — Run: dotnet adapter v1 metadata-channel sunset
- `167a261` — Main Branch: verification routing to Manual Test
- _(this commit)_ — PM: cycle-close (3-history bundle + transient cleanup + INDEX regen)

## Backward-compat communication for external consumers

The next public Nove Test release CHANGELOG SHOULD explicitly note:

> **BREAKING (.NET adapter)**: `RunRecord.metadata.coverage_unavailable_kind`
> + `coverage_unavailable_message` removed. Consumers MUST migrate to
> `envelope.warnings[].{code,message,details}` (operational since
> 2026-06-07).

Decision-file Amendment 2026-06-19 already documents this for internal
audit; CHANGELOG amplifies for the public audience. Lowest priority follow-up,
to be folded into the v0.1.2 publication cycle's release notes.

## Closure

The v1 metadata-bridge is gone. The canonical `envelope.warnings[]` surface
is the single source of truth for adapter-emitted warnings. The audit trail
in the source decision file is preserved. The one-release-cycle backward-compat
contract has been honored to its expiration date. Future-cycle queue #3 is
operationally closed.

**Companion entries**: `2026-06-19-workspace-relpath-utility-promotion.md`
(closes #6) and `2026-06-19-notices-pip-deps-and-perf-bench-bundle.md`
(closes #2a/#5/#8) close the Wave 1 cohort.
