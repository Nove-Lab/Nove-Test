"""`go test` Native Engine adapter.

Invokes ``go test -json`` against a Go module workspace, capturing the
NDJSON event stream plus stdout/stderr logs and (optionally) a
cover-profile artifact. Surface for `run/engine.execute`; registered
through `engine.execute_with_engine_context`'s explicit branch on
``engine_name == "go-test"`` (no generic registry yet — the third
adapter still does not motivate the abstraction, but it does motivate
moving in that direction at the fourth).

Foundations parity with pytest_adapter / jest_adapter:

- ``cwd`` is required and must be the workspace root containing ``go.mod``.
- All native artifacts (``events.jsonl``, ``stdout.log``, ``stderr.log``,
  optional ``cover.out``, per-test failure logs) land under
  ``<artifact_dir>/native/``. The orchestration layer rewrites those
  absolute paths to Project-Store-relative strings before persisting the
  Run Record.
- ``collect_coverage=True`` adds ``-cover -coverprofile=<...>/cover.out
  -covermode=atomic -coverpkg=./...`` and registers the resulting
  profile under the artifact key ``coverage_profile`` (NOT
  ``coverage_json`` — that key is reserved for Istanbul / coverage.py
  JSON; the Coverage engine dispatches format-handling on
  ``engine_name``).

Unlike pytest, ``go test`` has no plugin-autoload concept. The closest
analogue is the module-cache layer (``GOFLAGS=-mod=readonly`` keeps it
deterministic — see ``_build_child_env``).

Target conversion (RUN-01, W1/S1): ``go test`` interprets a bare
positional as a package selector — a plain directory name (``pkg``) is
read as an IMPORT PATH (pre-compile failure) and ``.`` runs the ROOT
package only, non-recursively (silent false green on modules whose tests
live in subpackages). The adapter therefore converts the Test Target by
``target_type`` instead of appending it verbatim — see
``_go_target_args`` for the conversion table.

Per-test failure logs are written **here**, not in the normalizer. The
adapter is the only layer that holds ``artifact_dir``; the normalizer
just consumes a payload-resident map of ``"<Package>::<Test>" →
"<relative path>"`` strings. Coupling the adapter to the normalizer's
node-id format (``<Package>::<Test>``) is documented and intentional —
the alternative (threading ``artifact_dir`` through ``normalize_native_result``)
churns more surface for the same effect.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path, PurePosixPath
from typing import Any

from novetest.run.adapters._target_guard import reject_dash_leading_target
from novetest.run.errors import AdapterInvocationError
from novetest.run.types import NativeResult, TestTarget
from novetest.utils.asyncio_subprocess import run_subprocess


EVENTS_JSONL_FILENAME = "events.jsonl"
STDOUT_LOG_FILENAME = "stdout.log"
STDERR_LOG_FILENAME = "stderr.log"
COVER_PROFILE_FILENAME = "cover.out"
FAILURES_DIR_NAME = "failures"


async def run_gotest(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None = 600.0,
    collect_coverage: bool = False,
) -> NativeResult:
    """Run ``go test`` against ``test_target`` and return the parsed Native Result.

    ``artifact_dir`` is the per-run directory under
    ``.novetest/run/artifacts/run_<ulid>/`` where ``native/`` is created;
    in tests, pass a ``tmp_path``-rooted directory.

    When ``collect_coverage`` is True, ``go test`` is invoked with
    ``-cover -coverprofile=<artifact_dir>/native/cover.out
    -covermode=atomic -coverpkg=./...``. ``-coverpkg=./...`` is mandatory
    (per engine-adapters.md §4 edge cases) — without it, only the test's
    own package is measured. The ``cover.out`` file is registered under
    the artifact key ``coverage_profile``.
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
    cover_path = native_dir / COVER_PROFILE_FILENAME
    failures_dir = native_dir / FAILURES_DIR_NAME

    # Resolve `go` up front. Unlike `npx` on Windows, `go.exe` is a
    # real PE binary that `CreateProcess` (and therefore
    # `asyncio.create_subprocess_exec`) can launch directly — no `cmd /c`
    # launcher needed. An absent `go` is reported as a typed error here
    # rather than letting a downstream `FileNotFoundError` surface a less
    # specific message.
    go_path = shutil.which("go")
    if go_path is None:
        raise AdapterInvocationError(
            "`go` not found on PATH; install Go 1.21+ from https://go.dev/dl/",
            kind="missing-binary",
            install_hint="install Go 1.21+ from https://go.dev/dl/",
        )

    # RUN-22 guard: a dash-leading target would be consumed by `go test`
    # as a flag (e.g. `-count=5` overriding our `-count=1`), never as a
    # package selector. Rejected before any conversion or spawn.
    reject_dash_leading_target(
        test_target.target_expression, engine_label="go test"
    )

    # `-count=1` disables Go's per-test result cache (§4 edge cases) so a
    # re-invocation of the adapter always re-runs the test bodies.
    # `-timeout` mirrors the subprocess-level timeout at the engine level
    # — `go test` will kill long-running tests itself rather than waiting
    # for our parent to do it.
    timeout_seconds = int(timeout) if timeout is not None else 600
    argv: list[str] = [
        go_path,
        "test",
        "-json",
        "-count=1",
        f"-timeout={timeout_seconds}s",
    ]
    if collect_coverage:
        argv.extend(
            [
                "-cover",
                f"-coverprofile={cover_path}",
                "-covermode=atomic",
                "-coverpkg=./...",
            ]
        )
    argv.extend(_go_target_args(test_target))

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
        # `go` was resolved above, so this is a narrow fallback: a TOCTOU
        # race (binary removed between resolution and exec). Surface as
        # typed error rather than a raw Python traceback.
        raise AdapterInvocationError(
            "the `go` launcher could not be executed; install Go 1.21+ from "
            "https://go.dev/dl/",
            kind="missing-binary",
            install_hint="install Go 1.21+ from https://go.dev/dl/",
        ) from exc
    completed_ms = int(time.time() * 1000)

    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)

    if result.timed_out:
        raise AdapterInvocationError(
            f"go test exceeded {timeout}s timeout",
            kind="timed-out",
        )

    # Stream-parse stdout line by line. `go test -json` emits NDJSON
    # (one event per line); never parse the buffer as a single JSON
    # document. We read the bytes after the process exits because
    # `run_subprocess` captures eagerly — that's not "true" streaming,
    # but it preserves the *parser* contract: a malformed line in the
    # middle of the stream does not abort the rest. Buffer is bounded
    # by Go's natural output cadence (typically << 1 MB per package).
    events: list[dict[str, Any]] = []
    packages_seen: set[str] = set()
    saw_run_action = False
    # Per-test output buffers keyed by (Package, Test). Only failing
    # tests' buffers are written to disk (one log file per failure).
    output_buffers: dict[tuple[str, str], list[str]] = {}
    failure_logs: dict[str, str] = {}  # "<Package>::<Test>" → relative path

    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Defensive parsing: skip malformed lines rather than abort.
            # Go has never emitted invalid JSON in the documented format
            # (`go doc cmd/test2json`), but the defensive-parsing decision
            # of 2026-05-25 requires us to tolerate drift gracefully.
            continue
        if not isinstance(event, dict):
            continue
        events.append(event)

        action = event.get("Action")
        package = event.get("Package")
        test = event.get("Test")
        if isinstance(package, str) and package:
            packages_seen.add(package)

        # Buffer output events keyed by (Package, Test). Package-level
        # outputs (Test absent or empty — e.g. `FAIL\texample.com/foo\t0.003s`)
        # are recorded in `events` but not attributed to any test.
        if (
            action == "output"
            and isinstance(package, str)
            and package
            and isinstance(test, str)
            and test
        ):
            output_text = event.get("Output")
            if isinstance(output_text, str):
                output_buffers.setdefault((package, test), []).append(output_text)

        if (
            action == "run"
            and isinstance(test, str)
            and test
        ):
            saw_run_action = True

        # On a failing terminal action, drain the buffer to a per-test
        # failure log file. URL-style escaping is not needed — replace
        # `/` (subtest separator) with `_` and `:` (package-path colon
        # in module paths like `example.com/foo:tools`) with `_` so the
        # filename is unambiguous and filesystem-safe everywhere.
        if (
            action == "fail"
            and isinstance(package, str)
            and package
            and isinstance(test, str)
            and test
        ):
            buffer = output_buffers.get((package, test))
            if buffer:
                node_id = f"{package}::{test}"
                safe_name = _safe_failure_log_name(node_id)
                failures_dir.mkdir(parents=True, exist_ok=True)
                failure_path = failures_dir / f"{safe_name}.log"
                failure_path.write_text("".join(buffer), encoding="utf-8")
                # Store the path RELATIVE to artifact_dir so Memory's
                # path-rewriting layer treats it like any other artifact.
                failure_logs[node_id] = str(
                    failure_path.relative_to(artifact_dir)
                )

    # Build-failure detection. `go test -json` does not emit *any*
    # NDJSON events when `go build` fails before test setup — the build
    # errors go straight to stderr and stdout is empty. Use the
    # "no `run` action ever fired" + "non-zero exit" combination as the
    # discriminant: a successful empty-test-set package exits 0 with a
    # `skip` action, distinguishing it from a build failure.
    #
    # A build failure (corrupt `go.mod`, syntax error in the SuT) is a
    # USER-side error, not an adapter failure (S15 rider, routed from the
    # W1/S8 close — morally identical to a pytest import error): the
    # payload flows on to normalization, where zero test results + a
    # non-zero exit yield a persisted `status="errored"` Run Record
    # (exit 3). The build detail is preserved in the stdout/stderr
    # artifacts written above.
    build_failed = not saw_run_action and result.returncode != 0

    # Write the events.jsonl artifact — one canonical event per line so
    # downstream consumers (the future Localization / Replay slices) can
    # re-read it without our adapter as a dependency.
    with events_path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    if collect_coverage and not build_failed and not cover_path.exists():
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        raise AdapterInvocationError(
            f"go test --coverage did not write {cover_path}; "
            f"stderr tail: {stderr_text[-400:]}",
            kind="unparseable-output",
        )

    payload: dict[str, object] = {
        "events": events,
        "packages": sorted(packages_seen),
        "failure_logs": failure_logs,
    }

    engine_version = await _read_go_version(go_path, test_target.workspace_path)

    artifact_paths: dict[str, Path] = {
        "gotest_events_jsonl": events_path,
        "stdout": stdout_path,
        "stderr": stderr_path,
    }
    if collect_coverage and not build_failed:
        # Distinct key from pytest/jest's `coverage_json` — the future
        # Coverage-team slice will dispatch on `engine_name == "go-test"`
        # to parse the cover-profile format (NOT Istanbul JSON). On a
        # build failure no profile was written; the key is omitted so
        # downstream `coverage` verbs report unavailable for this run.
        artifact_paths["coverage_profile"] = cover_path

    return NativeResult(
        engine_name="go-test",
        payload=payload,
        artifact_paths=artifact_paths,
        returncode=result.returncode,
        started_at_ms=started_ms,
        completed_at_ms=completed_ms,
        engine_version=engine_version,
    )


def _go_target_args(test_target: TestTarget) -> list[str]:
    """Convert a Test Target into the trailing ``go test`` argv elements.

    Conversion table (RUN-01, W1/S1 — see also
    ``design/implementation-plan/engine-adapters.md §4``):

    - empty expression (``target_type="workspace"``) → ``["./..."]`` —
      every package under the module, the pre-existing default;
    - nodeid ``<pkg>::<TestName>`` → ``["-run", "^<TestName>$", <selector>]``
      — anchored per subtest level, regex metacharacters escaped
      (``_anchored_run_pattern``), package half converted by
      ``_package_selector``;
    - an all-dots component (``./...``, ``pkg/...``) → verbatim: already
      engine-native pattern syntax. Decided LEXICALLY, before the
      ``target_type`` dispatch, because Win32 strips trailing dots from
      path components and can classify ``./...`` as a directory (same
      trap as ``normalize_target_expression``'s guard, 2026-07-04);
    - ``target_type="directory"`` → ``./<rel-posix>/...`` (``.`` →
      ``./...``): recursive, consistent with cargo/dotnet treating a
      directory target as "run that whole scope". A bare relative
      directory would otherwise be read as an import path (pre-compile
      failure) and ``.`` would run the root package only, non-recursively
      (silent false green);
    - anything else (``target_type="file"``) → verbatim. ``go test``
      file mode (``go test foo_test.go``) requires every dependent file
      to be listed explicitly, so a single-file target usually fails
      loudly — out of W1/S1 scope, noted in the handoff.

    Inputs arrive anchor-relative canonical-POSIX from
    ``normalize_target_expression`` (D3); ``PurePosixPath`` keeps the
    conversion platform-independent for direct workflow-API callers too.
    """

    expression = test_target.target_expression
    if not expression:
        return ["./..."]
    if test_target.target_type == "nodeid":
        package_part, _, test_name = expression.partition("::")
        selector = _package_selector(package_part, test_target.workspace_path)
        if not test_name:
            # Degenerate `pkg::` — no test half to filter on; run the
            # package. (`-run '^$'` would silently select zero tests.)
            return [selector]
        return ["-run", _anchored_run_pattern(test_name), selector]
    if _has_all_dots_component(expression):
        return [expression]
    if test_target.target_type == "directory":
        rel_posix = PurePosixPath(expression).as_posix()
        if rel_posix == ".":
            return ["./..."]
        return [f"./{rel_posix}/..."]
    return [expression]


def _package_selector(package_part: str, workspace: Path) -> str:
    """Convert the package half of a nodeid into a ``go test`` selector.

    - empty → ``./...`` (filter across the whole module);
    - ``.`` → ``.`` (root package);
    - an existing directory under the workspace → ``./<rel-posix>``
      (relative-directory form — a bare ``pkg`` would be read as an
      import path and fail to resolve);
    - anything else → verbatim: full import paths
      (``example.com/mod/pkg``, the shape RunRecord node ids carry) are
      valid selectors inside the module as-is.
    """

    if not package_part:
        return "./..."
    rel_posix = PurePosixPath(package_part).as_posix()
    if rel_posix == ".":
        return "."
    if (workspace / rel_posix).is_dir():
        return f"./{rel_posix}"
    return package_part


def _anchored_run_pattern(test_name: str) -> str:
    """Build the anchored ``-run`` regex for ``<TestName>`` (incl. subtests).

    ``go test -run`` splits the pattern on unbracketed ``/`` and matches
    each element against the corresponding subtest level, so each level
    is anchored and escaped independently: ``TestParent/zero`` →
    ``^TestParent$/^zero$``. Without anchoring, ``-run TestAdd`` also
    matches ``TestAddSubtests`` — the nodeid contract is exact selection.
    ``re.escape`` output is valid RE2 (Go's regexp): escaped ASCII
    punctuation is read as the literal character.
    """

    return "/".join(f"^{re.escape(part)}$" for part in test_name.split("/"))


def _has_all_dots_component(expression: str) -> bool:
    """True when any path component of ``expression`` is solely dots.

    Mirrors ``orchestration/anchor_resolution._has_all_dots_component``:
    ``...`` (and longer dot runs) are go's package-wildcard syntax, never
    filesystem names. ``.`` never survives path parsing as a component
    and ``..`` is genuine parent navigation, so neither triggers.
    """

    return any(
        part != ".." and set(part) == {"."}
        for part in PurePosixPath(expression).parts
    )


def _safe_failure_log_name(node_id: str) -> str:
    """Convert ``<Package>::<Test>`` (incl. subtest ``Parent/Child``) into a
    filesystem-safe basename.

    Replacement rules (documented choice; alternatives are URL-encoding or
    base64 — both less readable):

    - ``/`` → ``_``  (covers both module-path separators in ``Package``
      and the ``Parent/Child`` subtest separator)
    - ``:`` → ``_``  (covers the ``::`` join between Package and Test, and
      Windows-illegal `:` characters generally)
    - ``\\`` → ``_`` (Windows path separator — defensive, not strictly
      needed because Go always uses forward slashes in test names, but
      cheap to add)

    A double-underscore in the result therefore signals "this is where
    the original `::` separator was"; consumers that need a round-trip
    should store the unescaped ``node_id`` separately (the
    ``failure_logs`` payload key does exactly that).
    """

    return (
        node_id.replace("/", "_").replace(":", "_").replace("\\", "_")
    )


def _build_child_env() -> dict[str, str]:
    """Build the subprocess env for ``go test``.

    Mirrors the determinism intent of pytest's `_build_child_env` /
    jest's `_build_child_env`:

    - ``GOFLAGS=-mod=readonly`` keeps Go from walking vendored dirs or
      attempting module downloads mid-run — §4 edge cases call this out
      specifically for Windows. Adding it everywhere costs nothing on
      POSIX (it's already the default for projects with `go.sum`).
    - ``NO_COLOR`` strips ANSI escapes from any captured tool output
      (e.g. error traces from broken builds).
    - ``GOTOOLCHAIN=local`` keeps Go from auto-fetching a newer toolchain
      when the workspace's ``go.mod`` declares a higher ``go`` directive
      than the installed binary — that would re-trigger network access
      on a `-mod=readonly` run and surface a confusing error.
    """

    env = os.environ.copy()
    env["GOFLAGS"] = "-mod=readonly"
    env["GOTOOLCHAIN"] = "local"
    env["NO_COLOR"] = "1"
    return env


async def _read_go_version(go_path: str, workspace: Path) -> str | None:
    """Best-effort version read via ``go version``.

    Returns the bare semver-ish string (e.g. ``"1.23.4"``) extracted from
    Go's canonical version line ``go version go1.23.4 linux/amd64`` —
    same shape since Go 1.0. Returns ``None`` silently on any subprocess
    failure or unparseable output: version is informational metadata,
    never load-bearing for the Run Record's correctness (mirrors
    `_read_jest_version` / `_read_pytest_version`).
    """

    try:
        result = await run_subprocess(
            [go_path, "version"],
            cwd=workspace,
            timeout=10.0,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.decode("utf-8", errors="replace").strip()
    # Expected: "go version go1.23.4 linux/amd64"
    parts = text.split()
    if len(parts) >= 3 and parts[2].startswith("go"):
        version = parts[2][2:]
        return version if version else None
    return None


__all__ = [
    "COVER_PROFILE_FILENAME",
    "EVENTS_JSONL_FILENAME",
    "FAILURES_DIR_NAME",
    "STDERR_LOG_FILENAME",
    "STDOUT_LOG_FILENAME",
    "run_gotest",
]
