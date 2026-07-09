# Troubleshooting (Human)

This page is organized by what you see on your terminal. Find the
shape that matches your problem, read the cause, apply the one-line fix.

In TEXT mode (the default on a terminal), a failed command renders a
generic error block, regardless of which verb produced it:

```
✗ <command>
  <code>: <human-readable message>
```

The first line names the failing command; the second gives the
machine-friendly error `code` (use it for searching docs / issues) and
a sentence describing what went wrong. To see the full structured
detail, re-run with `novetest --output json <verb>` and read
`errors[0]`.

> Examples on this page use the canonical `calc` project (a small
> Python package) and Nove Test **0.1.2**.

---

## Exit codes at a glance

Every command maps to one of six exit codes:

| Exit | Meaning |
|---|---|
| 0 | Success. |
| 1 | Generic / unexpected failure (e.g. an uncaught internal error). |
| 2 | Usage / validation: uninitialized store, bad argument, unknown `run_id`, bad flag, `reset` without `--confirm`. |
| 3 | **Your tests failed or errored.** The tool worked (`ok: true`); this is product information, not an error. |
| 4 | The engine could not run: no/insufficient native engine, or an adapter invocation error. |
| 5 | Project Store storage error (corrupt store, wipe failed). |

The important subtlety: **exit 3 is not a tooling error.** A failing —
or errored — test run still reports `ok: true`; failing tests are data,
and a suite that errored before producing results (e.g. a collection or
import error) is a recorded result too (`run_record.status: "errored"`).
Treat exit 3 the way you'd treat a failing `pytest` invocation — read
the recommendation block, fix the code or the test, re-run.

---

## Install issues

### "command not found: novetest"

The install script dropped the binary at `~/.local/bin/novetest`
(POSIX) or `%USERPROFILE%\.local\bin\novetest.exe` (Windows), but that
directory isn't on your PATH.

**Fix.** Add it to PATH:

```bash
# Linux / macOS — add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"
```

```powershell
# Windows — add to PowerShell profile
$env:PATH = "$HOME\.local\bin;$env:PATH"
```

Then `source` the profile (or open a new shell) and re-check with
`novetest --version` (it prints `novetest 0.1.2 (Python …)`).

### Install script aborts with "SHA-256 mismatch"

The install script downloads the binary plus its published `.sha256`
sidecar, computes the hash, and compares. On a mismatch it **aborts
loudly and writes nothing** — a real integrity guard. It means the
download was corrupted in flight, or the release artifacts are
inconsistent.

**Fix.**
1. Re-run the install script (most often it's a flaky network).
2. Still failing? Pin a specific version:
   `NOVETEST_INSTALL_VERSION=v0.1.2 curl … | sh`.
3. Still failing? File an issue with your OS / arch / network situation.

### "First run is slow" (5–15 seconds)

Expected. The binary is PyApp-wrapped: it bundles its own CPython and
unpacks the embedded interpreter once, on the first invocation per
binary version. Subsequent invocations are warm and fast.

### Windows: PowerShell script blocked

Your execution policy is blocking `install.ps1`.

**Fix.** Run with a bypass:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Or unblock the file first:

```powershell
Unblock-File install.ps1
.\install.ps1
```

### Supported platforms

The published binaries are: Linux x86_64, Linux aarch64, macOS
universal2 (one fat binary covering Intel + Apple Silicon), and Windows
x86_64. There is **no Windows arm64** build.

---

## `init` issues

### `✗ init  store-corrupt: …`

`.novetest/store.json` exists but is unreadable or malformed (exit 5).

**Fix.** Inspect the file to see if you can salvage it. If not (or if
you don't care about run history):

```bash
rm -rf .novetest
novetest init
```

That wipes all stored runs for this project. Your source code and
tests are untouched.

### `✗ init  no-engine-detected: …` (exit 4)

No workspace marker at the directory you ran `init` in. Nothing was
created. The message lists candidate sub-projects found by a bounded
scan (depth ≤ 2) — `cd` into the one you meant and run `init` there.
At `/` or `$HOME` the scan itself is refused.

### `✗ init  engine-ambiguous: …` (exit 2)

Two or more viable engines at this directory (e.g. `pyproject.toml` +
`Cargo.toml`, both toolchains installed). Nothing was created — choose
explicitly:

```bash
novetest init --engine pytest    # or cargo-test, jest, go-test, junit, xunit
```

The same error from a non-`init` verb means a pre-pin store at an
ambiguous root: re-run `init --engine <name>` (re-pins in place; run
history kept).

### `✓ Initialized .novetest/ …` but `engine readiness: engine-missing`

`init` always succeeds and always leads with `✓` — it never fails on a
missing engine. But the readiness line tells you it couldn't find a
usable test engine:

```
✓ Initialized .novetest/ at /path/to/calc-demo/.novetest
  engine readiness: engine-missing — no engine detected
  issue: Python workspace detected but no pytest configuration (pytest.ini, [tool.pytest.ini_options], conftest.py, or tests/ dir) found
```

(That `issue:` line is for a Python project that has a `pyproject.toml`
but no pytest config; a directory with no recognized markers at all
instead reports `issue: no supported (ecosystem, native engine) pair
detected in workspace`. A healthy project shows `engine readiness: ready
— python/pytest 9.0.3`.)

**Fix.** The `issue:` line(s) carry the real, engine-specific reason.
Common cases and the toolchain that satisfies them:

| Engine | Typical issue | Fix |
|---|---|---|
| pytest | "no pytest configuration … found" | Add a `tests/` dir / `[tool.pytest.ini_options]` / `pytest.ini` / `conftest.py`; install pytest + `pytest-json-report`. |
| jest | "Node.js (`node`/`npx`) not found on PATH" | Install Node.js ≥ 18, then `npm install --save-dev jest` in the project root. |
| go-test | go not on PATH | Install Go ≥ 1.21 from <https://go.dev/dl/>. |
| cargo-test | "`cargo nextest` is not installed" | `cargo install cargo-nextest --locked` (nextest is **required** — there is no plain `cargo test` fallback). |
| junit | "`java` not found on PATH" | Install JDK 17+ and Maven 3.9+ or Gradle 7.6+. JUnit 5 Jupiter only (JUnit 4 / TestNG are rejected). |
| xunit | dotnet not on PATH | Install .NET SDK 8.0+ and add `xunit` (v2) to your test project. MSTest / NUnit are rejected. |

Re-run `novetest init` after fixing.

> Readiness states are exactly three: `ready`, `engine-missing`, and
> `engine-misconfigured`. There is no `engine-not-ready` readiness
> state. `engine-missing` means no engine applies (or its binary is
> absent); `engine-misconfigured` means the engine applies but required
> tooling is missing (plugin, nextest, JDK, etc.).

---

## `test` / `run` issues

### `✗ run  engine-missing: …` (exit 4)

```
✗ run
  engine-missing: engine readiness state: engine-missing (engine=(none detected))
```

No usable native engine. The error `code` is the readiness state
verbatim — `engine-missing` (the code IS the state, with no extra
prefix). The same shape applies to `novetest test`.

**Fix.** Run `novetest init` (or just re-run the verb — `test`/`run`
re-probe readiness each time) and read the readiness `issue:` lines, or
re-run with `--output json` and read `data.engine_readiness.issues[]`.
Then install/configure the engine per the table above. Note the fix
hints live in `data.engine_readiness.issues[]`, not in the error
object's `details` (which is empty).

If the engine **is** on PATH but Nove Test still doesn't see it:

1. **Wrong interpreter (pytest).** Nove Test runs pytest with its own
   bundled interpreter (`<python> -m pytest …`), not a `pytest` on PATH.
   A globally-installed pytest that this interpreter can't import reads
   as `engine-misconfigured`. The readiness `issue:` line will say
   `install with: pip install pytest` (or `… pytest-json-report`).
2. **Wrong project.** Confirm you're in the right directory.

### `✗ run  engine-misconfigured: …` (exit 4)

The engine applies but a required piece is missing — pytest /
`pytest-json-report` not importable, nextest not installed, JDK
missing, JUnit 4 / TestNG / MSTest / NUnit detected (unsupported), etc.
The readiness `issue:` line names the exact install command.

### `✗ test  adapter-…: …` (exit 4)

The engine started but failed before producing parseable results — a
build failure, missing plugin, or a tool the adapter shells out to
exiting non-zero. The code is `adapter-<kind>`, e.g.
`adapter-unparseable-output`, `adapter-missing-plugin`,
`adapter-missing-binary`, `adapter-timed-out`. The message includes the
engine's own stderr tail. (`adapter-invalid-target` is the exception — a
malformed target, not an engine failure; it exits **2**, see below.)

**Fix.** Read the stderr tail in the message — the underlying problem is
at the engine level (your build, your dependencies), not in Nove Test.
Fix it and re-run.

> Tip: an unknown token like `novetest frobnicate` is **not** "command
> not found". The first non-verb token is treated as a test selector
> (`novetest test frobnicate`), so the engine tries to run it as a test
> path and fails with an adapter error.

### `✗ test  adapter-invalid-target: …` (exit 2)

The target you passed was rejected **before launch** — a dash-/flag-/
metacharacter-shaped target that would be swallowed as an engine flag or
shell metacharacter, e.g. `novetest run -- --pdb`. The code is still
`adapter-invalid-target`, but this is a **usage error** (a malformed
argument), so it exits **2**, not exit 4 like the engine-level adapter
failures above.

**Fix.** Correct the **target expression** — drop the leading dash /
flag / metacharacter — and re-run. The problem is your argument, not the
engine or your build.

### An explicit target that matches nothing reports `passed` with 0 tests

`novetest run path/that/matches/nothing.py` currently yields
`collected: 0, total: 0, status: passed`, exit 0. If you pass an
explicit target, check the collected count before trusting a green
result — a typo'd or non-anchor-relative path "passes" without running
anything.

### Exit code 3 (tests failed or errored) — NOT an error

Your tests actually failed — or the suite errored before it could
produce results (`ok: true`, exit 3; `run_record.status` is `failed`
vs `errored`). The recommendation block on stdout names which locations
to investigate, e.g.:

```
5 recommendations · 1 category · run_id=…

  ! [investigate_location] Investigate `subtract`@6 in `calc/arithmetic.py` (rank 1, ochiai=1.000, sbfl_per_test).
```

Fix the code or the test, then re-run.

### `✗ <verb>  not-found: …` (exit 2)

You passed a `run_id` (to `inspect`, `coverage show`, `regression
compare`, `localization`, `replay`, `memory show`, `memory delete`, …)
that doesn't exist:

```
✗ coverage.show
  not-found: No Memory Entry for run_id='FAKE123'
```

**Fix.** List the real IDs and copy one:

```bash
novetest memory list
```

Run IDs are 26-char ULIDs (e.g. `01KVYRRRN9FWVNQWVHNE1QHAQ4`); partial
matches are not accepted.

---

## Coverage issues

### `— unavailable (missing-derived-facts)`

```
✓ per-test · 13/13 statements (100.0%) · run_id=…   ← healthy
— unavailable (missing-derived-facts)               ← no coverage recorded
```

`coverage show` is a cache read — it never derives on demand. If the
run was produced by `novetest run` **without** `--coverage`, no
coverage facts were recorded.

**Fix.** Re-run with coverage, then look again:

```bash
novetest run --coverage          # -c is the short form
# or just:
novetest test                    # `test` ALWAYS collects coverage
```

`novetest test` has no `--coverage` flag because it always collects
coverage. Only `novetest run` takes `--coverage` / `-c`.

### Go projects never produce coverage facts

This is a known limitation: the go-test adapter runs your tests and
writes a coverage profile, but the coverage engine does not consume it.
`novetest run --coverage` on a Go project yields a coverage outcome of
`unavailable`. Test execution works; coverage facts do not. The other
five engines (pytest, jest, cargo-test, junit, xunit) produce coverage
facts.

---

## `localization` issues

### `— unavailable (no_failed_tests)`

Expected on a green run — SBFL has nothing to rank when no test failed.
(Localization reason strings use underscores, unlike coverage's
hyphens.)

**Fix.** None needed; this is the correct outcome.

### `— unavailable (missing_derived_facts)`

The run lacks the per-test data SBFL needs (most commonly: coverage was
unavailable, so per-test attribution is missing).

**Fix.** Make sure coverage is being collected (`novetest test`, or
`novetest run --coverage`), then re-run `novetest localization <run_id>`.

### `✗ localization  invalid-flag: …` (exit 2)

```
✗ localization
  invalid-flag: Invalid --formula='nope'; expected one of ['dstar2', 'ochiai', 'op2', 'tarantula']
```

**Fix.** Pick a value from the listed set. The valid formulas are
`ochiai` (default), `op2`, `dstar2` (note: `dstar2`, not `dstar`), and
`tarantula`. Likewise `--top-n` must be a positive integer
(`Invalid --top-n=0; expected a positive integer`); the default is 10.

### `⚠ localization-cache-rederived`

You re-invoked `novetest localization` with a `--formula`/`--top-n`
that differs from what was cached. The CLI invalidated the cache,
re-derived at your requested values, and surfaced this warning. The
result is correct; the warning is informational.

### `⚠ localization-formula-noop-in-mode`

You passed `--formula` but the SBFL mode is `failure_proximity`, which
pins `ochiai` as a placeholder and ignores the formula. The flag had no
effect.

**Fix.** Drop `--formula` in this mode, or accept the warning.

---

## `reset` issues

### `✗ reset  confirm-required: …` (exit 2)

```
✗ reset
  confirm-required: `novetest reset` is destructive. Pass --confirm to acknowledge.
```

`reset` hard-wipes the store. It refuses to run without explicit
acknowledgement.

**Fix.** Re-run with `--confirm`:

```bash
novetest reset --confirm
```

This wipes all runs/findings and re-initializes the store:

```
✓ Reset .novetest/ at /path/to/.novetest
  removed: nothing
  engine readiness: ready — python/pytest 9.0.3
```

(`reset --confirm` is the only hard wipe. `memory delete <run_id>`
merely **tombstones** a run — it still appears in `memory list`/`memory
show` with a `tombstoned_at` timestamp.)

---

## `replay` issues

`replay` actually re-executes the run, so it can hit engine problems.
A healthy replay reads `✓ reproducible · 1/1 · run_id=…`. Unavailable
replays render `? unavailable (<reason>)`.

### `? unavailable (engine-not-ready)` / `? unavailable (target-missing)` (exit 4)

The engine binary isn't available anymore, or the original target no
longer exists.

**Fix.** Same as `engine-missing`: install / configure the engine, or
restore the target, then retry.

### `? unavailable (missing-derived-facts)` (exit 0)

Not enough recorded evidence to replay this run. This is data, not a
tool error (exit 0).

### Tuning a replay

```bash
novetest replay <run_id> --reruns 3 --timeout 1200
```

`--reruns` defaults to 1, `--timeout` to 600.0 seconds.

> `inspect`'s `replay  ? unavailable (missing-derived-facts)` line is
> expected: `inspect` is a pure read and never executes a replay. Run
> `novetest replay <run_id>` to actually replay.

---

## Output-mode issues

### "I see JSON everywhere, not pretty text"

TEXT mode is used only when stdout is a real terminal. Anything piped or
redirected defaults to JSON. You're either:

1. Piping (`novetest test | less`) → JSON is the default for non-TTY.
   Force text with `novetest --output text test`.
2. Have `NOVETEST_OUTPUT=json` exported → `unset NOVETEST_OUTPUT`.

Precedence is `--output` > `NOVETEST_OUTPUT` > TTY autodetect.

### "My CI logs are full of pretty JSON; I want one line per envelope"

Use NDJSON (one compact line per envelope):

```bash
NOVETEST_OUTPUT=ndjson novetest test
```

### `--output bogus` prints a Python traceback

An invalid `--output` value (or `NOVETEST_OUTPUT`) is rejected before
the envelope machinery starts, so you get a raw traceback and exit 1 —
not a clean error envelope. Use only `text`, `json`, or `ndjson`.

### "I expected color"

There is no ANSI color. The glyph palette
(`✓ ✗ — ⚠ ! ? · ↳`) carries the meaning instead.

---

## Project Store issues

### `✗ <verb>  store-corrupt: …` (exit 5)

`.novetest/store.json` is unreadable or malformed.

**Fix.** Worst case:

```bash
rm -rf .novetest
novetest init
```

You lose run history but recover the store.

### `✗ reset  store-wipe-failed: …` (exit 5)

A filesystem error (e.g. permissions) interrupted the wipe.

**Fix.** Check directory permissions on `.novetest/`, then retry, or
`rm -rf .novetest && novetest init`.

### "How do I share run history with my team?"

Commit `.novetest/` to git — the tree is plain JSON and diffs cleanly.
Most teams choose NOT to (history is large and per-developer); it's the
right answer only when you want a single team-shared baseline.

### "How do I clean up old runs?"

Tombstone individual runs:

```bash
novetest memory delete <run_id>
```

Or wipe the whole store:

```bash
novetest reset --confirm
# or
rm -rf .novetest && novetest init
```

---

## When all else fails

1. `novetest --version` to confirm the binary is sane.
2. `novetest --help` to confirm the verb you're trying exists.
3. `novetest status` (after `init`) to see what's actually stored.
4. Re-run the failing verb with `novetest --output json <verb>` to see
   the full envelope; `errors[0]` usually carries more detail than the
   text-mode `<code>: <message>` line.
5. Search the issue tracker:
   <https://github.com/Nove-Lab/Nove-Test/issues>
6. File a new issue with the JSON envelope output and your OS / engine
   versions.

---

## What to read next

- The exit-code → meaning table → [after-test.md §exit-codes](./after-test.md#exit-codes).
- Per-engine setup → [languages.md](./languages.md).
- Deeper verbs → [advanced.md](./advanced.md).
