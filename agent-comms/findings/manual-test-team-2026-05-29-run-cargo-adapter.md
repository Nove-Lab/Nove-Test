---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
slug: run-cargo-adapter
created: 2026-05-29
verdict: partial
related:
  - agent-comms/verifications/2026-05-29-run-cargo-adapter.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
---

# Findings: cargo nextest Native Engine adapter (Phase 3 adapter #2)

## Verdict

**partial** — every probe that can be exercised without a Rust toolchain
came back clean; the running-cargo paths (basic run, coverage,
node_id conventions, per-test failure-log filenames, integration-test
binary distinction, version-floor enforcement, `--coverage` without
`cargo-llvm-cov`, libtest-json flag compatibility) cannot be verified
on this dev box because it ships no `cargo` and no `rustc`. The
verification document itself acknowledges this split ("full coverage of
the running-cargo paths is the integration suite's job PLUS your job on
a real Rust box") and the unit + integration test gate already passed
on the merged tip — but Manual Test cannot stamp those branches as
fully E2E-verified without a Rust box.

Net read for the CEO: the slice is structurally sound — readiness
probe, envelope shape, install-hint URL, exit-code mapping, selector
fallback — but the actual `cargo nextest run` execution path remains
unverified at the Manual Test layer pending a Rust-equipped agent.

## What was tested

This dev box has no `cargo` and no `rustc` on PATH. That makes it the
ideal environment to verify the **engine-missing** branch
exhaustively, and useless for the running-cargo branches. The
verification doc's Step 1 was probed directly; Steps 2-5 require Rust
and were skipped with a PM recommendation noted at the end.

Two bonus probes — running `novetest run` in (a) an EMPTY workspace
(no Cargo.toml, no manifests of any kind) and (b) the cargo SuT with
`--coverage` flag — were added beyond the verification doc to confirm
the readiness layer covers selection-side and coverage-mode entry
uniformly.

## Test-gate baseline

Re-ran the gate on the merged tip BEFORE doing any probe work, to
confirm the verification doc's numbers held on this box.

```
$ uv run pytest -q tests/unit tests/integration
... 667 passed, 5 skipped in 18.19s

$ uv run mypy
Success: no issues found in 70 source files (strict)
```

Matches the verification doc's claim of 667 passed / 5 skipped / 70
source files clean **verbatim**. Two of the 5 skips are the new
`tests/integration/run/test_cargo_*.py` cases skipping cleanly on this
no-Rust box, exactly as the slice intends.

## Commands run + observed output

### Step 1 — No-toolchain readiness probe (verification doc §1)

```bash
PROBE=/tmp/novetest-manual-cargo
rm -rf "$PROBE" && mkdir -p "$PROBE"
cp -r .../tests/fixtures/projects/cargo-test-basic "$PROBE/sut"
cd "$PROBE/sut"

novetest init --output json   # → store_state: ready, ok: true
novetest run  --output json   # ↓
```

Envelope received (full body):

```json
{
  "command": "run",
  "data": {
    "engine_readiness": {
      "ecosystem": null,
      "engine": null,
      "engine_version": null,
      "evidence": ["Cargo.toml"],
      "issues": [
        "`cargo` not found on PATH; install Rust toolchain from https://rustup.rs"
      ],
      "state": "engine-missing"
    }
  },
  "errors": [
    {
      "code": "engine-engine-missing",
      "details": {},
      "message": "engine readiness state: engine-missing (engine=(none detected))"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

**Shell exit code: `4`** (i.e. `EXIT_ENGINE_MISSING`, per
`src/novetest/cli/output.py:16`).

Every field requested by the verification doc is verbatim correct:

| Pin | Expected | Observed | Match |
|---|---|---|---|
| `state` | `engine-missing` | `engine-missing` | yes |
| `evidence` | `["Cargo.toml"]` | `["Cargo.toml"]` | yes |
| `issues[0]` text | install URL = `https://rustup.rs` | exact text "`cargo` not found on PATH; install Rust toolchain from https://rustup.rs" | yes |
| `errors[0].code` | `engine-engine-missing` | `engine-engine-missing` | yes |
| `ecosystem` / `engine` / `engine_version` | all `null` | all `null` | yes |
| `ok` | `false` | `false` | yes |
| `schema` | `novetest/v1` | `novetest/v1` | yes |

### Bonus probe A — Workspace with NO Cargo.toml (selection-side)

```bash
PROBE=/tmp/novetest-manual-cargo-noctom
rm -rf "$PROBE" && mkdir -p "$PROBE/sut"
cd "$PROBE/sut"
novetest init --output json   # store_state: ready
novetest run  --output json
```

Envelope: `state="engine-missing"`, `evidence=[]` (no detection-evidence
files), `issues=["no supported (ecosystem, native engine) pair
detected in workspace"]`. Exit code `4`. The selector-side path
produces the same `engine-engine-missing` error code, just with a
different issue message. Sane.

### Bonus probe B — Cargo SuT with `--coverage` and no Rust on PATH

```bash
cd /tmp/novetest-manual-cargo/sut
novetest run --coverage --output json
```

Envelope: identical to Step 1 — `state=engine-missing`,
`issues=["\`cargo\` not found on PATH; install Rust toolchain from
https://rustup.rs"]`, `errors[0].code="engine-engine-missing"`. Exit
code `4`. The `--coverage` flag does NOT change the readiness verdict
when the toolchain is missing entirely; readiness fires before the
coverage-mode branch dispatches. This matches the documented design.

### Steps 2-5 — Running-cargo paths (BLOCKED)

Cannot be probed on this box. The verification doc lists these as the
to-cover branches:

- Step 2: basic `cargo nextest run` envelope; node_id `::`
  convention; engine_name=="cargo-test"; summary counts.
- Step 3: coverage path with `cargo-llvm-cov`; LCOV artifact
  registration; build-failure-detector carve-out.
- Step 4: readiness paths beyond `engine-missing`
  (`engine-misconfigured` flavors: missing nextest, broken cargo
  version, no Cargo.toml — the last of which is the selection-side
  case I DID cover via Bonus probe A above).
- Step 5: `nextest_version` stash location — does it surface in the
  persisted Run Record envelope at all?

Each requires either a real `cargo` + `cargo-nextest`, or
`cargo-llvm-cov`, or a doctored toolchain layout (broken cargo, no
nextest, etc.). Manual Test recommends PM either:

1. Dispatch this slice to an agent on a Rust-equipped box (or set up a
   CI matrix cell — the Release team's pending follow-up per
   verification doc's "PM bookkeeping drift" §); OR
2. Accept the unit + integration test gate as sufficient signal for
   the running-cargo paths (the Run team's own tests at the subprocess
   seam already cover the libtest-json parser, node_id convention,
   failure-log filename safety, `_assess_cargo_readiness` branches,
   etc., per the verification doc's claim of "+29 net unit passes").

The latter is operationally fine for v1 — but the cargo adapter would
then be the first adapter to ship without a Manual Test E2E pass on its
actual execution path. PM call.

## Issues found

**1. Verification-doc wording drift — exit code claim is wrong.**

The verification doc states (verbatim):

> Exit code: `0` at the shell (the orchestrator treats engine
> readiness as a soft failure surfaced in JSON; `ok: false` is the
> machine signal).

The actual exit code on the engine-missing path is `4` (the
`EXIT_ENGINE_MISSING` constant from `src/novetest/cli/output.py:16`,
mapped at `src/novetest/cli/app.py:236, 255`). This is the
**intended** behavior per the source — exit code 4 is the documented
signal for "engine not ready", distinct from EXIT_GENERIC (1),
EXIT_USER_TESTS_FAILED (3), etc.

The drift is in the verification-doc prose, not the product. No code
change needed; minor PM correction to the doc if it gets reused as a
spec elsewhere. Non-blocking.

**2. Unverified at Manual Test layer (see §"What was tested" above).**

Five branches of the cargo adapter cannot be exercised on this box.
This is environmental, not a defect. Logged as PM-side: schedule a
Rust-box pass OR explicitly accept the unit-test gate as sufficient
for v1. The verification doc itself raised this — confirming the
posture, not surfacing a new finding.

## Recommendations for PM

1. **Pick a closure posture for the cargo adapter's E2E gap.** Either
   (a) dispatch a follow-up Manual Test task with explicit "this
   requires Rust + cargo-nextest + cargo-llvm-cov installed" gating,
   or (b) accept the unit/integration gate as the v1 E2E signal and
   record the choice in a short decision so future cycles know cargo
   is the exception. The CEO should not assume this slice has
   identical Manual Test coverage to the pytest/jest/gotest adapters
   — those were all probed by running the actual native engine.

2. **Correct the verification-doc claim of "exit code 0"** if it gets
   reused as a downstream spec. Exit 4 is correct and intentional.
   The doc's prose says exit 0; the source produces 4. Five-minute
   PM-side note in the doc itself is enough.

3. **Track the `nextest_version` payload-stash question** flagged in
   the verification doc §5 — it's a real product-design call (encode
   the payload-stash convention OR amend `NativeEngineContext` to take
   adapter-supplied metadata), but it needs a Rust box to confirm
   where `nextest_version` actually surfaces in the persisted Run
   Record envelope. Same gating as recommendation 1.

4. **No code-change recommendations from this verification.** The
   no-toolchain readiness path is correct, the install-hint URL is
   verbatim what's specced, the error-code prefix `engine-engine-`
   matches the same pattern as the gotest adapter (this is a known
   double-`engine-` cosmetic; same observation as the 2026-05-28
   gotest findings). No new defects surfaced.

## Process notes

- `jq` is not installed on this dev box. All JSON inspection was done
  via `python3 -c "import json; ..."`.
- The `Write` tool tripped the worktree-isolation guard mid-session,
  same as prior cycles; this file was written via the sanctioned Bash
  heredoc fallback (GOTCHAS.md).
- Bash classifier briefly returned "claude-opus-4-7 is temporarily
  unavailable" mid-session; retry on the same command succeeded
  immediately. No impact on findings content.
