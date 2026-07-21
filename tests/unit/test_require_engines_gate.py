"""Self-coverage for the ``NOVETEST_REQUIRE_ENGINES`` engine gate.

The gate lives in the repo test-root ``tests/conftest.py`` (loaded by pytest as
a plugin). Here we import that module a second time under a private name and
exercise its pure helpers plus the real ``pytest_runtest_makereport`` hook
wrapper directly — no ``pytester`` / subprocess and no global plugin change, so
this test cannot perturb the dormant-by-default behavior of the outer suite.

Covered (per the S44 brief): (a) dormant-by-default, (b) promotion fires on a
planted engine-gated skip, (c) unknown-token loudness — plus the guard matrix
(unrequired engine / non-matching path / non-skip outcome / xfail are all left
untouched).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_CONFTEST_PATH = Path(__file__).resolve().parents[1] / "conftest.py"


def _load_gate() -> Any:
    spec = importlib.util.spec_from_file_location(
        "_novetest_engine_gate_under_test", _CONFTEST_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def _skipped_report(nodeid: str, reason: str = "requires `go` on PATH") -> pytest.TestReport:
    """Build a realistic skipped report (as `pytest.skip(reason)` would)."""

    path = nodeid.split("::", 1)[0]
    return pytest.TestReport(
        nodeid=nodeid,
        location=(path, 0, nodeid),
        keywords={},
        outcome="skipped",
        longrepr=(path, 12, f"Skipped: {reason}"),
        when="call",
    )


def _drive_makereport(nodeid: str, outcome: str, required: frozenset[str],
                      *, wasxfail: bool = False) -> pytest.TestReport:
    """Run the actual `pytest_runtest_makereport` wrapper against a report."""

    path = nodeid.split("::", 1)[0]
    report = pytest.TestReport(
        nodeid=nodeid,
        location=(path, 0, nodeid),
        keywords={},
        outcome=outcome,
        longrepr=(path, 12, "Skipped: requires `go` on PATH") if outcome == "skipped" else None,
        when="call",
    )
    if wasxfail:
        report.wasxfail = "expected to fail"

    class _FakeConfig:
        # `stash.get(key, default)` is the only surface the wrapper touches; a
        # plain dict satisfies it and keeps the StashKey object as the key.
        stash = {gate._REQUIRED_ENGINES_KEY: required}

    item = type("_FakeItem", (), {"nodeid": nodeid, "config": _FakeConfig()})()

    generator = gate.pytest_runtest_makereport(item, None)
    next(generator)  # advance to the `report = yield`
    try:
        generator.send(report)
    except StopIteration as stop:
        return stop.value
    raise AssertionError("hook wrapper did not return")  # pragma: no cover


# --- (a) dormant-by-default -------------------------------------------------

@pytest.mark.parametrize("raw", [None, "", "   ", ",", " , "])
def test_dormant_when_unset_or_empty(raw: str | None) -> None:
    env = {} if raw is None else {gate.ENV_VAR: raw}
    assert gate.required_engines(env) == frozenset()


def test_dormant_hook_leaves_skip_untouched() -> None:
    report = _drive_makereport(
        "tests/integration/run/test_gotest_basic.py::test_x",
        "skipped",
        required=frozenset(),
    )
    assert report.skipped is True
    assert report.outcome == "skipped"


# --- token parsing ----------------------------------------------------------

def test_parse_strips_dedups_and_ignores_blanks() -> None:
    assert gate.required_engines({gate.ENV_VAR: " pytest , jest ,, jest "}) == frozenset(
        {"pytest", "jest"}
    )


# --- (c) unknown-token loudness ---------------------------------------------

def test_unknown_token_raises_usage_error() -> None:
    with pytest.raises(pytest.UsageError) as excinfo:
        gate.required_engines({gate.ENV_VAR: "pytest,bogus"})
    message = str(excinfo.value)
    assert "bogus" in message
    assert gate.ENV_VAR in message


# --- node id -> engine attribution -----------------------------------------

@pytest.mark.parametrize(
    ("nodeid", "expected"),
    [
        ("tests/integration/run/test_gotest_basic.py::t", "go"),
        ("tests/integration/run/test_cargo_basic.py::t", "cargo"),
        ("tests/integration/run/test_dotnet_basic.py::t", "dotnet"),
        ("tests/integration/run/test_junit_maven.py::t", "junit"),
        ("tests/integration/run/test_jest_basic.py::t", "jest"),
        ("tests/integration/coverage/test_jest_coverage.py::t", "jest"),
        # coverage-dir e2e tests are gated too (the CI dotnet/junit cells
        # exercise their coverage-derive lanes). cargo + dotnet match real
        # files today; junit classifies the coverage team's new test even
        # though it lands in a parallel lane — patterns are classifiers, not
        # existence assertions.
        ("tests/integration/coverage/test_cargo_lcov_e2e.py::t", "cargo"),
        ("tests/integration/coverage/test_dotnet_cobertura_derive.py::t", "dotnet"),
        ("tests/integration/coverage/test_junit_jacoco_derive.py::t", "junit"),
        ("tests/unit/run/test_gotest_adapter.py::t", None),
        ("tests/unit/test_require_engines_gate.py::t", None),
    ],
)
def test_engine_for_nodeid(nodeid: str, expected: str | None) -> None:
    assert gate.engine_for_nodeid(nodeid) == expected


# --- (b) promotion fires ----------------------------------------------------

def test_promotion_flips_skip_to_failure_via_hook() -> None:
    report = _drive_makereport(
        "tests/integration/run/test_gotest_basic.py::test_x",
        "skipped",
        required=frozenset({"go"}),
    )
    assert report.outcome == "failed"
    assert report.skipped is False
    rendered = str(report.longrepr)
    assert "'go'" in rendered
    assert gate.ENV_VAR in rendered
    assert "requires `go` on PATH" in rendered  # original reason preserved


def test_promote_helper_preserves_original_reason() -> None:
    report = _skipped_report(
        "tests/integration/run/test_jest_basic.py::t",
        reason="fixture's `node_modules` not installed",
    )
    gate.promote_skip_to_failure(report, "jest")
    assert report.outcome == "failed"
    assert "fixture's `node_modules` not installed" in str(report.longrepr)


# --- guard matrix: promotion is narrow --------------------------------------

def test_no_promotion_for_unrequired_engine() -> None:
    report = _drive_makereport(
        "tests/integration/run/test_gotest_basic.py::t",
        "skipped",
        required=frozenset({"jest"}),  # go skip, but only jest is required
    )
    assert report.outcome == "skipped"


def test_no_promotion_for_nonmatching_path() -> None:
    report = _drive_makereport(
        "tests/integration/run/test_cargo_basic.py::t",
        "skipped",
        required=frozenset({"go"}),  # cargo path does not match the go pattern
    )
    assert report.outcome == "skipped"


def test_no_promotion_for_passing_test() -> None:
    report = _drive_makereport(
        "tests/integration/run/test_gotest_basic.py::t",
        "passed",
        required=frozenset({"go"}),
    )
    assert report.outcome == "passed"


def test_no_promotion_for_xfail() -> None:
    report = _drive_makereport(
        "tests/integration/run/test_gotest_basic.py::t",
        "skipped",
        required=frozenset({"go"}),
        wasxfail=True,
    )
    assert report.outcome == "skipped"
