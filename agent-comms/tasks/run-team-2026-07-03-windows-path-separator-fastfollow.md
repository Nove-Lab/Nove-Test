---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-07-03
slug: windows-path-separator-fastfollow
related:
  - agent-comms/findings/manual-test-team-2026-07-03-pin-driven-dispatch-and-detection-api.md
  - agent-comms/tasks/run-team-2026-07-03-pin-driven-dispatch-and-detection-api.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Task: Run — FAST-FOLLOW: dotnet glob evidence must emit POSIX paths (Windows CI red)

- **Owner**: novetest-run-team
- **Severity**: **merge-gate** — 3 of 10 CI jobs (all `windows-latest`) red at
  batch HEAD `b982fad`. Blocks the pin-driven-dispatch cycle close AND the
  Wave 2 (Orchestration anchored-pin) dispatch.
- **Sequencing**: immediately. Nothing else rides on this slice.

## The regression (from Manual Test findings, reproduced on CI `28633288553`)

Your `pin-driven-dispatch-and-detection-api` slice (`0825f64`) added glob-based
marker evidence in `src/novetest/run/engine_selector.py:102`:

```python
for match in root.glob(marker):
    glob_hits.add(str(match.relative_to(root)))   # os-native separators
```

`str(PurePath)` yields `\` on Windows, but the slice's OWN test —
`tests/unit/run/test_engine_selector.py::test_detect_dotnet_one_level_csproj_evidence_is_root_relative`
— pins root-relative **POSIX** form (`MyLib.Tests/MyLib.Tests.csproj`). The
test's contract is correct: evidence strings flow into readiness/init
envelopes consumed by AI agents and must be platform-stable. The
implementation violates it on Windows only:

```
At index 0 diff: 'MyLib.Tests\\MyLib.Tests.csproj' != 'MyLib.Tests/MyLib.Tests.csproj'
```

## In scope (surgical — one line)

```python
glob_hits.add(match.relative_to(root).as_posix())
```

No test changes: the failing test already pins the correct contract.

## Out of scope

The 4 pre-existing `str(x.relative_to(y))` sites
(`cargo_adapter.py:367`, `junit_adapter.py:898`, `dotnet_adapter.py:571`,
`dotnet_adapter.py:1233`) are artifact-log keys / metadata, NOT envelope
evidence, and are green on Windows CI today. Do NOT touch them in this
fast-follow (Manual Test concurs; optional hygiene audit is a separate
conversation).

## Acceptance criteria

- `tests/unit/run/test_engine_selector.py` green locally; mypy clean.
- Full CI matrix **10/10** at the merge commit (the three `windows-latest`
  jobs are the whole point — confirm them explicitly in the handoff).
- `WORKLOG.md` entry; handoff at
  `agent-comms/handoffs/run-team-2026-07-03-windows-path-separator-fastfollow.md`
  citing the green CI run id.

## Effort estimate

One line of production code, zero test changes. Minutes, not hours.
