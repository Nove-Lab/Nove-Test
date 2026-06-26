# Troubleshooting

This page is organized by failure mode. Find the shape that matches your
problem, read the cause, apply the fix. Most failures pair a process
**exit code** with a machine-friendly `errors[0].code`; route on the
exit code first, then on the code. The full catalog is in
[Understanding Results -> `errors[].code` catalog](./understanding-results.md#errorscode-catalog-failure-paths).

Examples use the canonical `calc` project (a small Python package) and
Nove Test **0.1.2**.

::: tabs
@tab For human

In TEXT mode (the default on a terminal), a failed command renders a
generic error block, regardless of which verb produced it:

```
✗ <command>
  <code>: <human-readable message>
```

The first line names the failing command; the second gives the error
`code` (useful for searching docs / issues) and a one-sentence
description. For full detail, re-run with `novetest --output json`.

@tab For agent

Every envelope has exactly these top-level keys (JSON-sorted):
`command, data, errors, ok, schema, warnings`. `schema` is always
`"novetest/v1"`; `errors`/`warnings` are arrays of
`{code, message, details}`. There is **no** top-level `version`,
`verb`, or `exit_code` field. Route on the process exit code, then on
`errors[0].code`:

```python
err  = envelope["errors"][0] if envelope["errors"] else None
code = err and err["code"]
# install hints for engine errors live in data.engine_readiness.issues[],
# NOT in err["details"].
```

:::

## Exit codes at a glance

| Exit | Meaning |
|---|---|
| 0 | Success (`ok: true`). |
| 1 | Generic / unexpected failure (e.g. `cli-error`). |
| 2 | Usage / validation: uninitialized store, bad argument, unknown `run_id`, bad flag, `reset` without `--confirm`. |
| 3 | **Your tests failed.** The tool worked (`ok: true`); failing tests are data, not an error. |
| 4 | The engine could not run: no/insufficient engine, or an adapter invocation error. |
| 5 | Project Store storage error (corrupt store, wipe failed). |

::: tabs
@tab For human

**Exit 3 is not a tooling error.** A failing test run still reports
`ok: true`. Treat it like a failing `pytest` invocation — read the
recommendation block, fix the code or the test, re-run.

@tab For agent

#### Quick reference — exit code × `errors[0].code`

| Exit | `errors[0].code` | Recovery |
|---|---|---|
| 0 | (none) | Success. |
| 1 | `cli-error` | Uncaught internal error (`command: "cli"`). Capture, file issue. Do not retry blindly. |
| 2 | `uninitialized` | `novetest init`, then retry. |
| 2 | `not-found` | Unknown `run_id`. `novetest memory list`, pick a real ULID. |
| 2 | `invalid-flag` | Value outside the closed set. Read `errors[0].message`. |
| 2 | `confirm-required` | `reset` needs `--confirm` (destructive). |
| 3 | (none) | `ok: true` — user's tests failed. Read `data.recommendations`. |
| 4 | `engine-engine-missing` | No usable engine. Read `data.engine_readiness.issues[]`. |
| 4 | `engine-engine-misconfigured` | Engine applies, tooling missing. Read `data.engine_readiness.issues[]`. |
| 4 | `adapter-<kind>` | Engine ran but failed. Read `errors[0].message` (stderr tail). |
| 5 | `store-corrupt` / `store-wipe-failed` | Storage failure. Surface to operator. |

Two spellings that bite parsers: an unready engine surfaces as the
doubled `engine-engine-missing` code (prefix `engine-` + state
`engine-missing`); adapter codes key on the failure **kind**
(`adapter-unparseable-output`), not the engine name. There is no
`engine-not-ready` code and no `not-implemented` runtime code.

:::

---

## Install issues

### `command not found: novetest`

The install script drops the binary at `~/.local/bin/novetest` (POSIX)
or `%USERPROFILE%\.local\bin\novetest.exe` (Windows), which may not be
on PATH.

**Fix.** Add it:

```bash
# Linux / macOS — add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"
```

```powershell
# Windows — add to PowerShell profile
$env:PATH = "$HOME\.local\bin;$env:PATH"
```

Re-check with `novetest --version` (`novetest 0.1.2 (Python …)`).

### Install script aborts with `SHA-256 mismatch`

The install script downloads the binary plus its `.sha256` sidecar,
verifies the hash, and **aborts loudly, writing nothing, on a
mismatch** — a real integrity guard. The download was corrupted or the
release artifacts are inconsistent.

**Fix.**

1. Re-run the install script (usually a flaky network).
2. Pin a version: `NOVETEST_INSTALL_VERSION=v0.1.2 curl … | sh`.
3. Still failing? File an issue with your OS / arch / network situation.

### First run is slow (5–15 seconds)

Expected. The binary is PyApp-wrapped — it unpacks its bundled CPython
once, on the first invocation per binary version. Later runs are warm.

### Windows: PowerShell script blocked

Your execution policy is blocking `install.ps1`.

**Fix.**

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
# or
Unblock-File install.ps1; .\install.ps1
```

### Supported platforms

Linux x86_64, Linux aarch64, macOS universal2 (one fat binary for Intel
+ Apple Silicon), Windows x86_64. **No Windows arm64** build.

---

## `init` issues

### `store-corrupt` (exit 5)

::: tabs
@tab For human

`.novetest/store.json` exists but is unreadable or malformed:

```
✗ init
  store-corrupt: Project Store at /home/you/calc-demo/.novetest is unreadable: <reason>.
```

**Fix.** Salvage the file if you can; otherwise:

```bash
rm -rf .novetest
novetest init
```

That wipes stored runs for this project. Source and tests are untouched.

@tab For agent

```json
{
  "errors": [
    { "code": "store-corrupt", "details": {}, "message": "Project Store at <path> is unreadable: <reason>." }
  ]
}
```

Do NOT auto-recover — destructive recovery destroys history. Surface to
the operator.

:::

### `init` succeeded but `engine readiness: engine-missing`

`init` always succeeds and leads with `✓` — it never fails on a missing
engine. The readiness line reports it couldn't find a usable engine.

::: tabs
@tab For human

```
✓ Initialized .novetest/ at /path/to/calc-demo/.novetest
  engine readiness: engine-missing — no engine detected
  issue: Python workspace detected but no pytest configuration (pytest.ini, [tool.pytest.ini_options], conftest.py, or tests/ dir) found
```

(This `issue:` is for a Python project with a `pyproject.toml` but no
pytest config — matching the agent-tab envelope below; a directory with no
recognized markers at all instead reports `no supported (ecosystem, native
engine) pair detected in workspace`. A healthy project shows `engine
readiness: ready — python/pytest 9.0.3`.)

The `issue:` line carries the real, engine-specific reason and install
command. Common cases:

| Engine | Fix |
|---|---|
| pytest | Add a `tests/` dir / `[tool.pytest.ini_options]` / `pytest.ini` / `conftest.py`; install pytest + `pytest-json-report`. |
| jest | Install Node.js ≥ 18, then `npm install --save-dev jest` in the project root. |
| go-test | Install Go ≥ 1.21 (<https://go.dev/dl/>). |
| cargo-test | `cargo install cargo-nextest --locked` (nextest is **required** — no plain `cargo test` fallback). |
| junit | Install JDK 17+ and Maven 3.9+ or Gradle 7.6+. JUnit 5 Jupiter only. |
| xunit | Install .NET SDK 8.0+ and add `xunit` (v2). MSTest / NUnit are rejected. |

Re-run `novetest init` after fixing.

@tab For agent

```json
{
  "command": "init",
  "data": {
    "engine_readiness": {
      "ecosystem": null, "engine": null, "engine_version": null,
      "evidence": ["pyproject.toml"],
      "issues": ["Python workspace detected but no pytest configuration (pytest.ini, [tool.pytest.ini_options], conftest.py, or tests/ dir) found"],
      "state": "engine-missing"
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

`init` is always `ok: true`, exit 0 — route off
`data.engine_readiness.state`, one of exactly `ready`,
`engine-missing`, `engine-misconfigured` (there is **no**
`engine-not-ready` state). The actionable, engine-specific install
commands are the strings in `data.engine_readiness.issues[]`.

:::

---

## `test` / `run` issues

### `engine-engine-missing` (exit 4)

::: tabs
@tab For human

```
✗ run
  engine-engine-missing: engine readiness state: engine-missing (engine=(none detected))
```

No usable engine. The code really is the doubled `engine-engine-missing`
(error prefix `engine-` + state `engine-missing`). `novetest test`
behaves the same.

**Fix.** Run `novetest init` (or re-run the verb — `test`/`run` re-probe
each time) and read the readiness `issue:` lines, then install the
engine. If the engine *is* installed but unseen:

1. **Wrong interpreter (pytest).** Nove Test runs pytest with its own
   bundled interpreter (`<python> -m pytest …`), not a `pytest` on PATH.
   A pytest it can't import reads as `engine-misconfigured`.
2. **Wrong project.** Confirm you're in the right directory.

@tab For agent

```json
{
  "command": "run",
  "data": {
    "engine_readiness": {
      "ecosystem": null, "engine": null, "engine_version": null,
      "evidence": ["pyproject.toml"],
      "issues": ["Python workspace detected but no pytest configuration … found"],
      "state": "engine-missing"
    }
  },
  "errors": [
    { "code": "engine-engine-missing", "details": {}, "message": "engine readiness state: engine-missing (engine=(none detected))" }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

The install hints are in `data.engine_readiness.issues[]` — **not** in
`errors[0].details` (which is `{}`). Real `issues[]` examples carry the
exact command, e.g. "pytest is not importable from the resolved
interpreter; install with: pip install pytest" or "`cargo nextest` is
not installed … Install with: cargo install cargo-nextest --locked …".
`engine-misconfigured` surfaces as the code
`engine-engine-misconfigured`. If policy permits installs, execute the
hint and retry; otherwise surface it.

:::

### `adapter-<kind>` (exit 4)

::: tabs
@tab For human

The engine launched but failed before producing parseable results — a
build error, a missing plugin, or a tool exiting non-zero. The code is
`adapter-<kind>` (e.g. `adapter-unparseable-output`,
`adapter-missing-plugin`, `adapter-missing-binary`, `adapter-timed-out`);
the message includes the engine's own stderr tail.

**Fix.** Read the stderr tail — the problem is at the engine level (your
build, your dependencies), not in Nove Test. Fix it and re-run.

An unknown token like `novetest frobnicate` is **not** "command not
found": the first non-verb token is treated as a test selector
(`novetest test frobnicate`), so the engine tries to run it and fails
with an adapter error.

@tab For agent

```json
{
  "command": "test",
  "data": {},
  "errors": [
    { "code": "adapter-unparseable-output", "details": {}, "message": "pytest-cov did not write coverage JSON to …/coverage.json; stderr tail: ERROR: file or directory not found: bogusverb\n\n" }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

`<kind>` ∈ `unparseable-output`, `missing-plugin`, `missing-binary`,
`missing-engine`, `timed-out`, `misconfigured-environment` (varies by
adapter). Engine-level issue — read `errors[0].message`, fix, retry.
Some adapters attach `details.install_hint`.

:::

### Exit code 3 (tests failed) — NOT an error

::: tabs
@tab For human

Your tests actually failed (`ok: true`, exit 3). The recommendation
block names where to look:

```
5 recommendations · 1 category · run_id=…

  ! [investigate_location] Investigate `subtract`@6 in `calc/arithmetic.py` (rank 1, ochiai=1.000, sbfl_per_test).
```

Fix the code or the test, re-run.

@tab For agent

```python
if exit_code == 3:
    assert env["ok"] is True               # DATA, not a tool error
    for rec in env["data"]["recommendations"]:
        route(rec["category"])             # 7 categories; priority int, lower = higher
```

Recommendations carry a `category` and an int `priority` (1–7,
lower = higher) — there is **no** `severity` field. Categories:
`regression_with_localization` (1), `investigate_location` (2),
`investigate_regression` (3), `coverage_gap` (4), `flaky_suspected` (5,
**never fires today** — replay isn't wired into `test`),
`unavailable_analysis` (6), `all_green` (7, exclusive).

:::

### `not-found` (exit 2) — bad `run_id`

::: tabs
@tab For human

```
✗ coverage.show
  not-found: No Memory Entry for run_id='FAKE123'
```

A `run_id` passed to `inspect` / `coverage show` / `regression compare`
/ `localization` / `replay` / `memory show` / `memory delete` matched no
run.

**Fix.**

```bash
novetest memory list
```

Copy a real ULID (26 chars, e.g. `01KVYRRRN9FWVNQWVHNE1QHAQ4`); partial
matches are rejected.

@tab For agent

```json
{
  "command": "coverage.show",
  "data": {},
  "errors": [
    { "code": "not-found", "details": {}, "message": "No Memory Entry for run_id='FAKE123'" }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

`novetest memory list`, read
`data.entries[].run_record.run_reference.run_id`, retry. Look-up + retry
is always safe.

:::

---

## Coverage issues

::: tabs
@tab For human

### `— unavailable (missing-derived-facts)`

```
✓ per-test · 13/13 statements (100.0%) · run_id=…   ← healthy
— unavailable (missing-derived-facts)               ← no coverage recorded
```

`coverage show` is a cache read — it never derives on demand. If the run
came from `novetest run` **without** `--coverage`, no facts were
recorded.

**Fix.**

```bash
novetest run --coverage    # -c is the short form
# or
novetest test              # `test` ALWAYS collects coverage
```

`novetest test` has no `--coverage` flag (it always collects); only
`novetest run` takes `--coverage` / `-c`.

@tab For agent

`coverage show` returns exit 0 / `ok: true` even when facts are missing
— unavailability is data:

```json
"coverage_outcome": {
  "kind": "unavailable",
  "reason": "missing-derived-facts",
  "detail": "No coverage_facts.json found for this run; call derive_coverage_facts first",
  "run_reference": { … }
}
```

Re-run with `novetest run --coverage` (or `novetest test`) to populate.
Coverage reasons are hyphenated (`missing-derived-facts`,
`missing-native-payload`, …).

:::

**Go projects never produce coverage facts.** The go-test adapter runs
your tests and writes a coverage profile, but the coverage engine
doesn't consume it, so `--coverage` on a Go project yields an
`unavailable` coverage outcome. The other five engines (pytest, jest,
cargo-test, junit, xunit) do produce coverage facts.

---

## `localization` issues

::: tabs
@tab For human

### `— unavailable (no_failed_tests)`

Expected on a green run — SBFL has nothing to rank. No fix needed.
(Localization reasons use underscores, unlike coverage's hyphens.)

### `— unavailable (missing_derived_facts)`

The run lacks the per-test data SBFL needs (commonly: coverage was
unavailable). Make sure coverage is collected (`novetest test`, or
`novetest run --coverage`), then re-run `novetest localization <run_id>`.

### `invalid-flag` (exit 2)

```
✗ localization
  invalid-flag: Invalid --formula='nope'; expected one of ['dstar2', 'ochiai', 'op2', 'tarantula']
```

Pick a value from the set: `ochiai` (default), `op2`, `dstar2` (note:
`dstar2`, not `dstar`), `tarantula`. `--top-n` must be a positive
integer (default 10).

### `⚠ localization-cache-rederived`

You re-invoked with a `--formula`/`--top-n` that differs from the
cached run. The CLI invalidated the cache and re-derived. Informational.

### `⚠ localization-formula-noop-in-mode`

`--formula` was ignored because the SBFL mode is `failure_proximity`
(which pins `ochiai`). Drop the flag, or accept the warning.

@tab For agent

`localization` returns exit 0 / `ok: true` even when unavailable:

```json
"localization_outcome": {
  "kind": "unavailable",
  "reason": "no_failed_tests",
  "detail": "run has no failed test results",
  "run_reference": { … }
}
```

Localization reasons are **underscored**: `no_failed_tests`,
`no_coverage`, `no_run_evidence`, `missing_derived_facts`,
`run_not_analyzable`. A bad flag is exit 2:

```json
{
  "command": "localization",
  "data": {},
  "errors": [
    { "code": "invalid-flag", "details": {}, "message": "Invalid --formula='nope'; expected one of ['dstar2', 'ochiai', 'op2', 'tarantula']" }
  ],
  "ok": false, "schema": "novetest/v1", "warnings": []
}
```

`--formula` ∈ `{ochiai, op2, dstar2, tarantula}`; `--top-n` ≥ 1
(`Invalid --top-n=0; expected a positive integer`). Warnings
`localization-cache-rederived` / `localization-formula-noop-in-mode`
never affect `ok` or exit code.

:::

---

## `reset` issues

### `confirm-required` (exit 2)

::: tabs
@tab For human

```
✗ reset
  confirm-required: `novetest reset` is destructive. Pass --confirm to acknowledge.
```

`reset` hard-wipes the store and refuses to run without acknowledgement.

**Fix.**

```bash
novetest reset --confirm
```

```
✓ Reset .novetest/ at /path/to/.novetest
  removed: nothing
  engine readiness: ready — python/pytest 9.0.3
```

`reset --confirm` is the only hard wipe. `memory delete <run_id>` only
**tombstones** a run — it still appears in `memory list`/`memory show`
with a `tombstoned_at` timestamp.

@tab For agent

```json
{
  "command": "reset",
  "data": {},
  "errors": [
    { "code": "confirm-required", "details": {}, "message": "`novetest reset` is destructive. Pass --confirm to acknowledge." }
  ],
  "ok": false, "schema": "novetest/v1", "warnings": []
}
```

Re-issue as `novetest reset --confirm` ONLY with operator approval —
it hard-wipes all runs/findings. `memory delete` tombstones reversibly.

:::

---

## `replay` issues

`replay` actually re-executes the run, so it can hit engine problems.
A healthy replay reads `✓ reproducible · 1/1 · run_id=…`.

::: tabs
@tab For human

### `? unavailable (engine-not-ready)` / `? unavailable (target-missing)`

The engine binary is gone, or the original target no longer exists
(exit 4). Same fix as `engine-missing`: install/configure the engine, or
restore the target.

### `? unavailable (missing-derived-facts)`

Not enough recorded evidence to replay (exit 0 — data, not an error).

### Tuning

```bash
novetest replay <run_id> --reruns 3 --timeout 1200
```

`--reruns` defaults to 1, `--timeout` to 600.0 seconds.

`inspect`'s `replay  ? unavailable (missing-derived-facts)` line is
expected — `inspect` is a pure read and never replays. Use
`novetest replay <run_id>` to actually replay.

@tab For agent

`replay` is the one read-style verb whose unavailable reasons split by
exit code: `engine-not-ready` / `target-missing` → exit 4;
`original-not-found` → exit 2; `tombstoned-original` /
`context-reconstruction-failed` / `missing-derived-facts` → exit 0
(`ok: true`). `--reruns` (default 1) and `--timeout` (default 600.0)
control re-execution.

:::

---

## Output-mode issues

::: tabs
@tab For human

#### "I see JSON everywhere, not pretty text"

TEXT mode is used only when stdout is a real terminal; piped/redirected
output defaults to JSON. You're either piping
(`novetest test | less` → use `novetest --output text test`) or have
`NOVETEST_OUTPUT=json` exported (`unset NOVETEST_OUTPUT`). Precedence is
`--output` > `NOVETEST_OUTPUT` > TTY autodetect.

#### "My CI logs are full of pretty JSON; I want one line per envelope"

```bash
NOVETEST_OUTPUT=ndjson novetest test
```

NDJSON is one compact line per envelope.

#### `--output bogus` prints a traceback

An invalid `--output` (or `NOVETEST_OUTPUT`) value is rejected before
the envelope machinery starts — raw traceback, exit 1, no envelope. Use
only `text`, `json`, or `ndjson`.

#### "I expected color"

There is no ANSI color. The glyph palette (`✓ ✗ — ⚠ ! ? · ↳`) carries
meaning instead.

@tab For agent

#### "I get text when I expected JSON"

You're invoking from a TTY without an override. Pin once:

```bash
export NOVETEST_OUTPUT=json
```

Or per-invocation: `novetest --output json <verb>`. JSON is
pretty-printed (indent 2, sorted keys); NDJSON is one compact line.
Precedence: `--output` > `NOVETEST_OUTPUT` > TTY autodetect. An invalid
value raises before the envelope is built (traceback, exit 1) — validate
your value. Never parse text mode; only the JSON/NDJSON shape is stable.

:::

---

## Project Store issues

### `store-corrupt` / `store-wipe-failed` (exit 5)

`.novetest/store.json` is unreadable or malformed (`store-corrupt`), or a
filesystem error interrupted `reset` (`store-wipe-failed`).

**Fix.** Check permissions, then worst case:

```bash
rm -rf .novetest
novetest init
```

You lose run history but recover the store. (Agents: do NOT auto-recover
— this destroys data; surface to the operator.)

### "How do I share run history with my team?"

Commit `.novetest/` to git — plain JSON, diffs cleanly. Most teams
choose NOT to (history is large and per-developer); do it only for a
single team-shared baseline.

### "How do I clean up old runs?"

```bash
novetest memory delete <run_id>   # tombstone one run
# or wipe everything:
novetest reset --confirm
```

---

## Idempotency and retry policy (agent reference)

::: tabs
@tab For human

(Mostly matters for agents and CI. Interactively, retrying any verb is
safe; `reset --confirm` and `rm -rf .novetest` are the only destructive
actions.)

@tab For agent

| Verb | Idempotent? | Retry policy |
|---|---|---|
| `init` | Yes (no-op on existing store) | Retry safe. |
| `test` / `run` | Each call produces a new run | Retry produces a new `run_id`. |
| `status` / `inspect` | Read-only | Retry safe. |
| `coverage show` / `diff` | Read-only | Retry safe. |
| `regression compare` / `latest` | Cache-aware | Retry safe. |
| `localization` / `latest` | Cache-aware; warns on rederive | Retry safe; cache invalidated if flags differ. |
| `compare` | Read-only | Retry safe. |
| `replay` | Re-executes | Retry safe; each adds another rerun. |
| `memory list` / `show` | Read-only | Retry safe. |
| `memory delete` | Tombstone is atomic | Retry safe (re-tombstone is a no-op). |
| `reset --confirm` | Wipes + re-inits | **Destructive** — operator approval only. |
| `licenses` | Read-only | Retry safe. |

Nove Test does **no network I/O** at invocation time (only the install
script does, once).

:::

### When to abort vs when to recover

::: tabs
@tab For human

(Same caveat — this is mostly for agents.)

@tab For agent

| Situation | Action |
|---|---|
| Exit 0 / 3 | Success path — read the envelope (3 = tests failed, still `ok: true`). |
| Exit 2, `uninitialized` | Auto-recover: `init` then retry. |
| Exit 2, `not-found` | Auto-recover: `memory list` and pick. |
| Exit 2, `invalid-flag` | Auto-recover: fix the value. |
| Exit 2, `confirm-required` | Re-issue with `--confirm` ONLY with operator approval. |
| Exit 5, `store-corrupt` / `store-wipe-failed` | Do NOT auto-recover. Surface. |
| Exit 4, `engine-engine-missing` / `-misconfigured` | Auto-recover IF policy permits installs (use `data.engine_readiness.issues[]`). Else surface. |
| Exit 4, `adapter-*` | Surface (engine-level issue, not a Nove Test bug). |
| Exit 1, `cli-error` | Surface with the envelope. Do not retry blindly. |

:::

---

## Health-check pattern (agent reference)

::: tabs
@tab For human

(For interactive use, the sanity checks on the
[Installation](./installation.md) page are enough.)

@tab For agent

```bash
# 1) Binary on PATH
command -v novetest >/dev/null || { echo "novetest missing"; exit 1; }

# 2) Identity envelope
NOVETEST_OUTPUT=json novetest --version | \
  jq -e '.ok == true and .schema == "novetest/v1"' \
  || { echo "version envelope malformed"; exit 1; }

# 3) Project store exists (if you have a workspace)
if [ -d ./.novetest ]; then
  NOVETEST_OUTPUT=json novetest status | \
    jq -e '.ok == true' \
    || { echo "status envelope malformed"; exit 1; }
fi
```

Pass = ready to drive. Fail = surface to operator.

:::

---

## When all else fails

1. `novetest --version` to confirm the binary is sane.
2. `novetest --help` to confirm the verb exists.
3. `novetest status` (after `init`) to see what's actually stored.
4. Re-run with `novetest --output json <verb>`; `errors[0]` carries more
   detail than the text-mode line.
5. Search the issue tracker:
   <https://github.com/Nove-Lab/Nove-Test/issues>
6. File a new issue with the JSON envelope and your OS / engine versions.

---

## What to read next

- Exit-code -> meaning table → [Understanding Results -> Exit codes](./understanding-results.md#exit-codes).
- Per-engine setup → [Supported Languages](./supported-languages.md).
- Deeper verbs → [Advanced Usage](./advanced-usage.md).
