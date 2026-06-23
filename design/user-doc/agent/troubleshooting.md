# Troubleshooting (Agent)

This page indexes failure modes by `errors[0].code` and provides
machine-deterministic recovery. Use this when an `ok: false` envelope
comes back; route on the exit code first, then on `errors[0].code`.

---

## Quick reference — exit code × `errors[0].code`

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

---

## Failure-mode reference

### `uninitialized` (exit 2)

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

**Cause.** Walked from `cwd` to root looking for `.novetest/`; found
nothing.

**Recovery.**
1. If your agent owns the project directory: `novetest init` then retry.
2. If your agent is invoked from outside the project tree: `cd` into the project first, or set `NOVETEST_HOME=/abs/path/to/.novetest` to pin the store.

**Idempotency.** Safe to retry indefinitely after `init`.

### `store-corrupt` (exit 2 or 5)

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
1. Inspect `.novetest/store.json` directly. If you can fix it, retry.
2. Destructive recovery: `rm -rf .novetest && novetest init`. Wipes run history.

**Idempotency.** The destructive recovery is idempotent. Do NOT auto-trigger this without operator approval; it permanently destroys data.

### `not-found` (exit 2)

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

**Cause.** You passed a `run_id` (to `inspect`, `coverage show`,
`replay`, `memory show`, `memory delete`) that doesn't match any
Memory Entry.

**Recovery.** Call `novetest memory list`, pick a valid `run_id`.

**Idempotency.** Look up + retry is always safe.

### `invalid-flag` (exit 2)

```json
{
  "errors": [
    {
      "code": "invalid-flag",
      "message": "--formula must be one of: ochiai, op2, dstar2, tarantula (got: 'fancy_formula').",
      "details": { "flag": "--formula", "value": "fancy_formula", "allowed": ["ochiai", "op2", "dstar2", "tarantula"] }
    }
  ]
}
```

**Cause.** Flag value outside the closed set.

**Recovery.** Read `details.allowed` (when present) and pick a valid
value. Or read the allowed values from `--help` envelope's
machine-readable verb spec.

**Idempotency.** Safe to retry with corrected value.

### `engine-missing` / `engine-misconfigured` / `engine-not-ready` (exit 4)

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
1. If your agent has install permissions and a deterministic install policy: execute `details.install_hint` (it's a one-line shell command for each MVP engine — see [languages.md](./languages.md) for the full toolchain matrix).
2. Otherwise: surface the hint to the operator and abort.

**Idempotency.** Re-invoking the failing verb after install is safe.
The first `novetest init` after install will record the engine as
`"ready"`.

### `adapter-<engine>` (exit 4 typically)

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

**Cause.** Native adapter detected an engine-level failure that isn't a
test failure. Common cases: build error, missing dependency, version
mismatch.

**Recovery.** Read `details.stderr_tail` for the engine's own error
message. Fix the underlying problem at the engine level (it's not a
Nove Test issue).

**Idempotency.** Retry safe once the engine-level fix is applied.

### `cli-error` (exit 1)

```json
{
  "errors": [
    {
      "code": "cli-error",
      "message": "Unexpected internal exception: <type>: <message>",
      "details": { "traceback_tail": "..." }
    }
  ]
}
```

**Cause.** Unhandled CLI exception. Should not occur.

**Recovery.** Do NOT auto-retry; capture the envelope and report.

### `not-implemented` (exit 2)

Should not occur in `v0.1.2`. If you see it, you're calling a
post-MVP verb whose stub returns this. Capture and report.

---

## Stage-eligibility surprises (NOT errors)

When `ok: true` but a stage is `"unavailable"`:

```json
"stage_eligibility": {
  "coverage": "available",
  "regression": "unavailable",
  "localization": "available",
  "replay": "not_run"
}
```

These are **structural facts**, not errors. Common reasons:

| Stage | Reason | Meaning |
|---|---|---|
| `regression` | `no-comparable-baseline` | First run on this target. Next run will populate. |
| `localization` | `no_failed_tests` | All tests green; nothing to localize. |
| `localization` | `missing-derived-facts` | Per-test data not captured (e.g. coverage tool absent → no per-test coverage attribution). |
| `replay` | `not-run` | `novetest test` deliberately skips replay. Call `novetest replay <run_id>` explicitly. |

Your agent should NOT treat these as errors; route around them.

---

## Warning codes (NOT errors)

`envelope.warnings[].code` ∈ closed set:

| Code | Meaning | Agent action |
|---|---|---|
| `localization-cache-rederived` | Cache rewritten due to flag mismatch. | Log; ignore. |
| `localization-formula-noop-in-mode` | `--formula` ignored in `failure_proximity` mode. | Log; drop the flag on next call. |
| `engine-misconfigured` | Optional engine piece missing (e.g. coverage tool). | Log; consider installing per hint. |
| `junit-multiple-build-systems` | Both `pom.xml` and `build.gradle` present; Maven chosen. | Log; rename/remove one to disambiguate. |
| `coverlet-floor-degraded` | .NET project pins old Coverlet; per-test coverage unavailable. | Log; bump Coverlet to ≥ 6.0.2 if you need per-test SBFL. |

Warnings never affect exit code or `ok`. Log them for observability;
they are a degradation signal but not a failure.

---

## Idempotency and retry policy

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

Network calls: none. Nove Test does no network I/O at invocation time
(the install script does, once).

---

## When to abort vs when to recover

| Situation | Action |
|---|---|
| Exit 0 / 3 | Success path — read the envelope. |
| Exit 2, `uninitialized` | Auto-recover: `init` then retry. |
| Exit 2, `not-found` | Auto-recover: list and pick. |
| Exit 2, `invalid-flag` | Auto-recover: fix the value. |
| Exit 2, `store-corrupt` | Do NOT auto-recover. Surface to operator (destructive recovery destroys data). |
| Exit 4, `engine-missing` | Auto-recover IF policy permits installs. Else surface. |
| Exit 4, `adapter-*` | Surface to operator (engine-level issue, not a Nove Test problem). |
| Exit 5 | Surface to operator. |
| Exit 1, `cli-error` | Surface to operator with the envelope. Do not retry blindly. |

---

## Health-check pattern for agents

A minimal "is Nove Test usable right now" probe:

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

---

## What to read next

- Full exit-code table + envelope shapes → [after-test.md](./after-test.md).
- Per-engine install hints → [languages.md](./languages.md).
- Deeper verbs (`replay`, `localization`, `memory delete`) → [advanced.md](./advanced.md).
