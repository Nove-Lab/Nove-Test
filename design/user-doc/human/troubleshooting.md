# Troubleshooting (Human)

This page is organized by what you see on your terminal. Find the
shape that matches your problem, read the one-line fix.

Most error envelopes in text mode look like:

```
✗ <verb>
  <code>: <human-readable message>
  <optional hint>
```

The first line tells you which verb failed; the second tells you the
machine-friendly error code (use this for searching docs / issues) and
a sentence describing what went wrong; the optional third line is
typically a one-line install hint.

---

## Install issues

### "command not found: novetest"

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

### Install script aborts with "SHA-256 mismatch"

This is the install script's loud-abort guard. It means the binary's
hash did not match the published `.sha256` sidecar — either the
download was corrupted in flight, or the release artifacts are
inconsistent.

**Fix.**
1. Re-run the install script (the most common cause is a flaky network).
2. If it still fails, pin a specific version: `NOVETEST_INSTALL_VERSION=v0.1.2 curl ... | sh`.
3. If THAT still fails, file an issue with your OS / arch / network situation.

### "First run is slow" (5-25 seconds)

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

### `✗ init  store-corrupt: ...`

`.novetest/store.json` exists but is unreadable or malformed.

**Fix.** Inspect the file to see if you can salvage it. If not (or if
you don't care about run history):

```bash
rm -rf .novetest
novetest init
```

That wipes all stored runs for this project. Your source code and
tests are untouched.

### `✓ Initialized .novetest/ ...` but `engine readiness: engine-missing`

`init` succeeded, but it could not find your test engine on PATH.

**Fix.** The `issue:` lines after the readiness line tell you what's
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

### `✗ init  uninitialized: ...` running a non-`init` verb

You ran `novetest test` (or any other operating verb) from a
directory whose tree contains no `.novetest/`.

**Fix.** `cd` into your project root (or any subdirectory of it after
running `novetest init` there once), then re-run the verb.

---

## `test` / `run` issues

### `✗ test  engine-missing: ...`

Native test engine not on PATH. Same fix as the `engine-missing`
readiness above.

If you have an engine on PATH but Nove Test still doesn't see it, two
common causes:

1. **Wrong shell.** `novetest` is using `/bin/sh`-like resolution — if
   you installed pytest only inside a Python venv that you haven't
   activated, Nove Test cannot see it.
2. **Wrong project.** Make sure you're in the right directory.
   `novetest init` records which engine was detected; `novetest test`
   from a fresh `.novetest/` re-probes.

### Exit code 3 (tests failed) — NOT an error

This is product information, not a tooling problem. Your tests
actually failed. The recommendation block on stdout names which tests
and points you at where to look.

Treat this the same way you'd treat a failing `pytest` invocation —
fix the code or the test, re-run.

### `✗ test  not-found: ...`

You passed a `run_id` (to `inspect`, `coverage show`, `replay`, …)
that doesn't exist in the store.

**Fix.** List available IDs:

```bash
novetest memory list
```

Copy a real ULID from there. ULIDs are 26 chars; partial matches are
not accepted.

### `⚠ engine-misconfigured` warning

Adapter found the engine but flagged missing optional pieces. Common
case: `pytest-cov` not installed.

**Fix.** Install the missing piece (e.g. `pip install pytest-cov`).
Coverage will become `✓ available` on the next run. Until then, the
warning is informational only.

---

## `localization` issues

### `— unavailable (no_failed_tests)`

Expected on green runs. SBFL has nothing to rank when no test failed.

**Fix.** None needed; this is the correct outcome.

### `— unavailable (missing-derived-facts)`

The run completed without recording the per-test data SBFL needs (most
commonly: coverage was unavailable, so per-test coverage attribution
is missing).

**Fix.** Install your engine's coverage tool (e.g. `pytest-cov` for
pytest), then re-run `novetest test`.

### `⚠ localization-cache-rederived`

You re-invoked `novetest localization` with a different `--formula`
than what was cached. The CLI rewrote the cache. This is informational
only.

### `⚠ localization-formula-noop-in-mode`

You passed `--formula` but the chosen SBFL mode is
`failure_proximity`, which doesn't use a formula. The flag was ignored.

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

NOT an error. This is the actual product output telling you the test
result is flaky. The corresponding `flaky_suspect` recommendation in
the next `novetest test` will point you at the unstable tests.

---

## Output-mode issues

### "I see JSON everywhere, not pretty text"

You're either:

1. Piping (`novetest test | less`) → JSON is the default for pipes. Use `--output text` to force text.
2. Have `NOVETEST_OUTPUT=json` exported. Run `unset NOVETEST_OUTPUT` to release the override.

### "My CI logs are full of pretty JSON; I want one line per envelope"

Use NDJSON:

```bash
NOVETEST_OUTPUT=ndjson novetest test
```

Each envelope becomes a single line.

### "I expected color"

There is no ANSI color at MVP. The 7-glyph palette
(`✓ ✗ — ⚠ ! ? · ↳`) carries meaning instead. Color is queued for
post-MVP.

---

## Project Store issues

### `✗ <verb>  store-corrupt: ...`

`.novetest/store.json` is unreadable or malformed.

**Fix.** Worst case:

```bash
rm -rf .novetest
novetest init
```

You lose run history but recover the store.

### "How do I share run history with my team?"

Commit `.novetest/` to git. The whole tree is plain JSON files; it
diffs cleanly. Most teams choose NOT to do this (the history is large
and per-developer); it's the right answer only when you want a single
team-shared baseline.

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

- The exit-code → meaning table → [after-test.md §exit-codes](./after-test.md#exit-codes).
- Per-engine setup → [languages.md](./languages.md).
- Deeper verbs → [advanced.md](./advanced.md).
