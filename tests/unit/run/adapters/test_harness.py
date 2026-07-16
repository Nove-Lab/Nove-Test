"""Unit tests for the shared adapter harness (``run/adapters/_harness.py``).

Single-source tests for the four mechanics extracted from the six native
adapters in refactoring slice W2/S13 (findings RUN-04 / RUN-06 / RUN-17 /
RUN-23):

- ``safe_failure_log_name`` — the union escape charset (Windows-reserved +
  whitespace) plus per-engine extras (RUN-06).
- ``write_failure_log`` — POSIX relative path (RUN-04) + skip-if-empty
  (RUN-17).
- ``run_and_capture`` — the timed spawn + stdout/stderr capture + the ONE
  ``kind="timed-out"`` raise (RUN-23).
- ``prepare_artifact_dirs`` — resolve + ``native/`` creation.

Plus a divergence guard asserting no adapter re-defines a private
``_safe_failure_log_name`` (the drift RUN-06 recorded — 3/3/11/16 charsets).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from novetest.run.adapters import _harness
from novetest.run.adapters._harness import (
    prepare_artifact_dirs,
    run_and_capture,
    safe_failure_log_name,
    write_failure_log,
)
from novetest.run.errors import AdapterInvocationError
from novetest.utils.asyncio_subprocess import SubprocessResult


# ---------------------------------------------------------------------------
# safe_failure_log_name — RUN-06 (union charset + per-engine extras)
# ---------------------------------------------------------------------------


class TestSafeFailureLogName:
    def test_plain_name_unchanged(self) -> None:
        # No reserved characters → byte-identical (``.`` and ``_`` are safe).
        assert safe_failure_log_name("crate.tests.foo_bar") == "crate.tests.foo_bar"

    def test_default_replaces_common_separators(self) -> None:
        # ``/`` and ``:`` are the go/cargo node-id separators — both in the
        # default union, so the 3-char adapters get correct escaping with
        # ZERO extras (the RUN-06 charset growth from 3 → union).
        assert safe_failure_log_name("example.com/foo::TestSub") == (
            "example.com_foo__TestSub"
        )

    def test_default_covers_every_windows_reserved_char(self) -> None:
        # The union ALWAYS covers ``< > : " / \\ | ? *`` — cargo/gotest
        # previously escaped only ``/ : \``, so an exotic test name with a
        # reserved char could hit OSError on Windows (RUN-06 scenario).
        for reserved in '<>:"/\\|?*':
            result = safe_failure_log_name(f"a{reserved}b")
            assert result == "a_b", f"reserved char {reserved!r} not escaped"

    def test_default_covers_whitespace(self) -> None:
        assert safe_failure_log_name("a b\tc") == "a_b_c"

    def test_extra_chars_add_engine_specific(self) -> None:
        # junit/dotnet add ``#``/``[](),``/``=``/``'`` etc. via extra_chars.
        result = safe_failure_log_name(
            "X#test[1, foo](int)", ("#", "[", "]", "(", ")", ",")
        )
        for bad in "#[](),":
            assert bad not in result

    def test_extra_chars_left_untouched_without_opt_in(self) -> None:
        # ``#`` is NOT in the default union — an adapter that does not pass
        # it as an extra keeps it verbatim (the seam is opt-in per engine).
        assert "#" in safe_failure_log_name("a#b")

    def test_result_is_deterministic_regardless_of_set_order(self) -> None:
        # The escape iterates a frozenset (non-deterministic order); the
        # result must be stable because ``_`` is never itself a source char.
        name = '<>:"/\\|?* \ta#b(c)'
        assert (
            safe_failure_log_name(name, ("#", "(", ")"))
            == safe_failure_log_name(name, ("#", "(", ")"))
        )


# ---------------------------------------------------------------------------
# write_failure_log — RUN-04 (posix relative path) + RUN-17 (skip-if-empty)
# ---------------------------------------------------------------------------


class TestWriteFailureLog:
    def test_non_empty_writes_and_registers_posix_relative_path(
        self, tmp_path: Path
    ) -> None:
        artifact_dir = tmp_path
        failures_dir = artifact_dir / "native" / "failures"
        failure_logs: dict[str, str] = {}
        write_failure_log(
            node_id="pkg::TestFoo",
            content="boom\ntraceback",
            failures_dir=failures_dir,
            artifact_dir=artifact_dir,
            failure_logs=failure_logs,
        )
        assert "pkg::TestFoo" in failure_logs
        rel = failure_logs["pkg::TestFoo"]
        # RUN-04: forward-slash POSIX, relative, never absolute / backslash.
        assert rel == "native/failures/pkg__TestFoo.log"
        assert "\\" not in rel
        assert not Path(rel).is_absolute()
        assert (artifact_dir / rel).read_text(encoding="utf-8") == "boom\ntraceback"

    def test_empty_content_writes_and_registers_nothing(self, tmp_path: Path) -> None:
        # RUN-17: the unified skip-if-empty rule — cargo/dotnet used to
        # write a 0-byte log + register it; now nothing happens.
        artifact_dir = tmp_path
        failures_dir = artifact_dir / "native" / "failures"
        failure_logs: dict[str, str] = {}
        write_failure_log(
            node_id="pkg::TestEmpty",
            content="",
            failures_dir=failures_dir,
            artifact_dir=artifact_dir,
            failure_logs=failure_logs,
        )
        assert failure_logs == {}
        assert not failures_dir.exists()

    def test_extra_chars_shape_the_basename(self, tmp_path: Path) -> None:
        artifact_dir = tmp_path
        failures_dir = artifact_dir / "native" / "failures"
        failure_logs: dict[str, str] = {}
        write_failure_log(
            node_id="Foo#bar(int)",
            content="x",
            failures_dir=failures_dir,
            artifact_dir=artifact_dir,
            failure_logs=failure_logs,
            extra_chars=("#", "(", ")"),
        )
        # Key keeps the raw node id (round-trip); the FILE basename escapes.
        assert failure_logs["Foo#bar(int)"] == "native/failures/Foo_bar_int_.log"


# ---------------------------------------------------------------------------
# run_and_capture — RUN-23 (timing + capture + single timed-out contract)
# ---------------------------------------------------------------------------


def _fake_result(*, timed_out: bool = False) -> SubprocessResult:
    return SubprocessResult(
        returncode=124 if timed_out else 0,
        stdout=b"OUT",
        stderr=b"ERR",
        timed_out=timed_out,
    )


class TestRunAndCapture:
    async def test_happy_path_captures_and_returns_timing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_run_subprocess(argv, **kwargs):  # type: ignore[no-untyped-def]
            return _fake_result()

        monkeypatch.setattr(_harness, "run_subprocess", fake_run_subprocess)
        stdout_path = tmp_path / "stdout.log"
        stderr_path = tmp_path / "stderr.log"
        result, started_ms, completed_ms = await run_and_capture(
            ["echo", "hi"],
            cwd=tmp_path,
            timeout=5.0,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_label="pytest",
        )
        assert result.returncode == 0
        assert stdout_path.read_bytes() == b"OUT"
        assert stderr_path.read_bytes() == b"ERR"
        assert isinstance(started_ms, int) and isinstance(completed_ms, int)
        assert completed_ms >= started_ms

    async def test_timed_out_raises_the_one_timed_out_contract(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_run_subprocess(argv, **kwargs):  # type: ignore[no-untyped-def]
            return _fake_result(timed_out=True)

        monkeypatch.setattr(_harness, "run_subprocess", fake_run_subprocess)
        stdout_path = tmp_path / "stdout.log"
        stderr_path = tmp_path / "stderr.log"
        with pytest.raises(AdapterInvocationError) as excinfo:
            await run_and_capture(
                ["mvn", "test"],
                cwd=tmp_path,
                timeout=30.0,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout_label="mvn test",
            )
        # The kind token is the data contract RUN-23 pins in ONE place.
        assert excinfo.value.kind == "timed-out"
        assert "mvn test exceeded 30.0s timeout" == str(excinfo.value)
        # Partial output is persisted BEFORE the raise (diagnosability).
        assert stdout_path.read_bytes() == b"OUT"
        assert stderr_path.read_bytes() == b"ERR"

    async def test_file_not_found_propagates_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A launcher TOCTOU FileNotFoundError must reach the adapter so it
        # can map to its own typed missing-binary error.
        async def fake_run_subprocess(argv, **kwargs):  # type: ignore[no-untyped-def]
            raise FileNotFoundError("go removed mid-flight")

        monkeypatch.setattr(_harness, "run_subprocess", fake_run_subprocess)
        with pytest.raises(FileNotFoundError):
            await run_and_capture(
                ["go", "test"],
                cwd=tmp_path,
                timeout=5.0,
                stdout_path=tmp_path / "stdout.log",
                stderr_path=tmp_path / "stderr.log",
                timeout_label="go test",
            )


# ---------------------------------------------------------------------------
# prepare_artifact_dirs
# ---------------------------------------------------------------------------


class TestPrepareArtifactDirs:
    def test_resolves_and_creates_native_dir(self, tmp_path: Path) -> None:
        artifact_dir, native_dir = prepare_artifact_dirs(tmp_path / "run_x")
        assert artifact_dir == (tmp_path / "run_x").resolve()
        assert native_dir == artifact_dir / "native"
        assert native_dir.is_dir()

    def test_idempotent_on_second_call(self, tmp_path: Path) -> None:
        prepare_artifact_dirs(tmp_path / "run_x")
        artifact_dir, native_dir = prepare_artifact_dirs(tmp_path / "run_x")
        assert native_dir.is_dir()


# ---------------------------------------------------------------------------
# Single-source divergence guard (RUN-06)
# ---------------------------------------------------------------------------


_ADAPTER_MODULES = (
    "pytest_adapter",
    "jest_adapter",
    "gotest_adapter",
    "cargo_adapter",
    "junit_adapter",
    "dotnet_adapter",
)


class TestNoAdapterRedefinesSanitizer:
    @pytest.mark.parametrize("module_name", _ADAPTER_MODULES)
    def test_no_private_safe_failure_log_name(self, module_name: str) -> None:
        """No adapter re-defines the private ``_safe_failure_log_name`` that
        RUN-06 found copied four times with diverged (3/3/11/16) charsets —
        the sanitizer now lives ONLY in ``_harness.safe_failure_log_name``."""

        module = importlib.import_module(f"novetest.run.adapters.{module_name}")
        assert not hasattr(module, "_safe_failure_log_name"), (
            f"{module_name} re-defines _safe_failure_log_name; the sanitizer "
            "must be sourced solely from _harness.safe_failure_log_name"
        )

    def test_harness_is_the_single_source(self) -> None:
        assert hasattr(_harness, "safe_failure_log_name")
