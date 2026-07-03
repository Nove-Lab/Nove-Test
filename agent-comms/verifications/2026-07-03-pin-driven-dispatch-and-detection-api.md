---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-07-03
slug: pin-driven-dispatch-and-detection-api
related:
  - agent-comms/handoffs/run-team-2026-07-03-pin-driven-dispatch-and-detection-api.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Verification request: Run — pin-driven dispatch + single-source detection API (anchored-pin D1/D3, §4.1 fix)

## Merged

- **Commit**: `0825f64` (single commit) — rebased and FF-merged as slice
  3/4 of the 2026-07-03 batch.
- **Source handoff**: `run-team-2026-07-03-pin-driven-dispatch-and-detection-api.md`.
- **Merge mechanics**: one WORKLOG.md keep-both conflict; no other
  conflicts.

## Gate (on the merged tree)

- `env -u PYTHONPATH uv run mypy` → Success, 114 source files.
- Slice gate **1404 passed / 3 deselected / 47 snapshots** (= +13 run
  tests); final batch tree 1418/3/47. **Zero snapshot regen** — the
  `execute(engine=None)` legacy envelope surface is byte-identical.
- Pre-merge review (code-reviewer): **MERGE-OK, zero blocking findings.**
  `engine=None` branch confirmed line-for-line the old body; new
  `_ENGINE_MARKER_TABLE` order confirmed identical to the old SELECTOR
  order (the readiness chain was the wrong list and is deleted); repo-wide
  grep found zero references to removed readiness symbols; dotnet glob
  evidence byte-compatible.

## What changed (behavior)

- **§4.1 latent bug killed**: readiness and dispatch previously held
  different priority lists (readiness: python,js,go,rust,java,dotnet vs
  selector: python,js,java,go,rust,dotnet). A `pom.xml`+`go.mod` workspace
  could be Go-readiness-verified while JUnit was dispatched. Now ONE table
  drives both.
- **New API for the pending Orchestration anchored-init slice** (all
  package-exported from `novetest.run`): `detect_engine_candidates`,
  `probe_engine`, and `execute(..., engine=(ecosystem, engine_name))`.
- No other observable change: single-ecosystem workspaces, envelopes, and
  all 47 snapshots byte-identical.

## Verification steps (all outputs below observed live on the merged tree)

`env -u PYTHONPATH uv run python`:

```python
import asyncio, tempfile
from pathlib import Path
from novetest.run import (
    detect_engine_candidates, probe_engine, list_supported_engine_pairs,
)
from novetest.run.readiness import assess_engine_readiness

# R1 — canonical detection order + evidence (multi-marker workspace)
poly = Path(tempfile.mkdtemp()); (poly/"pom.xml").write_text("<project/>")
(poly/"go.mod").write_text("module example\n")
detect_engine_candidates(poly)
# observed: (java/junit, evidence=('pom.xml',)), (go/go-test, evidence=('go.mod',))
# — java outranks go (canonical order; pre-slice readiness said go)

# R2 — §4.1 agreement: readiness context == selection winner
res = asyncio.run(assess_engine_readiness(poly))
# observed: state='engine-misconfigured', context engine='junit'
# (bare pom.xml, no JDK/Maven — deterministic on any host; the POINT is
#  the context names junit, agreeing with dispatch)

# R3 — probe_engine probes exactly the NAMED pair, no fallback
pyws = Path(tempfile.mkdtemp()); (pyws/"pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
asyncio.run(probe_engine(pyws, "python", "pytest"))  # observed: state='engine-missing'
asyncio.run(probe_engine(pyws, "zig", "zig-test"))
# observed: raises EngineNotSupportedError (programming-error backstop;
#  CLI must validate --engine BEFORE calling — D7 invalid-flag exit 2)

# R4 — the single source of truth
list_supported_engine_pairs()
# observed: (('python','pytest'), ('javascript-typescript','jest'),
#            ('java','junit'), ('go','go-test'), ('rust','cargo-test'),
#            ('dotnet','xunit'))
```

CLI regression check: `novetest init` + `novetest test` on any
single-engine fixture behaves exactly as before (auto-detect `engine=None`
path; covered by the untouched lifecycle e2e suite + snapshots).

Targeted suite: `env -u PYTHONPATH uv run pytest -q tests/unit/run/` →
334 passed.

## Critical edge cases worth probing

1. **D1 ambiguity recipe** (for the coming init slice): candidates →
   per-candidate `probe_engine` → count `state == "ready"`; a tooling-only
   `package.json` with no runnable jest is candidate-but-NOT-ready and
   must not trigger `engine-ambiguous` (pinned by
   `test_probe_engine_tooling_only_package_json_is_candidate_but_not_ready`).
2. **TOCTOU**: a marker that vanishes between detection and probe comes
   back `engine-misconfigured`, never a crash.
3. **Pinned dispatch still gates readiness**: `execute(engine=...)` probes
   before the subprocess — a stale pin returns the clean exit-4 envelope
   instead of crashing inside the native runner. "No re-detection" holds:
   no marker scan decides anything on the pinned path.
4. **`RunRecord.engine_version` is adapter-observed only** (pre-existing
   contract, run-team-flagged): a pinned run whose probe saw a version but
   whose adapter reports none lands `engine_version=None`. Pin consumers
   must not expect the probe's version on the record.
5. **jest trio**: the 3 deselected jest integration tests are the
   documented Node-12-host issue — verify on CI (Ubuntu) not on this host.

## Open items (Run team / PM)

- `execute(engine=None)` compat branch lives until the Orchestration
  anchored-init slice removes the last caller (TODO pinned in `engine.py`).
- Deviation flagged for PM: `design/workflows/run.md` edited though not in
  the brief's pinned list (charter-owned truth-restoration; 3 rows).
