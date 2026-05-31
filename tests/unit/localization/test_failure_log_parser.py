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

The parser is **best-effort**: a regex that finds nothing returns the
empty tuple. The parser MUST NOT crash on malformed input; it MUST
deduplicate ``(file, line)`` tuples within a single failure log so a
file mentioned at the same line in multiple stack frames counts once.
"""

from __future__ import annotations

from novetest.localization.failure_proximity import parse_failure_log


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
