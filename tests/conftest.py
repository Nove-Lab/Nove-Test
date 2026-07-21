"""Repo test-root conftest — the opt-in engine gate (XCT-08 / XCT-09).

Engine-gated integration tests (`test_jest_*`, `test_gotest_*`, `test_cargo_*`,
`test_dotnet_*`, `test_junit_*`) `pytest.skip` when their native toolchain is
absent. That is the right default on a dev host, but it means a CI lane that is
*supposed* to equip a toolchain can silently lose it (a `setup-node` / `npm
install` step regresses, PATH drift) and the suite stays green — the skip count
just grows and nobody notices (XCT-09's exact failure mode: the only CI-run
native+istanbul coverage path vanishes without a red build).

This module adds an **opt-in** promotion: set the env var
``NOVETEST_REQUIRE_ENGINES`` to a comma-separated list of engine tokens, and any
test that would SKIP because one of those engines' toolchain is missing is
promoted to a FAILURE naming the engine and the original skip reason. Unset or
empty → the hook is DORMANT and the suite behaves byte-identically to today
(this is the default on every dev host and is why nothing here fires unless a
caller opts in).

Matching rule (kept deliberately small and explicit):

- Token vocabulary is fixed: ``pytest, jest, go, cargo, dotnet, junit``. An
  unknown token aborts the session loudly (``pytest.UsageError``) rather than
  being silently absorbed as a typo.
- A test is attributed to an engine purely by its **node id path** via the
  ``ENGINE_TEST_PATTERNS`` map below (e.g. any node id containing
  ``tests/integration/run/test_gotest_`` is a ``go`` test). Node ids use ``/``
  separators on every OS, so the patterns are portable.
- Promotion fires only when: the env var names the engine, the test's node id
  matches that engine's pattern, and the report outcome is ``skipped`` (never an
  ``xfail``). A passing/failing test is never touched; a skip in an *unrequired*
  engine is never touched.

``pytest`` maps to no patterns on purpose: the pytest native engine runs in the
parent interpreter and never skips for a missing toolchain, so a ``pytest``
requirement is always trivially satisfied — it exists to document CI intent.

This file is outside ``[tool.mypy] mypy_path = "src"`` scope, so it is not type
checked; the annotations are kept clean regardless.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import pytest

#: Env var that opts in to skip -> fail promotion. Unset / empty = dormant.
ENV_VAR = "NOVETEST_REQUIRE_ENGINES"

#: The complete, fixed engine-token vocabulary. Anything else is a config error.
VALID_ENGINE_TOKENS: frozenset[str] = frozenset(
    {"pytest", "jest", "go", "cargo", "dotnet", "junit"}
)

#: engine token -> node id substrings that identify a toolchain-gated test for
#: that engine. ``pytest`` is intentionally empty (see module docstring).
ENGINE_TEST_PATTERNS: dict[str, tuple[str, ...]] = {
    "pytest": (),
    "jest": (
        "tests/integration/run/test_jest_",
        "tests/integration/coverage/test_jest_",
    ),
    "go": ("tests/integration/run/test_gotest_",),
    "cargo": (
        "tests/integration/run/test_cargo_",
        "tests/integration/coverage/test_cargo_",
    ),
    "dotnet": (
        "tests/integration/run/test_dotnet_",
        "tests/integration/coverage/test_dotnet_",
    ),
    "junit": (
        "tests/integration/run/test_junit_",
        "tests/integration/coverage/test_junit_",
    ),
}

#: Parsed required-engine set, computed once at configure time.
_REQUIRED_ENGINES_KEY: pytest.StashKey[frozenset[str]] = pytest.StashKey()


def required_engines(environ: Mapping[str, str] | None = None) -> frozenset[str]:
    """Parse + validate ``NOVETEST_REQUIRE_ENGINES``.

    Returns the frozenset of required engine tokens (empty when unset/empty).
    Raises ``pytest.UsageError`` — loudly, with no traceback — if any token is
    outside :data:`VALID_ENGINE_TOKENS`.
    """

    env = os.environ if environ is None else environ
    tokens = [token.strip() for token in env.get(ENV_VAR, "").split(",")]
    tokens = [token for token in tokens if token]
    if not tokens:
        return frozenset()
    unknown = sorted({token for token in tokens if token not in VALID_ENGINE_TOKENS})
    if unknown:
        raise pytest.UsageError(
            f"{ENV_VAR}: unknown engine token(s): {', '.join(unknown)}. "
            f"Valid tokens are: {', '.join(sorted(VALID_ENGINE_TOKENS))}."
        )
    return frozenset(tokens)


def engine_for_nodeid(nodeid: str) -> str | None:
    """Return the engine token a test node id is gated on, or ``None``."""

    for engine, patterns in ENGINE_TEST_PATTERNS.items():
        if any(pattern in nodeid for pattern in patterns):
            return engine
    return None


def _skip_reason(report: pytest.TestReport) -> str:
    """Extract the human-readable skip reason from a skipped report."""

    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2])
    return str(longrepr)


def promote_skip_to_failure(report: pytest.TestReport, engine: str) -> None:
    """Rewrite a skipped ``report`` in place into a loud failure."""

    reason = _skip_reason(report)
    report.outcome = "failed"
    report.longrepr = (
        f"{ENV_VAR} gate: required engine {engine!r} is unavailable, so this "
        f"test SKIPPED instead of running. Original skip reason: {reason}"
    )


def pytest_configure(config: pytest.Config) -> None:
    # Parse (and validate) once. An unknown token aborts the session here.
    config.stash[_REQUIRED_ENGINES_KEY] = required_engines()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):
    report = yield
    required = item.config.stash.get(_REQUIRED_ENGINES_KEY, frozenset())
    if required and report.skipped and not getattr(report, "wasxfail", False):
        engine = engine_for_nodeid(item.nodeid)
        if engine is not None and engine in required:
            promote_skip_to_failure(report, engine)
    return report
