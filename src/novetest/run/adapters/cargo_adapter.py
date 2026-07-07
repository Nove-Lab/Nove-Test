"""``cargo nextest`` Native Engine adapter.

Phase 3 adapter backlog slice #2. Fourth Native Engine to land (after
pytest, jest, go-test). Ships nextest-only per the
``decisions/2026-05-29-cargo-adapter-nextest-primary.md`` Q3 resolution
— no plain-text ``cargo test`` fallback, no nightly
``-Z unstable-options`` JSON path. Users without ``cargo-nextest`` get a
clear ``engine-misconfigured`` state with an install hint, surfaced by
``readiness._assess_cargo_readiness`` BEFORE this adapter is spawned.

Foundations parity with pytest_adapter / jest_adapter / gotest_adapter:

- ``cwd`` is required and must be the workspace root containing
  ``Cargo.toml``.
- All native artifacts (``events.jsonl``, ``stdout.log``, ``stderr.log``,
  optional ``coverage.lcov``, per-test failure logs) land under
  ``<artifact_dir>/native/``. The orchestration layer rewrites those
  absolute paths to Project-Store-relative strings before persisting the
  Run Record.
- ``collect_coverage=True`` swaps the execution path from
  ``cargo nextest run`` to ``cargo llvm-cov nextest --lcov`` (the two
  paths are MUTUALLY EXCLUSIVE per invocation — cargo-llvm-cov wraps
  nextest internally; running both would conflict over instrumentation).
  The resulting LCOV file registers under the artifact key
  ``coverage_lcov`` — distinct from go-test's ``coverage_profile`` and
  pytest/jest's ``coverage_json`` so the Coverage engine can dispatch on
  ``engine_name == "cargo-test"`` later.

Per-test failure logs are written **here**, not in the normalizer. The
adapter is the only layer that holds ``artifact_dir``; the normalizer
just consumes a payload-resident map of ``"<name>" → "<relative path>"``
strings. The coupling on the libtest-json ``name`` field as the lookup
key is documented in both files.

libtest-json schema (nextest 0.9.50+ — stable on stable Rust):

- ``{"type":"suite","event":"started", ...}`` — once per test binary.
- ``{"type":"test","event":"started","name":"<crate>::<path>"}``
- ``{"type":"test","event":"ok"|"failed"|"ignored","name":"...",
  "stdout":"<panic + backtrace>","stderr":"<...>"}``
- ``{"type":"suite","event":"ok"|"failed",...}``

The ``name`` field includes the binary path prefix in nextest mode (e.g.
``cargo_test_basic::tests::test_add`` for a unit test or
``integration_test::test_x`` for a binary in ``tests/``), so it serves
directly as the ``node_id``. ``binary`` fields, when present at
suite-level events, are collected into ``payload["binaries"]`` for
informational use.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from novetest.run.adapters._target_guard import reject_dash_leading_target
from novetest.run.errors import AdapterInvocationError
from novetest.run.types import NativeResult, TestTarget
from novetest.utils.asyncio_subprocess import run_subprocess


EVENTS_JSONL_FILENAME = "events.jsonl"
STDOUT_LOG_FILENAME = "stdout.log"
STDERR_LOG_FILENAME = "stderr.log"
COVERAGE_LCOV_FILENAME = "coverage.lcov"
FAILURES_DIR_NAME = "failures"

# The runtime env-var literal `cargo-nextest` ≥ 0.9.50 emits in its
# stderr when ``--message-format=libtest-json`` was requested without
# ``NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1``. The 2026-05-31 hotfix
# (`_build_child_env`) sets this env var unconditionally so the symptom
# is not reachable in normal operation — but if a parent process /
# shell strips it, or a future nextest version renames the gate, the
# adapter surfaces a specific ``misconfigured-environment`` error
# instead of the generic ``unparseable-output``. The generic kind would
# mislead AI consumers and humans into root-causing this as a compile
# failure. Detection is substring-only on the env-var name (not the
# full upstream error sentence) so benign upstream wording tweaks do
# not break the heuristic; the env-var name itself is the load-bearing
# token nextest will keep printing as long as the gate is named that.
_NEXTEST_LIBTEST_JSON_ENV_LITERAL = "NEXTEST_EXPERIMENTAL_LIBTEST_JSON"

# The no-tests-match stderr signature `cargo-nextest` ≥ 0.9.50 emits
# when its filter expression resolves to zero tests across all binaries
# (exit code 4; distinct from compile failures which exit 101). The two
# literals together form the binding signature: ``Starting 0 tests
# across`` (the per-binary count line) AND ``error: no tests to run``
# (the trailing diagnostic). Both must be present for the carve-out to
# fire — the count line alone could appear in pathological
# "compiled-but-zero-`#[test]`-items" scenarios where the more accurate
# diagnosis is build-adjacent ("the user's fixture is empty"); the
# conjunction excludes that case because nextest only emits the second
# literal on filter mismatch, not on empty binaries. Recognizing this
# pair surfaces a distinct message before the generic ``likely build
# failure`` branch so users get accurate root-cause guidance — stderr
# clearly shows ``Finished test profile … target(s)`` earlier in the
# run when the build actually succeeded. See
# ``agent-comms/findings/manual-test-team-2026-06-04-host-equip.md``
# §"Cargo adapter — CLI vs adapter-direct discrepancy" for the
# verbatim stderr capture this heuristic recognizes.
_NEXTEST_NO_TESTS_LITERAL = "Starting 0 tests across"
_NEXTEST_NO_TESTS_ERROR_LITERAL = "error: no tests to run"


def _libtest_json_env_misconfigured_error(
    *, mode: str, returncode: int, stderr_tail: str
) -> AdapterInvocationError:
    """Build the ``misconfigured-environment`` error raised when
    nextest's stderr signals the libtest-json gate env var was not
    honored.

    ``mode`` is either ``"nextest"`` (plain run) or
    ``"llvm-cov nextest"`` (coverage run) — embedded as the spawn-path
    identifier in the message so AI consumers and humans can tell
    which path produced the failure. Both call sites use the same
    diagnosis prose so the symptom-to-action mapping stays consistent
    across the two branches. Single helper, two callers — duplicated
    f-strings would have drifted on the next polish pass.
    """

    return AdapterInvocationError(
        f"cargo {mode} exited {returncode} signaling that "
        f"NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 was not honored; the "
        f"adapter sets this env var in _build_child_env() — check that "
        f"the parent process or shell hasn't pre-unset it, and that a "
        f"future nextest version hasn't renamed the gate. stderr tail: "
        f"{stderr_tail}",
        kind="misconfigured-environment",
    )


async def run_cargo(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,
) -> NativeResult:
    """Run ``cargo nextest run`` (or ``cargo llvm-cov nextest``) against
    ``test_target`` and return the parsed Native Result.

    ``artifact_dir`` is the per-run directory under
    ``.novetest/run/artifacts/run_<ulid>/`` where ``native/`` is created;
    in tests, pass a ``tmp_path``-rooted directory.

    When ``collect_coverage`` is True, the execution path swaps to
    ``cargo llvm-cov nextest --lcov --output-path=<...>/coverage.lcov``.
    Nextest's libtest-json output stream is requested in both modes so
    test-result fidelity is preserved during coverage runs. The resulting
    LCOV file registers under the artifact key ``coverage_lcov``.
    """

    # Defensive resolve: hardens against future callers passing a relative
    # ``artifact_dir``. See pytest_adapter.py for the full rationale.
    # Idempotent on absolute paths.
    artifact_dir = artifact_dir.resolve()

    native_dir = artifact_dir / "native"
    native_dir.mkdir(parents=True, exist_ok=True)
    events_path = native_dir / EVENTS_JSONL_FILENAME
    stdout_path = native_dir / STDOUT_LOG_FILENAME
    stderr_path = native_dir / STDERR_LOG_FILENAME
    coverage_path = native_dir / COVERAGE_LCOV_FILENAME
    failures_dir = native_dir / FAILURES_DIR_NAME

    # Resolve `cargo` up-front. Per Q3 decision §1, the floor is
    # `cargo-nextest >= 0.9.50` — the install hint specifically calls
    # that out so the user can map the error to the missing crate.
    cargo_path = shutil.which("cargo")
    if cargo_path is None:
        raise AdapterInvocationError(
            "`cargo` not found on PATH; install Rust toolchain from https://rustup.rs",
            kind="missing-binary",
            install_hint="install Rust toolchain from https://rustup.rs",
        )

    # `target_expression` is plumbed through verbatim. Empty means "no
    # filter" — `--workspace` (added below) makes nextest walk every
    # crate in the workspace. Users can pass a nextest filter expression
    # (e.g. `tests::add` or `package(foo)`) for narrower runs.
    #
    # RUN-22 guard: a dash-leading value would be consumed by nextest's
    # own parser (`-p X` becomes a `--package` selector). The frozen
    # wave-1 `--` prescription is WRONG for nextest — args after `--` are
    # TEST-BINARY args, and the libtest emulation set is still consumed
    # as flags (`cargo nextest run -- --ignored` silently flips selection
    # to ignored-only; verified on nextest 0.9.137, 2026-07-07) — so the
    # adapter rejects instead.
    reject_dash_leading_target(
        test_target.target_expression, engine_label="cargo-nextest"
    )
    target_expression = test_target.target_expression

    # Coverage-mode and execution-mode are MUTUALLY EXCLUSIVE per
    # `engine-adapters.md §5` + Q3 decision §"What this decision does
    # NOT decide". `cargo-llvm-cov` wraps nextest internally; running
    # both would produce conflicting LLVM-instrumented invocations.
    argv: list[str]
    if collect_coverage:
        # `cargo llvm-cov nextest` forwards nextest args; including
        # `--message-format=libtest-json` keeps per-test result fidelity
        # during coverage runs (unlike Go where coverage just augments
        # the same `-json` invocation, Rust's coverage path requires the
        # llvm-cov wrapper).
        #
        # `--ignore-run-fail` (NOT `--no-fail-fast`) is the load-bearing
        # flag here. The two are mutually exclusive on cargo-llvm-cov's
        # CLI; `--no-fail-fast` runs every test but tells cargo-llvm-cov
        # to surface nextest's non-zero exit (any failing test → exit
        # 100) as the wrapper's own failure, which suppresses the LCOV
        # report. `--ignore-run-fail` also runs every test (it implies
        # `--no-fail-fast` internally — verify via stderr trace: cargo-
        # llvm-cov passes `--no-fail-fast` to the inner cargo-nextest
        # invocation regardless), BUT also commits to emitting the LCOV
        # report even when nextest exits non-zero. That is exactly the
        # behavior we need: a Localization / Coverage consumer of a
        # failing run wants to see what code the failing tests touched.
        # Empirical proof in
        # `agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`
        # §Defect 1: pre-fix `lcov written: NO`; post-fix `lcov written:
        # YES (1710 bytes)` on the `localization-aggregate-only`
        # fixture. Plain cargo-nextest (the non-coverage path below)
        # does NOT accept `--ignore-run-fail` — it is a cargo-llvm-cov-
        # only flag — so the swap is confined to this branch.
        argv = [
            cargo_path,
            "llvm-cov",
            "nextest",
            "--lcov",
            "--output-path",
            str(coverage_path),
            "--ignore-run-fail",
            "--workspace",
            "--message-format=libtest-json",
        ]
    else:
        # `--no-fail-fast` keeps nextest running after the first failure
        # so the Run Record captures every test outcome — matches the
        # `pytest --maxfail=1` opt-out posture (default is no
        # short-circuit). The cargo-llvm-cov-specific
        # `--ignore-run-fail` (used in the coverage branch above) is
        # NOT applicable here: it is a wrapper-level flag that plain
        # cargo-nextest rejects.
        argv = [
            cargo_path,
            "nextest",
            "run",
            "--message-format=libtest-json",
            "--no-fail-fast",
            "--workspace",
        ]

    # Fix A (2026-06-05 cargo CLI orchestration defect):
    # ``cargo nextest`` does NOT take filesystem-directory arguments as
    # positional filters. The positional argument is interpreted as a
    # **filter DSL expression** (e.g. ``tests::add`` or
    # ``package(foo)``). When ``target_resolver`` classifies the user's
    # input as ``target_type="directory"`` (the common ``novetest run .``
    # case, where ``workspace_context / "."`` exists as a directory), the
    # literal ``"."`` becomes a filter DSL token that matches a test
    # whose ID equals ``"."`` — nextest finds no such test and exits 4
    # with "no tests to run". Suppress the append for directory targets:
    # ``--workspace`` already covers the workspace root, which matches
    # the user's intent for ``novetest run .`` (identical to
    # ``novetest run`` bare). Sub-crate directory selection (e.g.
    # ``novetest run crates/foo/``) would need translation to nextest's
    # expression DSL (``-E 'package(foo)'``) or cargo's ``-p`` selector;
    # that is deferred until a user requests it. Documented in
    # ``design/implementation-plan/engine-adapters.md §5``. Non-directory
    # target types (``workspace``, ``nodeid``, ``file``) keep the
    # verbatim append: ``workspace`` produces an empty expression and
    # falls out at the truthiness check; ``nodeid`` carries a
    # ``crate::path::test`` form that nextest accepts directly;
    # ``file`` is a free-form string the user opted into and the engine
    # surfaces its own error on mismatch — parity with the pre-fix
    # contract for those three types.
    if target_expression and test_target.target_type != "directory":
        argv.append(target_expression)

    env = _build_child_env()
    started_ms = int(time.time() * 1000)
    try:
        result = await run_subprocess(
            argv,
            cwd=test_target.workspace_path,
            env=env,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        # TOCTOU fallback — `cargo` was resolved above but removed
        # between resolution and exec. Surface as typed error.
        raise AdapterInvocationError(
            "the `cargo` launcher could not be executed; install Rust toolchain "
            "from https://rustup.rs",
            kind="missing-binary",
            install_hint="install Rust toolchain from https://rustup.rs",
        ) from exc
    completed_ms = int(time.time() * 1000)

    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)

    if result.timed_out:
        raise AdapterInvocationError(
            f"cargo nextest exceeded {timeout}s timeout",
            kind="timed-out",
        )

    # Stream-parse stdout line by line. libtest-json emits NDJSON; never
    # parse the buffer as a single JSON document. We read bytes after
    # the process exits because `run_subprocess` captures eagerly —
    # this is not "true" streaming but preserves the *parser* contract:
    # a malformed line never aborts the rest. Defensive-parsing posture
    # per `decisions/2026-05-25-supported-engine-matrix.md` §2.
    events: list[dict[str, Any]] = []
    binaries_seen: set[str] = set()
    saw_test_started = False
    # Per-test stdout/stderr buffers keyed on the libtest-json `name`
    # field. Only failing tests' buffers are written to disk.
    output_buffers: dict[str, list[str]] = {}
    failure_logs: dict[str, str] = {}  # "<name>" → relative path

    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # libtest-json is stable but the defensive-parsing decision
            # of 2026-05-25 requires us to tolerate drift gracefully —
            # skip malformed lines, do not abort.
            continue
        if not isinstance(event, dict):
            continue
        events.append(event)

        ev_type = event.get("type")
        ev_event = event.get("event")
        name = event.get("name")

        # Collect binary names from both suite-level and test-level
        # events. Standard libtest-json doesn't carry `binary` at the
        # test level; nextest's `libtest-json-plus` extension does. We
        # accept either — purely informational metadata.
        for candidate_event in (event,):
            binary = candidate_event.get("binary")
            if isinstance(binary, str) and binary:
                binaries_seen.add(binary)

        if ev_type != "test":
            continue
        if ev_event == "started":
            # The "started" event marks build success: at least one test
            # binary compiled and the suite started executing. We track
            # this separately for the build-failure discriminant below.
            saw_test_started = True
            continue
        if not isinstance(name, str) or not name:
            continue

        # Per-test output capture. libtest-json carries `stdout` and
        # `stderr` strings on terminal events for failing tests; concat
        # both into a single failure log per the brief.
        for stream_field in ("stdout", "stderr"):
            stream_text = event.get(stream_field)
            if isinstance(stream_text, str) and stream_text:
                output_buffers.setdefault(name, []).append(stream_text)

        if ev_event == "failed":
            buffer = output_buffers.get(name, [])
            safe_name = _safe_failure_log_name(name)
            failures_dir.mkdir(parents=True, exist_ok=True)
            failure_path = failures_dir / f"{safe_name}.log"
            failure_path.write_text("".join(buffer), encoding="utf-8")
            failure_logs[name] = str(failure_path.relative_to(artifact_dir))

    # Build-failure detection.
    #
    # cargo can fail to compile before any test runs. Detection: "no
    # `started` event for any test AND non-zero returncode" → typed
    # `unparseable-output`. Skip in coverage mode: `cargo llvm-cov` may
    # consume stdout for its own bookkeeping in some versions, leaving
    # us with no parseable events even on successful runs. The
    # `coverage_path` existence check below catches actual coverage
    # failures more reliably in that mode.
    if not collect_coverage and not saw_test_started and result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        stdout_text = result.stdout.decode("utf-8", errors="replace")
        detail_source = stderr_text if stderr_text else stdout_text
        # The env-var-missing case is a more specific cause than a
        # generic build failure — check the literal in stderr first so
        # the typed error guides root-cause analysis to the right
        # spot. Falls through to the generic ``unparseable-output``
        # branch for true compile errors, which never reference the
        # env-var name.
        if _NEXTEST_LIBTEST_JSON_ENV_LITERAL in stderr_text:
            raise _libtest_json_env_misconfigured_error(
                mode="nextest",
                returncode=result.returncode,
                stderr_tail=detail_source[-400:],
            )
        # Fix B (2026-06-05 cargo CLI orchestration defect):
        # Distinguish nextest's "filter matched zero tests" exit (which
        # is exit 4 and stderr-signaled with the conjunction of the
        # two literals below) from a true compile failure (typically
        # exit 101 with cargo's ``error[E####]`` diagnostics in
        # stderr). The pre-fix branch surfaced both as "likely build
        # failure" wording, misleading users whose stderr clearly
        # showed ``Finished test profile … target(s)`` earlier in the
        # run. Post-fix: emit a distinct message that names the
        # actual cause and references the offending filter expression
        # so the user can correlate. Stays on
        # ``kind="unparseable-output"`` per
        # ``tasks/run-team-2026-06-04-cargo-cli-orchestration-defect.md``
        # §2 — adding a new kind would be a model-shape change and
        # requires a ``questions/`` entry; v1 disambiguation via
        # message text is sufficient. After Fix A above, this branch
        # rarely fires on the ``novetest run .`` path (directory-type
        # targets no longer reach nextest as filters); the carve-out
        # remains valuable for users who pass explicit filter
        # expressions (e.g. ``novetest run tests::nonexistent``).
        if (
            _NEXTEST_NO_TESTS_LITERAL in stderr_text
            and _NEXTEST_NO_TESTS_ERROR_LITERAL in stderr_text
        ):
            raise AdapterInvocationError(
                f"cargo nextest filter matched zero tests "
                f"(target_expression={target_expression!r}, "
                f"target_type={test_target.target_type!r}); the filter "
                f"expression did not match any test in the workspace. "
                f"Pass an explicit filter like ``tests::name`` or "
                f"``package(crate)``, or omit the positional argument "
                f"to run the full workspace. stderr tail: "
                f"{stderr_text[-400:]}",
                kind="unparseable-output",
            )
        raise AdapterInvocationError(
            f"cargo nextest exited {result.returncode} without starting any test "
            f"(likely build failure); stderr tail: {detail_source[-400:]}",
            kind="unparseable-output",
        )

    # Write the canonical events.jsonl artifact — one event per line so
    # downstream consumers can re-read without our adapter as a
    # dependency.
    with events_path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    if collect_coverage and not coverage_path.exists():
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        # Symmetric with the build-failure branch above: env-var-
        # missing is a more specific cause than "llvm-cov didn't
        # write the LCOV file" and must be checked first. ``cargo
        # llvm-cov nextest`` propagates the same env-var requirement
        # because it wraps nextest internally and forwards the
        # ``--message-format=libtest-json`` flag.
        if _NEXTEST_LIBTEST_JSON_ENV_LITERAL in stderr_text:
            raise _libtest_json_env_misconfigured_error(
                mode="llvm-cov nextest",
                returncode=result.returncode,
                stderr_tail=stderr_text[-400:],
            )
        raise AdapterInvocationError(
            f"cargo llvm-cov did not write {coverage_path}; "
            f"stderr tail: {stderr_text[-400:]}",
            kind="unparseable-output",
        )

    nextest_version = await _read_nextest_version(
        cargo_path, test_target.workspace_path
    )
    engine_version = await _read_cargo_version(
        cargo_path, test_target.workspace_path
    )

    payload: dict[str, object] = {
        "events": events,
        "binaries": sorted(binaries_seen),
        "failure_logs": failure_logs,
    }

    # Secondary-runner version surfaces on `RunRecord.metadata` via the
    # typed slot (per `decisions/2026-05-30-native-result-metadata-slot.md`,
    # which retired the lazy payload-stash convention). `engine_version`
    # carries the *primary* engine (cargo itself); `nextest_version`
    # identifies which runner produced the libtest-json events. Both
    # matter for replay/regression; both must surface to AI consumers
    # reading `record.json`. Skipped when the probe failed — the typed
    # slot is `dict[str, str]` so `None` cannot be assigned, and the
    # absence is more informative than a literal ``"None"`` string.
    metadata: dict[str, str] = {}
    if nextest_version is not None:
        metadata["nextest_version"] = nextest_version

    artifact_paths: dict[str, Path] = {
        "cargo_events_jsonl": events_path,
        "stdout": stdout_path,
        "stderr": stderr_path,
    }
    if collect_coverage:
        # Distinct artifact key from pytest/jest's `coverage_json` and
        # go-test's `coverage_profile` — the future Coverage-team slice
        # dispatches on `engine_name == "cargo-test"` to parse LCOV.
        artifact_paths["coverage_lcov"] = coverage_path

    return NativeResult(
        engine_name="cargo-test",
        payload=payload,
        artifact_paths=artifact_paths,
        returncode=result.returncode,
        started_at_ms=started_ms,
        completed_at_ms=completed_ms,
        engine_version=engine_version,
        metadata=metadata,
    )


def _safe_failure_log_name(name: str) -> str:
    """Convert a libtest-json ``name`` (e.g. ``crate::tests::foo``) into a
    filesystem-safe basename.

    Replacement rules (documented choice; alternatives are URL-encoding
    or base64 — both less readable):

    - ``/`` → ``_``  (Unix path separator; appears in integration-test
      binary paths emitted in some nextest versions)
    - ``:`` → ``_``  (Rust's ``::`` module separator becomes ``__``
      naturally; also covers the Windows-illegal ``:`` character in
      drive prefixes)
    - ``\\`` → ``_`` (Windows path separator — defensive; nextest emits
      forward slashes only)

    A double-underscore in the result therefore signals "this is where
    the original ``::`` module separator was"; consumers that need a
    round-trip can store the unescaped ``name`` separately (the
    ``failure_logs`` payload key does exactly that).
    """

    return (
        name.replace("/", "_").replace(":", "_").replace("\\", "_")
    )


def _build_child_env() -> dict[str, str]:
    """Build the subprocess env for ``cargo nextest``.

    Mirrors the determinism intent of pytest's `_build_child_env` /
    jest's `_build_child_env` / gotest's `_build_child_env`:

    - ``CARGO_TERM_COLOR=never`` strips ANSI escapes from cargo's own
      diagnostics (build errors, progress).
    - ``RUST_BACKTRACE=1`` enables the standard backtrace on panic so
      captured per-test stdout carries the failing frame. Per
      `engine-adapters.md §5`, this is set unconditionally — backtraces
      are how failure-detail capture works for Rust.
    - ``NO_COLOR=1`` is the cross-tool convention (libtest itself, the
      panic handler, third-party assertion crates like `pretty_assertions`
      all honor it).
    - ``NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`` is the gate that
      ``cargo-nextest`` ≥ 0.9.50 (our supported floor — see
      `decisions/2026-05-25-supported-engine-matrix.md`) requires before
      it will accept ``--message-format=libtest-json``. Without it,
      nextest exits 95 with a runtime error and writes zero events,
      which the build-failure heuristic then misclassifies as
      ``adapter-unparseable-output``.

    Notably absent:
    - NO ``RUSTFLAGS`` — overriding would invalidate the user's build
      cache and re-trigger a full rebuild on every run.
    - NO ``CARGO_INCREMENTAL=0`` — same reason. The user's incremental
      cache stays intact.
    """

    env = os.environ.copy()
    env["CARGO_TERM_COLOR"] = "never"
    env["RUST_BACKTRACE"] = "1"
    env["NO_COLOR"] = "1"
    env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] = "1"
    return env


async def _read_cargo_version(cargo_path: str, workspace: Path) -> str | None:
    """Best-effort version read via ``cargo --version``.

    Returns the bare semver string (e.g. ``"1.74.0"``) extracted from
    cargo's canonical output ``cargo 1.74.0 (ecb9851af 2023-10-18)``.
    Returns ``None`` silently on any subprocess failure or unparseable
    output: version is informational metadata, never load-bearing for
    the Run Record's correctness.
    """

    try:
        result = await run_subprocess(
            [cargo_path, "--version"],
            cwd=workspace,
            timeout=10.0,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.decode("utf-8", errors="replace").strip()
    # Expected: "cargo 1.74.0 (ecb9851af 2023-10-18)"
    parts = text.split()
    if len(parts) >= 2 and parts[0] == "cargo":
        version = parts[1]
        return version if version else None
    return None


async def _read_nextest_version(cargo_path: str, workspace: Path) -> str | None:
    """Best-effort version read via ``cargo nextest --version``.

    Returns the bare semver string (e.g. ``"0.9.70"``) extracted from
    nextest's canonical output ``cargo-nextest 0.9.70``. Returns
    ``None`` silently on any subprocess failure or unparseable output.

    Tolerates output-format variations by picking the first
    dotted-numeric token (some nextest versions add suffixes like
    `(some-hash 2024-01-15)` to the version line).
    """

    try:
        result = await run_subprocess(
            [cargo_path, "nextest", "--version"],
            cwd=workspace,
            timeout=10.0,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.decode("utf-8", errors="replace").strip()
    # Expected: "cargo-nextest 0.9.70" (sometimes with trailing build info).
    for token in text.split():
        if token and token[0].isdigit() and "." in token:
            return token
    return None


__all__ = [
    "COVERAGE_LCOV_FILENAME",
    "EVENTS_JSONL_FILENAME",
    "FAILURES_DIR_NAME",
    "STDERR_LOG_FILENAME",
    "STDOUT_LOG_FILENAME",
    "run_cargo",
]
