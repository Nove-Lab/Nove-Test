# Troubleshooting

This page is organized by failure mode. Find the shape that matches
your problem, read the one-line fix. Most error envelopes pair an
exit code with a machine-friendly `errors[0].code`; the
quick-reference table is in [Understanding Results -> `errors[].code`
catalog](./understanding-results.md#errorscode-catalog-failure-paths).

::: tabs
@tab For human

Most error envelopes in text mode look like:

```
✗ <verb>
  <code>: <human-readable message>
  <optional hint>
```

The first line tells you which verb failed; the second tells you
the machine-friendly error code (use this for searching docs /
issues) and a sentence describing what went wrong; the optional
third line is typically a one-line install hint.

@tab For agent

When `ok: false` comes back, the canonical routing is:

```python
err = envelope["errors"][0]
code = err["code"]
message = err["message"]
hint = err.get("details", {}).get("install_hint")
```

Route on the exit code FIRST, then on `errors[0].code`. Look at
the quick-reference matrix below before drilling into a specific
failure mode.

#### Quick reference — exit code × `errors[0].code`

| Exit | `errors[0].code` | Recovery |
|---|---|---|
| 0 | (no error) | Success path. |
| 1 | `cli-error` | Bug. Capture envelope, file issue. Do not retry blindly. |
| 2 | `uninitialized` | Run `novetest init`, then retry. |
| 2 | `store-corrupt` | (Optional) `rm -rf .novetest && novetest init` (destroys history), then retry. |
| 2 | `not-found` | The `run_id` you passed doesn't exist. List with `novetest memory list`, pick a real ULID. |
| 2 | `invalid-flag` | Flag value outside the closed set. Read `errors[0].message` for allowed values. |
| 2 | `not-implemented` | Verb stub not yet wired (should not occur on the happy path at MVP). |
| 3 | (no error) | `ok: true`; this is "user's tests failed". Read `data.recommendations`. |
| 4 | `engine-missing` | Install the engine per `details.install_hint`. |
| 4 | `engine-misconfigured` | Fix per `details.install_hint`. |
| 4 | `engine-not-ready` | Inspect `details` for the issue list. |
| 4 | `adapter-<engine>` | Adapter invocation failed at the engine level. `details.install_hint` often available. |
| 5 | `store-corrupt` | Same as exit-2 store-corrupt path, but more severe — usually filesystem-level. |

:::

---

## Install issues

### `command not found: novetest`

You ran the install script but `novetest` isn't on PATH.

**Fix.** Add `~/.local/bin` to your PATH:

```bash
# Linux / macOS — add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"
```

```powershell
# Windows — add to PowerShell profile
$env:PATH = "$HOME\.local\bin;$env:PATH"
```

Then `source` the profile (or open a new shell) and re-check with
`novetest --version`.

### Install script aborts with `SHA-256 mismatch`

This is the install script's loud-abort guard. It means the
binary's hash did not match the published `.sha256` sidecar — either
the download was corrupted in flight, or the release artifacts are
inconsistent.

**Fix.**

1. Re-run the install script (the most common cause is a flaky
   network).
2. If it still fails, pin a specific version:
   `NOVETEST_INSTALL_VERSION=v0.1.2 curl ... | sh`.
3. If THAT still fails, file an issue with your OS / arch / network
   situation.

### First run is slow (5–25 seconds)

Expected. PyApp self-extracts the bundled Python on the first
invocation per binary version per user. Subsequent invocations are
warm and fast (sub-second).

### Windows: PowerShell script blocked

Your execution policy is blocking `install.ps1`.

**Fix.** Run the install with bypass:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Or unblock the file first:

```powershell
Unblock-File install.ps1
.\install.ps1
```

---

## `init` issues

### `uninitialized` (exit 2) — non-`init` verb from outside a project

::: tabs
@tab For human

You ran `novetest test` (or any other operating verb) from a
directory whose tree contains no `.novetest/`.

Output (illustrative):

```
✗ test
  uninitialized: No Project Store found in this directory or any ancestor. Run `novetest init` to create one.
```

**Fix.** `cd` into your project root (or any subdirectory of it
after running `novetest init` there once), then re-run the verb.

@tab For agent

```json
{
  "errors": [
    {
      "code": "uninitialized",
      "message": "No Project Store found in this directory or any ancestor. Run `novetest init` to create one.",
      "details": {}
    }
  ]
}
```

**Cause.** Walked from `cwd` to root looking for `.novetest/`;
found nothing.

**Recovery.**

1. If your agent owns the project directory: `novetest init` then
   retry.
2. If your agent is invoked from outside the project tree: `cd`
   into the project first, or set
   `NOVETEST_HOME=/abs/path/to/.novetest` to pin the store.

**Idempotency.** Safe to retry indefinitely after `init`.

:::

### `store-corrupt` (exit 2 or 5)

::: tabs
@tab For human

`.novetest/store.json` exists but is unreadable or malformed.

Output:

```
✗ init
  store-corrupt: Project Store at /home/you/proj/.novetest is unreadable: <reason>.
```

**Fix.** Inspect the file to see if you can salvage it. If not (or
if you don't care about run history):

```bash
rm -rf .novetest
novetest init
```

That wipes all stored runs for this project. Your source code and
tests are untouched.

@tab For agent

```json
{
  "errors": [
    {
      "code": "store-corrupt",
      "message": "Project Store at <path> is unreadable: <reason>.",
      "details": { "store_path": "/path/.novetest" }
    }
  ]
}
```

**Cause.** `.novetest/store.json` is missing, malformed, or
permission-blocked.

**Recovery.**

1. Inspect `.novetest/store.json` directly. If you can fix it,
   retry.
2. Destructive recovery: `rm -rf .novetest && novetest init`.
   Wipes run history.

**Idempotency.** The destructive recovery is idempotent. Do NOT
auto-trigger this without operator approval; it permanently
destroys data.

:::

### `init` succeeded but `engine readiness: engine-missing`

`init` succeeded, but it could not find your test engine on PATH.

::: tabs
@tab For human

The `issue:` lines after the readiness line tell you what's
missing. Common cases:

| Engine | Hint |
|---|---|
| pytest | `pip install pytest` |
| jest | `npm install --save-dev jest` (in the project root) |
| go-test | install Go ≥ 1.21 from <https://go.dev/dl/> |
| cargo | `cargo install cargo-nextest --locked` |
| junit | install JDK ≥ 17 and Maven ≥ 3.9 or Gradle ≥ 7.6 |
| xunit | install .NET SDK ≥ 8.0 and add `xunit` ≥ 2.4 to your test project |

Re-run `novetest init` after installing.

@tab For agent

`init` envelope:

```json
{
  "ok": true,
  "data": {
    "engine_readiness": {
      "state": "engine-missing",
      "engine": "pytest",
      "ecosystem": "python",
      "issues": [
        "pytest is not installed in this environment"
      ]
    }
  }
}
```

`engine_readiness.state ∈ {"ready", "engine-missing",
"engine-misconfigured", "engine-not-ready"}`. Route off this.

`engine_readiness.issues[]` is a flat list of human-readable
actionable hints; surface them to the operator if your install
policy disallows auto-fix.

:::

---

## `test` / `run` issues

### `engine-missing` (exit 4)

Native test engine not on PATH. Same root cause as the
`engine-missing` readiness during `init`, but caught at run time.

::: tabs
@tab For human

If you have an engine on PATH but novetest still doesn't see it,
two common causes:

1. **Wrong shell.** novetest is using `/bin/sh`-like resolution —
   if you installed pytest only inside a Python venv that you
   haven't activated, novetest cannot see it.
2. **Wrong project.** Make sure you're in the right directory.
   `novetest init` records which engine was detected; `novetest
   test` from a fresh `.novetest/` re-probes.

@tab For agent

```json
{
  "errors": [
    {
      "code": "engine-missing",
      "message": "pytest is not installed in this environment.",
      "details": {
        "engine": "pytest",
        "ecosystem": "python",
        "install_hint": "pip install pytest"
      }
    }
  ]
}
```

**Cause.** Native engine binary not on PATH (`engine-missing`) or
present but unusable (`engine-misconfigured`, e.g. plugin missing).

**Recovery.**

1. If your agent has install permissions and a deterministic
   install policy: execute `details.install_hint` (it's a one-line
   shell command for each MVP engine — see
   [Supported Languages](./supported-languages.md) for the full
   toolchain matrix).
2. Otherwise: surface the hint to the operator and abort.

**Idempotency.** Re-invoking the failing verb after install is
safe. The first `novetest init` after install will record the
engine as `"ready"`.

:::

### Exit code 3 (tests failed) — NOT an error

This is product information, not a tooling problem. Your tests
actually failed. The recommendation block on stdout (text mode) or
the `data.recommendations[]` array (json mode) names which tests
and points you at where to look.

Treat this the same way you'd treat a failing `pytest` invocation —
fix the code or the test, re-run.

### `not-found` (exit 2) — bad `run_id`

You passed a `run_id` (to `inspect`, `coverage show`, `replay`,
`memory show`, `memory delete`, ...) that doesn't exist in the
store.

::: tabs
@tab For human

```bash
novetest memory list
```

Copy a real ULID from there. ULIDs are 26 chars; partial matches
are not accepted.

@tab For agent

```json
{
  "errors": [
    {
      "code": "not-found",
      "message": "Run record 01HX... not found in the Project Store.",
      "details": { "run_id": "01HX..." }
    }
  ]
}
```

**Recovery.** Call `novetest memory list`, pick a valid `run_id`.

**Idempotency.** Look-up + retry is always safe.

:::

### `invalid-flag` (exit 2)

::: tabs
@tab For human

You passed a flag value outside the allowed set. The error message
on stdout lists the allowed values; pick one of those.

@tab For agent

```json
{
  "errors": [
    {
      "code": "invalid-flag",
      "message": "--formula must be one of: ochiai, op2, dstar2, tarantula (got: 'fancy_formula').",
      "details": {
        "flag": "--formula",
        "value": "fancy_formula",
        "allowed": ["ochiai", "op2", "dstar2", "tarantula"]
      }
    }
  ]
}
```

**Recovery.** Read `details.allowed` (when present) and pick a
valid value.

**Idempotency.** Safe to retry with corrected value.

:::

### `adapter-<engine>` (exit 4 typically)

::: tabs
@tab For human

The adapter detected an engine-level failure that isn't a test
failure. Common cases: build error, missing dependency, version
mismatch. The error message includes the engine's own stderr tail.

**Fix.** Read the engine's own error message in the stderr tail.
Fix the underlying problem at the engine level (it's not a novetest
issue).

@tab For agent

```json
{
  "errors": [
    {
      "code": "adapter-cargo",
      "message": "cargo nextest exited non-zero before any test was reported (likely a build failure).",
      "details": {
        "exit_code": 101,
        "stdout_tail": "...",
        "stderr_tail": "...",
        "install_hint": "cargo install cargo-nextest --locked"
      }
    }
  ]
}
```

**Recovery.** Read `details.stderr_tail` for the engine's own
error message. Fix the underlying problem at the engine level.

**Idempotency.** Retry safe once the engine-level fix is applied.

:::

### `engine-misconfigured` warning

Adapter found the engine but flagged missing optional pieces.
Common case: `pytest-cov` not installed.

**Fix.** Install the missing piece (e.g. `pip install pytest-cov`).
Coverage will become `✓ available` on the next run. Until then,
the warning is informational only.

---

## `localization` issues

### `— unavailable (no_failed_tests)`

Expected on green runs. SBFL has nothing to rank when no test
failed.

**Fix.** None needed; this is the correct outcome.

### `— unavailable (missing-derived-facts)`

The run completed without recording the per-test data SBFL needs
(most commonly: coverage was unavailable, so per-test coverage
attribution is missing).

**Fix.** Install your engine's coverage tool (e.g. `pytest-cov`
for pytest), then re-run `novetest test`.

### `⚠ localization-cache-rederived`

You re-invoked `novetest localization` with a different `--formula`
than what was cached. The CLI rewrote the cache. This is
informational only.

### `⚠ localization-formula-noop-in-mode`

You passed `--formula` but the chosen SBFL mode is
`failure_proximity`, which doesn't use a formula. The flag was
ignored.

**Fix.** Drop the `--formula` flag in this mode, or accept the
warning.

---

## `replay` issues

### `? unable_to_replay (engine-unavailable)`

The host couldn't replay because the engine binary isn't available
anymore (or never was).

**Fix.** Same as `engine-missing`: install / configure the engine.

### `? unable_to_replay (replay-timeout)`

A rerun exceeded `--timeout` seconds.

**Fix.** Either fix the slow test, or bump the timeout:

```bash
novetest replay <run_id> --reruns 3 --timeout 1200
```

### `✗ inconsistent · 2/5 failed`

NOT an error. This is the actual product output telling you the
test result is flaky. The corresponding `flaky_suspect`
recommendation in the next `novetest test` will point you at the
unstable tests.

---

## Output-mode issues

::: tabs
@tab For human

#### "I see JSON everywhere, not pretty text"

You're either:

1. Piping (`novetest test | less`) → JSON is the default for pipes.
   Use `--output text` to force text.
2. Have `NOVETEST_OUTPUT=json` exported. Run
   `unset NOVETEST_OUTPUT` to release the override.

#### "My CI logs are full of pretty JSON; I want one line per envelope"

Use NDJSON:

```bash
NOVETEST_OUTPUT=ndjson novetest test
```

Each envelope becomes a single line.

#### "I expected color"

There is no ANSI color at MVP. The 7-glyph palette
(`✓ ✗ — ⚠ ! ? · ↳`) carries meaning instead. Color is queued for
post-MVP.

@tab For agent

#### "I get text when I expected JSON"

You're invoking from a TTY without an env override. Pin once at
session start:

```bash
export NOVETEST_OUTPUT=json
```

Or per-invocation:

```bash
novetest --output json <verb>
```

#### "My deterministic parser breaks across versions"

The JSON / NDJSON byte shape is **snapshot-pinned in CI** — drift
fails the release pipeline. If you observe drift in production,
file an issue with the two byte-different envelopes; this would be
a release-pipeline escape.

The text-mode bytes are NOT contractually pinned (only the JSON
shape is). Never parse text mode.

:::

---

## Project Store issues

### "How do I share run history with my team?"

Commit `.novetest/` to git. The whole tree is plain JSON files; it
diffs cleanly. Most teams choose NOT to do this (the history is
large and per-developer); it's the right answer only when you want
a single team-shared baseline.

### "How do I clean up old runs?"

Tombstone individual runs:

```bash
novetest memory delete <run_id>
```

Or wipe the whole store:

```bash
rm -rf .novetest
novetest init
```

Garbage collection of tombstones is post-MVP.

---

## Idempotency and retry policy (agent reference)

::: tabs
@tab For human

(Most of this matters only for agents and CI pipelines; if you're
clicking around interactively, retrying any verb is safe.)

@tab For agent

| Verb | Idempotent? | Retry policy |
|---|---|---|
| `init` | Yes (no-op on existing store) | Retry safe. |
| `test` | Yes (each call is independent; produces a new run) | Retry produces a new `run_id`. |
| `run` | Yes (each call produces a new run) | Same as `test`. |
| `status` | Yes (read-only) | Retry safe. |
| `inspect` | Yes (read-only) | Retry safe. |
| `coverage show` | Yes (read-only) | Retry safe. |
| `coverage diff` | Yes (read-only) | Retry safe. |
| `regression compare` | Yes (cache-aware derive-or-read) | Retry safe. |
| `regression latest` | Yes | Retry safe. |
| `localization` | Yes (cache-aware; emits warning on rederive) | Retry safe; cache is invalidated if flags differ. |
| `replay` | Yes (each call produces a new replay result) | Retry safe; each retry adds another rerun. |
| `compare` | Yes (read-only) | Retry safe. |
| `memory list` | Yes (read-only) | Retry safe. |
| `memory show` | Yes (read-only) | Retry safe. |
| `memory delete` | Yes (tombstone is atomic; re-tombstone of tombstoned entry is no-op) | Retry safe. |
| `licenses` | Yes (read-only) | Retry safe. |

Network calls: **none.** novetest does no network I/O at invocation
time (the install script does, once).

:::

### When to abort vs when to recover

::: tabs
@tab For human

(Same caveat — this is mostly for agents.)

@tab For agent

| Situation | Action |
|---|---|
| Exit 0 / 3 | Success path — read the envelope. |
| Exit 2, `uninitialized` | Auto-recover: `init` then retry. |
| Exit 2, `not-found` | Auto-recover: list and pick. |
| Exit 2, `invalid-flag` | Auto-recover: fix the value. |
| Exit 2, `store-corrupt` | Do NOT auto-recover. Surface to operator (destructive recovery destroys data). |
| Exit 4, `engine-missing` | Auto-recover IF policy permits installs. Else surface. |
| Exit 4, `adapter-*` | Surface to operator (engine-level issue, not a novetest problem). |
| Exit 5 | Surface to operator. |
| Exit 1, `cli-error` | Surface to operator with the envelope. Do not retry blindly. |

:::

---

## Health-check pattern (agent reference)

::: tabs
@tab For human

(For interactive use, the three sanity checks on the
[Installation](./installation.md) page are enough.)

@tab For agent

A minimal "is novetest usable right now" probe:

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
2. `novetest --help` to confirm the verb you're trying exists.
3. `novetest status` (after `init`) to see what's actually stored.
4. Re-run the failing verb with `NOVETEST_OUTPUT=json` to see the
   full envelope; the `errors[0]` object usually has more detail
   than the text-mode `<code>: <message>` line.
5. Search the GitHub issue tracker:
   <https://github.com/Nove-Lab/Nove-Test/issues>
6. File a new issue with the JSON envelope output and your OS /
   engine versions.

---

## What to read next

- Exit-code -> meaning table → [Understanding Results -> Exit codes](./understanding-results.md#exit-codes).
- Per-engine setup → [Supported Languages](./supported-languages.md).
- Deeper verbs → [Advanced Usage](./advanced-usage.md).
