# Troubleshooting (Agent)

This page indexes failure modes by exit code and `errors[0].code`, with
machine-deterministic recovery. Use it when an `ok: false` envelope (or
a non-zero exit) comes back: route on the **exit code first**, then on
`errors[0].code`.

Pin JSON output for the whole session so the byte shape is stable:

```bash
export NOVETEST_OUTPUT=json
```

Every envelope has exactly these top-level keys (JSON-sorted):
`command, data, errors, ok, schema, warnings`. `schema` is always
`"novetest/v1"`. `errors` / `warnings` are arrays of
`{code, message, details}`. There is **no** top-level `version`,
`verb`, or `exit_code` field — route on the process exit code plus
`errors[0].code`.

---

## Quick reference — exit code × `errors[0].code`

| Exit | `errors[0].code` | Meaning / recovery |
|---|---|---|
| 0 | (none) | Success. `ok: true`. |
| 1 | `cli-error` | Uncaught internal error (`command: "cli"`). Capture envelope, file issue. Do not retry blindly. |
| 2 | `uninitialized` | No `.novetest/` store. Run `novetest init`, then retry. |
| 2 | `not-found` | The `run_id` doesn't exist. `novetest memory list`, pick a real ULID. |
| 2 | `invalid-flag` | Flag value outside the closed set. Read `errors[0].message` for the allowed list. |
| 2 | `confirm-required` | `novetest reset` needs `--confirm`. Re-issue with `--confirm` (destructive). |
| 2 | `adapter-invalid-target` | Malformed test target (dash-/flag-/metachar-shaped) rejected before launch. A **caller usage error** — fix the target expression, then retry. |
| 3 | (none) | `ok: true` — **the user's tests failed or errored.** Read `data.recommendations` (or `run_record.status` on `run`). Not a tool error. |
| 4 | `engine-missing` | No usable engine. Read `data.engine_readiness.issues[]` for install hints. |
| 4 | `engine-misconfigured` | Engine applies but tooling missing. Read `data.engine_readiness.issues[]`. |
| 4 | `adapter-<kind>` | Engine ran but failed (build error, missing plugin, timeout). Read `errors[0].message` (stderr tail). (`adapter-invalid-target` is the exception — exit 2, a usage error; see above.) |
| 5 | `store-corrupt` / `store-wipe-failed` | Storage-level failure. Surface to operator. |

> Two things that bite parsers: an unready engine surfaces the readiness
> state **verbatim** as the error code (`engine-missing` /
> `engine-misconfigured` — the code IS the state, no extra prefix), and
> adapter codes are keyed on the **failure kind**
> (`adapter-unparseable-output`, `adapter-invalid-target`), not the
> engine name. There is no `engine-not-ready` code and no
> `not-implemented` runtime code.

---

## Failure-mode reference (real envelopes)

### `uninitialized` (exit 2)

```json
{
  "command": "run",
  "data": {},
  "errors": [
    {
      "code": "uninitialized",
      "details": {},
      "message": "No Project Store found in this directory or any ancestor. Run `novetest init` to create one."
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

**Cause.** Walked from `cwd` up to root looking for `.novetest/`; found
nothing.

**Recovery.** `novetest init` in the project root, then retry. If you're
invoked from outside the project tree, `cd` into it first.

**Idempotency.** Safe to retry indefinitely after `init`.

### `no-engine-detected` (exit 4)

Two shapes, discriminated by the `data` payload:

- **`init` on a markerless directory** — nothing created.
  `data.candidates[]` lists `{ecosystem, engine_name, path}` sub-projects
  (bounded scan, depth ≤ 2; `data.scan_refused: true` at `/` and `$HOME`
  — scan not attempted). Recovery: `cd` into each candidate `path`, run
  `init` there. Do NOT create `.novetest/` in directories the operator
  didn't designate.
- **`run` / `test` on a markerless anchor** (a pin-less legacy store with
  no engine marker at the workspace root) — same `no-engine-detected`
  code, but the payload is `data.engine_readiness` (`state:
  "engine-missing"`), **not** `data.candidates`. Recovery: `novetest init`
  (or `novetest init --engine <name>`) at the anchor to pin an engine,
  then retry.

### `engine-ambiguous` (exit 2)

≥ 2 viable engines (marker + toolchain-READY) at the init directory —
or a legacy pin-less store at such a root. Nothing is created/wiped.
Recovery: `novetest init --engine <name>` with a value from
`data.candidates[]`. Viability is host-dependent; never cache this
outcome across machines.

### `engine-missing` (exit 4)

```json
{
  "command": "run",
  "data": {
    "engine_readiness": {
      "ecosystem": null,
      "engine": null,
      "engine_version": null,
      "evidence": ["pyproject.toml"],
      "issues": ["Python workspace detected but no pytest configuration (pytest.ini, [tool.pytest.ini_options], conftest.py, or tests/ dir) found"],
      "state": "engine-missing"
    }
  },
  "errors": [
    {
      "code": "engine-missing",
      "details": {},
      "message": "engine readiness state: engine-missing (engine=(none detected))"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

**Cause.** No supported `(ecosystem, engine)` pair applies, or the
engine binary itself is absent.

**Recovery.** The actionable hints are in
`data.engine_readiness.issues[]` — **not** in `errors[0].details`
(which is `{}`). Read `data.engine_readiness.state`
(`engine-missing` | `engine-misconfigured`) and the `issues[]` strings,
which carry the exact install command, e.g.:

| Engine | `issues[]` text (real) |
|---|---|
| pytest (no config) | "Python workspace detected but no pytest configuration … found" |
| pytest (not importable) | "pytest is not importable from the resolved interpreter; install with: pip install pytest" |
| pytest (plugin) | "pytest-json-report plugin is not importable; install with: pip install pytest-json-report" |
| jest (no node) | "Node.js (`node`/`npx`) not found on PATH; install Node.js >=18 …" |
| jest (absent) | "jest not found in package.json … install with: npm install --save-dev jest" |
| cargo-test | "`cargo nextest` is not installed … Install with: cargo install cargo-nextest --locked …" |
| junit | "`java` not found on PATH; install JDK 17+" |

If your policy permits installs, execute the hint, then retry. Otherwise
surface the `issues[]` to the operator and abort. After a fix, the next
`novetest init` records `engine_readiness.state == "ready"`.

> `engine_readiness.state` is one of exactly three values:
> `ready`, `engine-missing`, `engine-misconfigured`. The `engine-missing`
> and `engine-misconfigured` states surface as the error code of the
> **same name** — the code IS the state.

### `adapter-<kind>` (exit 4)

```json
{
  "command": "test",
  "data": {},
  "errors": [
    {
      "code": "adapter-unparseable-output",
      "details": {},
      "message": "pytest-cov did not write coverage JSON to …/coverage.json; stderr tail: ERROR: file or directory not found: bogusverb\n\n"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

**Cause.** The engine launched but failed before producing parseable
output. `<kind>` ∈ `unparseable-output`, `missing-plugin`,
`missing-binary`, `missing-engine`, `timed-out`,
`misconfigured-environment` (the exact set varies by adapter). This is an
engine-level problem (build error, missing dependency), not a Nove Test
bug. Some adapter errors attach `details.install_hint`. (`invalid-target`
is a caller usage error, NOT an engine failure — it exits **2**, see the
next section.)

**Recovery.** Read `errors[0].message` for the engine's stderr tail; fix
the underlying issue, then retry. (Note: an unknown verb like
`novetest bogusverb` becomes `novetest test bogusverb` and surfaces here
as an adapter error — it is NOT a "command not found".)

### `adapter-invalid-target` (exit 2)

**Cause.** The target expression was rejected at the adapter boundary
**before any spawn** — a dash-/flag-/metachar-shaped target that would be
consumed as an engine flag or shell metacharacter, e.g.
`novetest run -- --pdb`. The error code is `adapter-invalid-target` (an
`adapter-<kind>` code, kind `invalid-target`), but this is a **caller
usage error** — you passed a malformed argument — so it exits **2**
(`EXIT_USAGE`), not exit 4 like the engine-level adapter kinds above.

**Recovery.** Fix the **target expression** (not the engine): drop the
leading dash / flag / shell metacharacter, then retry. This is a
usage-error recovery path (correct the argument), distinct from the
engine-remediation path (install/repair the toolchain) that the exit-4
`adapter-<kind>` codes call for.

### `not-found` (exit 2)

```json
{
  "command": "coverage.show",
  "data": {},
  "errors": [
    {
      "code": "not-found",
      "details": {},
      "message": "No Memory Entry for run_id='FAKE123'"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

**Cause.** A `run_id` passed to `inspect` / `coverage show` /
`coverage diff` / `regression compare` / `localization` / `replay` /
`memory show` / `memory delete` matched no Memory Entry. The guard
short-circuits before the engine runs.

**Recovery.** `novetest memory list`, read `data.entries[].run_record.run_reference.run_id`,
pick a valid 26-char ULID. Look-up + retry is always safe.

### `invalid-flag` (exit 2)

```json
{
  "command": "localization",
  "data": {},
  "errors": [
    {
      "code": "invalid-flag",
      "details": {},
      "message": "Invalid --formula='nope'; expected one of ['dstar2', 'ochiai', 'op2', 'tarantula']"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

**Cause.** Flag value outside the closed set. Validated at the CLI
boundary before any engine work. `details` is `{}`; the allowed values
are listed in `message`.

**Recovery.** Pick a valid value. `--formula` ∈
`{ochiai, op2, dstar2, tarantula}` (default `ochiai`); `--top-n` must be
a positive integer (default 10; `Invalid --top-n=0; expected a positive
integer`). Retry with the corrected value.

### `confirm-required` (exit 2)

```json
{
  "command": "reset",
  "data": {},
  "errors": [
    {
      "code": "confirm-required",
      "details": {},
      "message": "`novetest reset` is destructive. Pass --confirm to acknowledge."
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

**Cause.** `novetest reset` refuses to wipe the store without explicit
acknowledgement.

**Recovery.** Re-issue as `novetest reset --confirm` ONLY with operator
approval — it hard-wipes all runs/findings and re-initializes. (Contrast
`memory delete <run_id>`, which only tombstones, reversibly.)

### `store-corrupt` (exit 5) / `store-wipe-failed` (exit 5)

```json
{
  "errors": [
    { "code": "store-corrupt", "details": {}, "message": "…" }
  ]
}
```

**Cause.** `.novetest/store.json` is missing, malformed, or
permission-blocked (`store-corrupt`); or a filesystem error interrupted
`reset` (`store-wipe-failed`).

**Recovery.** Do NOT auto-recover — destructive recovery
(`rm -rf .novetest && novetest init`) permanently destroys history.
Surface to the operator.

### `cli-error` (exit 1)

```json
{
  "command": "cli",
  "data": {},
  "errors": [
    { "code": "cli-error", "details": {}, "message": "…" }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

**Cause.** An uncaught internal exception (note `command: "cli"`).
Should not occur.

**Recovery.** Do NOT auto-retry. Capture the envelope and report.

> There is no `not-implemented` runtime code. Every listed verb is a
> real handler; the stub machinery is dead code. Never branch on
> `not-implemented`.

---

## Exit 3 is not an error (the most important rule)

A failing **or errored** test run returns `ok: true`, exit `3`, an empty
`errors` array, and a populated `data.recommendations`. An *errored*
suite — one that crashed before producing normal results (e.g. a pytest
collection / import error) — is still a persisted user result:
`data.memory_entry.run_record.status` (`"errored"` vs `"failed"`)
discriminates it. Route on the exit code, not on `ok`:

```python
exit_code = run_novetest("test")          # process return code
env = json.loads(stdout)
if exit_code == 0:
    pass                                   # all green
elif exit_code == 3:
    assert env["ok"] is True               # tests failed — DATA, not an error
    handle(env["data"]["recommendations"]) # category-routed below
elif exit_code in (2, 4, 5):
    handle_tool_error(env["errors"][0]["code"])
```

Each recommendation has a `category` (one of 7 strings) and a `priority`
int (1–7, **lower = higher priority**) — there is no `severity` field.
Route on `category`:

| `category` | priority | agent action |
|---|---|---|
| `regression_with_localization` | 1 | A newly-failing test maps to a ranked location. Highest-signal fix target. |
| `investigate_location` | 2 | SBFL-ranked suspicious location. Open `slots.file` @ `slots.primary_line`. |
| `investigate_regression` | 3 | Newly-failing transition vs baseline. |
| `coverage_gap` | 4 | Uncovered lines overlap a suspect location. |
| `flaky_suspected` | 5 | Fires only with `novetest test --reruns N` (N ≥ 1) when the failed run's whole-run replay diverges. Empty `test_id` = divergence across several tests. |
| `unavailable_analysis` | 6 | Tests failed but a stage was unavailable. Read `slots.reason_per_stage`. |

(Authoritative category list: `design/implementation-plan/recommendation-synthesis.md` §8.)
| `all_green` | 7 | No failures, no regressions. (Exclusive — never coexists with another.) |

---

## Zero-collected explicit targets (NOT an error — but check)

An explicit target that matches nothing (typo, non-anchor-relative
path) yields `collected: 0, total: 0, status: "passed"`, exit 0.
Before treating a targeted run as green, assert
`data.memory_entry.run_record.total > 0`.

## Stage-eligibility surprises (NOT errors)

In a `test` envelope, `data.stage_eligibility` reports per-stage
availability. These are structural facts, not errors:

```json
"stage_eligibility": {
  "coverage": "available",
  "localization": "sbfl_per_test",
  "regression": "unavailable",
  "replay": "not_run"
}
```

| Stage | Value | Meaning |
|---|---|---|
| `coverage` | `available` / `unavailable` / `not_applicable` | Coverage facts derived (or not). |
| `regression` | `available` / `unavailable` / `not_applicable` | `unavailable` on the first run of a target (no baseline yet). |
| `localization` | SBFL **mode** string (`sbfl_per_test` / `sbfl_aggregate` / `failure_proximity`) when a finding exists; else `unavailable` | NOT the literal word `available` — it surfaces the mode. |
| `replay` | always `not_run` | `test` deliberately skips replay. Call `novetest replay <run_id>` explicitly. |

Route around `unavailable`/`not_run`; do not treat them as failures.

---

## Unavailable outcomes on read verbs (NOT errors)

`coverage show`/`diff`, `regression compare`/`latest`, `localization`,
and `inspect` return **exit 0, `ok: true`** even when the underlying
analysis can't be produced — unavailability is data, carried in the
outcome block's `kind: "unavailable"` with a `reason`:

```json
"coverage_outcome": {
  "kind": "unavailable",
  "reason": "missing-derived-facts",
  "detail": "No coverage_facts.json found for this run; call derive_coverage_facts first",
  "run_reference": { … }
}
```

Reason-string conventions differ by engine:

| Engine | Convention | Example reasons |
|---|---|---|
| coverage | hyphenated | `run-not-found`, `missing-native-payload`, `missing-derived-facts`, `native-payload-corrupt`, `incomparable-granularity` |
| regression | hyphenated | `run-not-found`, `run-tombstoned`, `no-comparable-baseline`, `missing-derived-facts`, `engine-mismatch`, `target-mismatch` |
| localization | underscored | `no_failed_tests`, `no_coverage`, `no_run_evidence`, `missing_derived_facts`, `run_not_analyzable` |

`coverage show` returning `missing-derived-facts` means the run was
produced without coverage — re-run with `novetest run --coverage` (or
`novetest test`, which always collects coverage) and read again. Note
**Go projects never produce coverage facts**: the go-test adapter writes
a profile under a key the coverage engine doesn't consume, so
`--coverage` on Go yields an `unavailable` coverage outcome.

`replay` is the exception to "unavailable = exit 0": its unavailable
reasons split by exit code — `engine-not-ready` / `target-missing` →
exit 4; `original-not-found` → exit 2; `tombstoned-original` /
`context-reconstruction-failed` / `missing-derived-facts` → exit 0.

---

## Warning codes (NOT errors)

`envelope.warnings[].code` never affects `ok` or the exit code. Log them
for observability:

| Code | Source | Meaning |
|---|---|---|
| `localization-cache-rederived` | localization | Cache invalidated + re-derived because explicit `--formula`/`--top-n` differed. Result is correct. |
| `localization-formula-noop-in-mode` | localization | `--formula` ignored because mode is `failure_proximity`. Drop the flag. |
| `ambiguous-build-tool` | junit | Both `pom.xml` and `build.gradle` present; Maven chosen. |
| `missing-jacoco` | junit | `--coverage` requested but JaCoCo not declared; coverage degraded. |
| `xunit-v3-coverage-deferred` | xunit | xUnit v3 detected; coverage deferred. |
| `ambiguous-project-layout` | xunit | Multiple candidate test projects. |
| `coverlet-below-floor` | xunit | Coverlet below the 6.0.2 floor; coverage degraded to aggregate mode. |
| `coverlet-absent` | xunit | `--coverage` requested but `coverlet.collector` not in the package graph; coverage not collected. |

---

## Idempotency and retry policy

| Verb | Idempotent? | Retry policy |
|---|---|---|
| `init` | Yes (no-op on existing store) | Retry safe. |
| `test` | Each call produces a new run | Retry produces a new `run_id`. |
| `run` | Each call produces a new run | Same as `test`. |
| `status` | Read-only | Retry safe. |
| `inspect` | Read-only | Retry safe. |
| `coverage show` / `diff` | Read-only | Retry safe. |
| `regression compare` | Cache-aware derive-or-read | Retry safe. |
| `regression latest` | Yes | Retry safe. |
| `localization` / `latest` | Cache-aware; warns on rederive | Retry safe; cache invalidated if flags differ. |
| `compare` | Read-only | Retry safe. |
| `replay` | Each call re-executes | Retry safe; each adds another rerun. |
| `memory list` / `show` | Read-only | Retry safe. |
| `memory delete` | Tombstone is atomic | Retry safe (re-tombstone is a no-op). |
| `reset --confirm` | Wipes + re-inits | **Destructive** — operator approval only. |
| `licenses` | Read-only | Retry safe. |

Nove Test does **no network I/O** at invocation time (only the install
script does, once).

---

## When to abort vs when to recover

| Situation | Action |
|---|---|
| Exit 0 / 3 | Success path — read the envelope (3 = tests failed, still `ok: true`). |
| Exit 2, `uninitialized` | Auto-recover: `init` then retry. |
| Exit 2, `not-found` | Auto-recover: `memory list` and pick. |
| Exit 2, `invalid-flag` | Auto-recover: fix the value. |
| Exit 2, `confirm-required` | Re-issue with `--confirm` ONLY with operator approval. |
| Exit 2, `adapter-invalid-target` | Auto-recover: fix the malformed target expression (drop the leading dash / flag / metacharacter). |
| Exit 5, `store-corrupt` / `store-wipe-failed` | Do NOT auto-recover. Surface (destructive recovery destroys data). |
| Exit 4, `engine-missing` / `engine-misconfigured` | Auto-recover IF policy permits installs (use `data.engine_readiness.issues[]`). Else surface. |
| Exit 4, `adapter-*` (except `adapter-invalid-target`, exit 2) | Surface (engine-level issue, not a Nove Test bug). |
| Exit 1, `cli-error` | Surface with the envelope. Do not retry blindly. |

---

## Health-check pattern

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
