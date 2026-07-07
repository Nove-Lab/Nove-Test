"""Per-engine ``parse_failure_log`` regex tests.

Each engine's failure-log format is distinct enough that the regex
dispatcher needs explicit per-engine coverage:

- pytest: ``<path>:<line>: <message>`` (crash form) +
          ``File "<path>", line N, in <name>`` (traceback frame form).
- jest:   ``at <name> (<path>:<line>:<col>)`` (Node.js stack frame) +
          ``at <path>:<line>:<col>`` (no enclosing name) +
          ``<path>:<line>:<col>`` (diagnostic context line).
- cargo:  ``panicked at <path>:<line>:<col>`` + ``failed at`` form +
          bare ``<path>.rs:<line>:<col>`` catch-all.
- gotest: ``  add_test.go:14: ...`` (test-failure frame) +
          ``\\t<path>:<line> +<offset>`` (panic-style frame).
- junit:  ``at [prefix/]<pkg>.<Cls>.<method>(<File>.java:<line>)`` —
          basename-only frames reconstructed to package-relative paths;
          test-infra / JDK frames dropped (W1/S7).
- xunit:  ``at <Ns>.<Cls>.<Method>() in <path>:line <N>`` — the ``in``
          clause is PDB-only, so framework frames self-exclude (W1/S7).

The parser is **best-effort**: a regex that finds nothing returns the
empty tuple. The parser MUST NOT crash on malformed input; it MUST
deduplicate ``(file, line)`` tuples within a single failure log so a
file mentioned at the same line in multiple stack frames counts once.

This module also covers ``resolve_failure_text``'s engine routing —
inline (pytest/jest), logfile (cargo/go), and the W1/S7 hybrid branch
(junit/xunit: log path first, inline fallback second).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.localization.failure_proximity import (
    parse_failure_log,
    resolve_failure_text,
)
from novetest.memory.project_store import (
    ProjectStore,
    create_project_store,
    get_project_store_state,
)


# ---------------------------------------------------------------------------
# pytest
# ---------------------------------------------------------------------------


def test_pytest_crash_form_extracts_path_and_line() -> None:
    """``<path>:<line>: <message>`` — what ``pytest_adapter`` sets."""
    text = "tests/test_calc.py:33: AssertionError\n+ assert 12 == 5.0"
    result = parse_failure_log("pytest", text)
    assert ("tests/test_calc.py", 33) in result


def test_pytest_traceback_frame_form_extracts_path_and_line() -> None:
    """``File "<path>", line N`` — the longrepr fallback form."""
    text = (
        'File "src/calc.py", line 5, in buggy\n'
        "    return x * 0\n"
        'File "tests/test_calc.py", line 12, in test_buggy\n'
        "    assert buggy(3) == 3"
    )
    result = parse_failure_log("pytest", text)
    assert ("src/calc.py", 5) in result
    assert ("tests/test_calc.py", 12) in result


def test_pytest_no_match_returns_empty() -> None:
    """A message without a recognizable file:line yields an empty tuple."""
    text = "Some opaque pytest error with no path references"
    result = parse_failure_log("pytest", text)
    assert result == ()


def test_pytest_dedupes_repeated_locations() -> None:
    """The same (file, line) mentioned twice counts once."""
    text = (
        "tests/test_x.py:7: AssertionError\n"
        "tests/test_x.py:7: AssertionError (repeated)"
    )
    result = parse_failure_log("pytest", text)
    # Exactly one (tests/test_x.py, 7) tuple, no duplicates.
    matches = [tup for tup in result if tup == ("tests/test_x.py", 7)]
    assert matches == [("tests/test_x.py", 7)]


def test_pytest_empty_input_returns_empty() -> None:
    """Empty failure_text yields empty tuple (no crash)."""
    assert parse_failure_log("pytest", "") == ()


# ---------------------------------------------------------------------------
# jest
# ---------------------------------------------------------------------------


def test_jest_parens_frame_extracts_path_and_line() -> None:
    """``at <name> (<path>:<line>:<col>)`` — standard Node frame."""
    text = "at Object.<anonymous> (/path/to/src/calc.test.ts:42:21)"
    result = parse_failure_log("jest", text)
    assert any(
        path.endswith("calc.test.ts") and line == 42 for path, line in result
    )


def test_jest_bare_at_frame_extracts_path_and_line() -> None:
    """``at <path>:<line>:<col>`` — no enclosing function name."""
    text = "    at src/calculator.js:14:9"
    result = parse_failure_log("jest", text)
    assert any(
        path.endswith("calculator.js") and line == 14 for path, line in result
    )


def test_jest_no_match_returns_empty() -> None:
    text = "Test failed with some message no file refs"
    result = parse_failure_log("jest", text)
    assert result == ()


# ---------------------------------------------------------------------------
# cargo
# ---------------------------------------------------------------------------


def test_cargo_panicked_at_form_extracts_path_and_line() -> None:
    """``thread '...' panicked at <path>:<line>:<col>`` — libtest panic form."""
    text = "thread 'tests::test_div' panicked at src/lib.rs:32:9:\nassertion failed"
    result = parse_failure_log("cargo-test", text)
    assert ("src/lib.rs", 32) in result


def test_cargo_failed_at_form_extracts_path_and_line() -> None:
    """``assertion failed at <path>:<line>:<col>`` — newer rustc form."""
    text = "assertion `left == right` failed at tests/integration_test.rs:18:5"
    result = parse_failure_log("cargo-test", text)
    assert ("tests/integration_test.rs", 18) in result


def test_cargo_bare_rs_path_does_NOT_match_after_defect3_fix() -> None:
    """Bare ``<path>.rs:<line>:<col>`` without the ``panicked at`` /
    ``failed at`` prefix MUST NOT match — regression pin for Defect 3
    (2026-05-31).

    Pre-fix the cargo regex set had a third "defensive catch-all"
    pattern ``\\b<file>.rs:N:M`` which slurped every frame in cargo
    nextest's default stack backtrace, including Rust stdlib paths
    like ``/rustc/<hash>/library/core/src/panicking.rs:N:M``. Those
    stdlib paths then tied with the real bug file at e_f=1; the
    lexicographic tie-break (file path ascending for ties) pushed
    ``src/arithmetic.rs`` to rank #4 behind three ``/rustc/...`` paths.

    The catch-all was DROPPED at 2026-05-31 (CEO-implied Option D from
    questions/main-branch-team-2026-05-31-localization-aggregate-e2e-defect3-parser-stdlib-pollution.md).
    This negative test pins that decision: a bare path:line that lacks
    the ``panicked at`` / ``failed at`` prefix MUST NOT be returned by
    the parser.

    The algorithm-side defense-in-depth (intersect with covered files
    in ``_derive_aggregate``) is the second layer — but THIS layer
    (parser-side) is the load-bearing one: keep the parser's output
    set tight, don't rely on the algorithm to clean up after it.
    """
    text = "Some stack-like text with src/arithmetic.rs:7:3 mentioned"
    result = parse_failure_log("cargo-test", text)
    # Pre-Defect-3 expectation: would have matched. Post-fix: does NOT match.
    assert ("src/arithmetic.rs", 7) not in result


def test_cargo_stdlib_backtrace_frames_do_NOT_match_after_defect3_fix() -> None:
    """Real cargo nextest stack-backtrace stdlib frames MUST NOT match.

    Captured verbatim from
    ``questions/main-branch-team-2026-05-31-localization-aggregate-e2e-defect3-parser-stdlib-pollution.md``
    (the cargo failure log on equipped host that surfaced Defect 3).
    The parser MUST extract only the top ``panicked at src/arithmetic.rs:53:9``
    line and NOTHING from the ``stack backtrace:`` block.
    """
    real_log = (
        "thread 'arithmetic::tests::test_divide' (27482) panicked at src/arithmetic.rs:53:9:\n"
        "assertion `left == right` failed\n"
        "  left: 12\n"
        " right: 5\n"
        "stack backtrace:\n"
        "   0: __rustc::rust_begin_unwind\n"
        "             at /rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/std/src/panicking.rs:689:5\n"
        "   1: core::panicking::panic_fmt\n"
        "             at /rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/core/src/panicking.rs:80:14\n"
        "   4: localization_aggregate_only::arithmetic::tests::test_divide\n"
        "             at ./src/arithmetic.rs:53:9\n"
        "   6: <closure as core::ops::function::FnOnce<()>>::call_once\n"
        "             at /rustc/ac68faa20c58cbccd01ee7208bf3b6e93a7d7f96/library/core/src/ops/function.rs:250:5\n"
    )
    result = parse_failure_log("cargo-test", real_log)
    # The ONLY extracted tuple should be the panicked-at one.
    assert ("src/arithmetic.rs", 53) in result
    # Stdlib paths from the stack backtrace MUST NOT appear (Defect 3 regression pin).
    stdlib_paths_in_result = [
        path for path, _line in result
        if path.startswith("/rustc/") or "/library/" in path or "ops/function.rs" in path
    ]
    assert stdlib_paths_in_result == [], (
        f"Defect 3 regression: stdlib paths leaked into parser output: "
        f"{stdlib_paths_in_result!r}; full result: {result!r}"
    )
    # Also the ./src/arithmetic.rs:53 frame inside the backtrace section is
    # de-duped with the panicked-at hit (line 53 = same line, same file
    # modulo leading ./ — parser DOES distinguish "./src/x.rs" from
    # "src/x.rs" as separate strings, but that's OK because the algorithm
    # filters non-covered paths anyway). What matters here is no stdlib.


# ---------------------------------------------------------------------------
# gotest
# ---------------------------------------------------------------------------


def test_gotest_frame_extracts_path_and_line() -> None:
    """``  add_test.go:14: expected ...`` — go test -v failure frame."""
    text = "--- FAIL: TestAdd (0.00s)\n    add_test.go:14: expected 5, got 6"
    result = parse_failure_log("gotest", text)
    assert ("add_test.go", 14) in result


def test_gotest_panic_frame_extracts_path_and_line() -> None:
    """``\\t<path>:<line> +0xN`` — go panic stack frame."""
    text = "panic: runtime error: index out of range [3] with length 3\n\tcalculator/arithmetic.go:22 +0x52"
    result = parse_failure_log("gotest", text)
    assert ("calculator/arithmetic.go", 22) in result


def test_gotest_alias_engine_name_resolves_to_same_regexes() -> None:
    """Both ``"gotest"`` and ``"go-test"`` route to the same dispatch.

    Adapter naming has shifted between hyphen and underscore forms over
    cycles; the dispatcher accepts both so call sites don't need to know.
    """
    text = "    add_test.go:14: bad"
    assert parse_failure_log("gotest", text) == parse_failure_log("go-test", text)


# ---------------------------------------------------------------------------
# Unknown engine — defensive fallback to pytest regexes
# ---------------------------------------------------------------------------


def test_unknown_engine_falls_back_to_pytest_regexes() -> None:
    """``<path>.py:<line>`` is universal enough to be the fallback default.

    Adapters that name themselves something new (e.g. dotnet, junit)
    will degrade to "extract anything that looks .py-like" rather than
    crashing. The defensive choice keeps the parser additive: each new
    engine adapter can add its own dispatch entry without breaking
    callers.
    """
    text = "tests/whatever.py:1: AssertionError"
    result = parse_failure_log("dotnet-future-engine", text)
    assert ("tests/whatever.py", 1) in result


def test_malformed_input_does_not_crash() -> None:
    """The parser MUST tolerate arbitrary garbage gracefully."""
    # ANSI escape sequences + null bytes + non-UTF8-looking sequence.
    text = "\x1b[31mfailed\x1b[0m \x00\x00 some garbage \x7f"
    # Should return without raising; result tuple is implementation-defined.
    parse_failure_log("pytest", text)
    parse_failure_log("cargo-test", text)
    parse_failure_log("jest", text)
    parse_failure_log("gotest", text)
    parse_failure_log("junit", text)
    parse_failure_log("xunit", text)


# ---------------------------------------------------------------------------
# junit (W1/S7, ANA-02)
# ---------------------------------------------------------------------------
#
# The two multi-line logs below are the adapter-written per-test failure
# logs captured VERBATIM on the equipped host (2026-07-07): Maven
# Surefire 3.2.5 and Gradle 8.14.5 against the junit-maven-basic /
# junit-gradle-basic fixtures (JDK 17.0.19, JUnit Jupiter). They are the
# empirical ground truth the W1/S7 regexes were designed against — do
# not "simplify" them; the framework/JDK frame noise IS the test.

_REAL_JUNIT_MAVEN_LOG = """\
[message] expected: <1> but was: <0>
[type] org.opentest4j.AssertionFailedError
[stack]
org.opentest4j.AssertionFailedError: expected: <1> but was: <0>
\tat org.junit.jupiter.api.AssertionFailureBuilder.build(AssertionFailureBuilder.java:151)
\tat org.junit.jupiter.api.AssertionFailureBuilder.buildAndThrow(AssertionFailureBuilder.java:132)
\tat org.junit.jupiter.api.AssertEquals.failNotEqual(AssertEquals.java:197)
\tat org.junit.jupiter.api.AssertEquals.assertEquals(AssertEquals.java:150)
\tat org.junit.jupiter.api.AssertEquals.assertEquals(AssertEquals.java:145)
\tat org.junit.jupiter.api.Assertions.assertEquals(Assertions.java:531)
\tat com.example.CalculatorTest.testSubtract(CalculatorTest.java:27)
\tat java.base/java.lang.reflect.Method.invoke(Method.java:569)
\tat java.base/java.util.ArrayList.forEach(ArrayList.java:1511)
\tat java.base/java.util.ArrayList.forEach(ArrayList.java:1511)
"""

_REAL_JUNIT_GRADLE_LOG = """\
[message] org.opentest4j.AssertionFailedError: expected: <1> but was: <0>
[type] org.opentest4j.AssertionFailedError
[stack]
org.opentest4j.AssertionFailedError: expected: <1> but was: <0>
\tat app//org.junit.jupiter.api.AssertionFailureBuilder.build(AssertionFailureBuilder.java:151)
\tat app//org.junit.jupiter.api.AssertionFailureBuilder.buildAndThrow(AssertionFailureBuilder.java:132)
\tat app//org.junit.jupiter.api.AssertEquals.failNotEqual(AssertEquals.java:197)
\tat app//org.junit.jupiter.api.AssertEquals.assertEquals(AssertEquals.java:150)
\tat app//org.junit.jupiter.api.AssertEquals.assertEquals(AssertEquals.java:145)
\tat app//org.junit.jupiter.api.Assertions.assertEquals(Assertions.java:531)
\tat app//com.example.CalculatorTest.testSubtract(CalculatorTest.java:26)
\tat java.base@17.0.19/java.lang.reflect.Method.invoke(Method.java:569)
\tat java.base@17.0.19/java.util.ArrayList.forEach(ArrayList.java:1511)
\tat java.base@17.0.19/java.util.ArrayList.forEach(ArrayList.java:1511)
"""


def test_junit_real_maven_log_extracts_only_the_user_frame() -> None:
    """The verbatim Surefire log yields EXACTLY the user frame, with the
    basename reconstructed to a package-relative path.

    Exact-tuple assertion is load-bearing: the log carries six
    ``org.junit.jupiter.*`` framework frames and three JDK
    module-prefixed frames; any of them leaking into the result is the
    Defect-3 pollution shape (framework files appear in EVERY failing
    test's log, so they would out-score the real file).
    """
    assert parse_failure_log("junit", _REAL_JUNIT_MAVEN_LOG) == (
        ("com/example/CalculatorTest.java", 27),
    )


def test_junit_real_gradle_log_handles_app_classloader_prefix() -> None:
    """Gradle 8.14.5 frames carry an ``app//`` classloader prefix and
    versioned module prefixes (``java.base@17.0.19/``) — the frozen
    wave-1 §S7 regex prescription (no prefix allowance) missed every
    user frame under Gradle. Empirical divergence, recorded in the
    W1/S7 handoff.
    """
    assert parse_failure_log("junit", _REAL_JUNIT_GRADLE_LOG) == (
        ("com/example/CalculatorTest.java", 26),
    )


def test_junit_default_package_frame_yields_bare_basename() -> None:
    """A class in the default package has no package half to fold in."""
    text = "\tat CalculatorTest.testX(CalculatorTest.java:9)"
    assert parse_failure_log("junit", text) == (("CalculatorTest.java", 9),)


def test_junit_nested_class_frame_maps_to_outer_file() -> None:
    """``Outer$Inner`` frames carry the OUTER file's basename; the ``$``
    stays inside the class token so the package half is still correct."""
    text = "\tat com.example.Outer$Inner.testY(Outer.java:5)"
    assert parse_failure_log("junit", text) == (("com/example/Outer.java", 5),)


def test_junit_kotlin_frame_extracts_kt_file() -> None:
    text = "\tat com.example.UtilsKt.helper(Utils.kt:12)"
    assert parse_failure_log("junit", text) == (("com/example/Utils.kt", 12),)


def test_junit_constructor_frame_matches_angle_bracket_method() -> None:
    """``<init>`` / ``<clinit>`` constructor frames are legal methods."""
    text = "\tat com.example.Foo.<init>(Foo.java:3)"
    assert parse_failure_log("junit", text) == (("com/example/Foo.java", 3),)


def test_junit_infra_frames_only_returns_empty() -> None:
    """A log containing ONLY test-infra / JDK frames yields nothing —
    the caller records a parse warning instead of ranking JUnit's own
    source files."""
    text = (
        "\tat org.junit.jupiter.api.AssertEquals.assertEquals(AssertEquals.java:150)\n"
        "\tat org.opentest4j.AssertionFailedError.something(AssertionFailedError.java:10)\n"
        "\tat java.base/java.lang.reflect.Method.invoke(Method.java:569)\n"
        "\tat org.gradle.internal.Worker.run(Worker.java:44)\n"
        "\tat org.apache.maven.surefire.booter.ForkedBooter.main(ForkedBooter.java:495)\n"
    )
    assert parse_failure_log("junit", text) == ()


def test_junit_inline_type_message_reference_has_no_frames() -> None:
    """The normalizer's inline ``"type: message"`` fill (no per-test log
    written) carries no stack frame — parse yields empty, and the caller
    emits the honest "no parseable file:line references" warning."""
    text = "org.opentest4j.AssertionFailedError: expected: <1> but was: <0>"
    assert parse_failure_log("junit", text) == ()


# ---------------------------------------------------------------------------
# xunit (W1/S7, ANA-02)
# ---------------------------------------------------------------------------

# Adapter-written per-test failure log captured VERBATIM on the equipped
# host (2026-07-07): dotnet SDK 8.0 + xunit 2.6 against the
# dotnet-test-basic fixture (workspace path shortened). Note: no
# ``[type]`` block (TRX ``<ErrorInfo>`` has no type element) and the
# framework frames carry NO `` in <path>:line`` clause — the clause is
# emitted only for frames with PDB debug info, i.e. user code.
_REAL_XUNIT_LOG = """\
[message] Assert.Equal() Failure: Values differ
Expected: 5
Actual:   6
[stack]
   at MathLib.Tests.MathTests.TestSubtractIntentionallyFails() in /home/user/ws/MathLib.Tests/MathTests.cs:line 32
   at System.RuntimeMethodHandle.InvokeMethod(Object target, Void** arguments, Signature sig, Boolean isConstructor)
   at System.Reflection.MethodBaseInvoker.InvokeWithNoArgs(Object obj, BindingFlags invokeAttr)
"""


def test_xunit_real_log_extracts_only_the_pdb_frame() -> None:
    """The verbatim TRX-derived log yields exactly the user frame's
    absolute path + line; the two ``System.*`` frames self-exclude
    because they carry no `` in <path>:line`` clause."""
    assert parse_failure_log("xunit", _REAL_XUNIT_LOG) == (
        ("/home/user/ws/MathLib.Tests/MathTests.cs", 32),
    )


def test_xunit_windows_drive_path_extracts() -> None:
    """Windows PDB paths (``C:\\...``) ride the shared drive-prefix
    group from the 2026-06-09 Windows fix."""
    text = r"   at Ns.Cls.M() in C:\Users\r\ws\MathLib.Tests\MathTests.cs:line 32"
    assert parse_failure_log("xunit", text) == (
        (r"C:\Users\r\ws\MathLib.Tests\MathTests.cs", 32),
    )


def test_xunit_fsharp_and_vb_extensions_extract() -> None:
    text = (
        "   at Lib.Tests.T.A() in /ws/Lib.Tests/Tests.fs:line 8\n"
        "   at Lib.Tests.T.B() in /ws/Lib.Tests/Tests.vb:line 4\n"
    )
    assert parse_failure_log("xunit", text) == (
        ("/ws/Lib.Tests/Tests.fs", 8),
        ("/ws/Lib.Tests/Tests.vb", 4),
    )


def test_xunit_no_match_returns_empty() -> None:
    """Inline ``"type: message"`` fills (empty TRX ``<ErrorInfo>``) have
    no ``in <path>:line`` clause — parse yields empty."""
    text = "System.InvalidOperationException: Sequence contains no elements"
    assert parse_failure_log("xunit", text) == ()


# ---------------------------------------------------------------------------
# resolve_failure_text — engine routing (W1/S7 hybrid branch)
# ---------------------------------------------------------------------------


_RUN_ID = "01HFP000000000000000000001"


def _make_store(tmp_path: Path) -> ProjectStore:
    """Materialize an empty Project Store handle (no Run Record needed —
    ``resolve_failure_text`` only reads ``store.path``)."""
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    create_project_store(workspace)
    return get_project_store_state(workspace / ".novetest")


def _write_failure_log(store: ProjectStore, relative: str, content: str) -> Path:
    """Write ``content`` at ``<store>/run/artifacts/run_<id>/<relative>``."""
    log_path = store.path / "run" / "artifacts" / f"run_{_RUN_ID}" / relative
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(content, encoding="utf-8")
    return log_path


def test_resolve_inline_engines_return_reference_verbatim(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    for engine in ("pytest", "jest"):
        assert (
            resolve_failure_text(store, _RUN_ID, engine, "src/foo.py:5: boom")
            == "src/foo.py:5: boom"
        )


def test_resolve_logfile_engine_reads_log_file(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _write_failure_log(store, "native/failures/t.log", "panicked at src/lib.rs:3:1")
    assert (
        resolve_failure_text(store, _RUN_ID, "cargo-test", "native/failures/t.log")
        == "panicked at src/lib.rs:3:1"
    )


def test_resolve_logfile_engine_missing_file_returns_empty(tmp_path: Path) -> None:
    """cargo/go keep their pre-S7 semantics: a reference that does not
    resolve to a file yields ``""`` (NOT the reference string) — those
    normalizers never fill inline text."""
    store = _make_store(tmp_path)
    assert (
        resolve_failure_text(store, _RUN_ID, "go-test", "native/failures/gone.log")
        == ""
    )


def test_resolve_hybrid_log_path_fill_reads_file(tmp_path: Path) -> None:
    """junit/xunit PRIMARY fill: an artifact-dir-relative log path."""
    store = _make_store(tmp_path)
    _write_failure_log(store, "native/failures/j.log", _REAL_JUNIT_MAVEN_LOG)
    for engine in ("junit", "xunit"):
        assert (
            resolve_failure_text(store, _RUN_ID, engine, "native/failures/j.log")
            == _REAL_JUNIT_MAVEN_LOG
        )


def test_resolve_hybrid_inline_fill_returns_reference(tmp_path: Path) -> None:
    """junit/xunit FALLBACK fill: the normalizer's inline
    ``"type: message"`` join when no per-test log was written."""
    store = _make_store(tmp_path)
    inline = "org.opentest4j.AssertionFailedError: expected: <1> but was: <0>"
    assert resolve_failure_text(store, _RUN_ID, "junit", inline) == inline


def test_resolve_hybrid_pathlike_inline_string_returns_inline(tmp_path: Path) -> None:
    """Contract edge (task brief §Data contracts): an inline string that
    SUPERFICIALLY looks path-like — e.g. an exception message quoting a
    file path — must come back as inline text, not degrade to ``""``.
    This is the deliberate divergence from cargo/go's
    return-empty-on-missing semantics."""
    store = _make_store(tmp_path)
    pathlike = "System.IO.FileNotFoundException: Could not find file 'native/failures/data.json'"
    assert resolve_failure_text(store, _RUN_ID, "xunit", pathlike) == pathlike
    # Even a string that IS exactly the artifact-relative log-path shape
    # resolves inline when no such file exists on disk.
    ghost = "native/failures/never_written.log"
    assert resolve_failure_text(store, _RUN_ID, "junit", ghost) == ghost


def test_resolve_hybrid_unreadable_existing_file_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An EXISTING but unreadable log file yields ``""`` (same posture as
    cargo/go) — NOT the inline fallback: the reference was genuinely a
    path, so feeding the path string to the parser would be wrong."""
    store = _make_store(tmp_path)
    _write_failure_log(store, "native/failures/locked.log", "content")

    def raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("simulated permission error")

    monkeypatch.setattr(Path, "read_text", raise_oserror)
    assert (
        resolve_failure_text(store, _RUN_ID, "junit", "native/failures/locked.log")
        == ""
    )


def test_resolve_hybrid_nul_byte_reference_does_not_crash(tmp_path: Path) -> None:
    """A NUL byte in inline text makes ``Path.is_file`` raise
    ``ValueError`` — the existence probe swallows it and the hybrid
    branch returns the inline text (best-effort: never crash on
    adapter-shaped data)."""
    store = _make_store(tmp_path)
    inline = "SomeException: weird \x00 payload"
    assert resolve_failure_text(store, _RUN_ID, "junit", inline) == inline


def test_resolve_unknown_engine_returns_empty(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    assert (
        resolve_failure_text(store, _RUN_ID, "seventh-engine", "anything")
        == ""
    )


def test_resolve_empty_reference_returns_empty(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    for engine in ("pytest", "jest", "cargo-test", "go-test", "junit", "xunit"):
        assert resolve_failure_text(store, _RUN_ID, engine, None) == ""
        assert resolve_failure_text(store, _RUN_ID, engine, "") == ""
