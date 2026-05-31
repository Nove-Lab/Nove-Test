"""Parametrized mode-selection per engine using real Run + Coverage seams.

Each scenario picks a fixture + invocation flag → asserts the resulting
Localization mode. Confirms the strategy doc §2 dispatch holds across
the engines we can exercise on this host:

| Scenario | Fixture                       | Coverage?    | Expected mode      |
|----------|-------------------------------|--------------|--------------------|
| A        | localization-branch (pytest)  | yes (--cov)  | sbfl_per_test      |
| B        | localization-no-coverage      | NO           | failure_proximity  |

Path B (sbfl_aggregate) is exercised by ``test_aggregate_mode_e2e.py``
under a cargo skip-guard; we don't duplicate that here because the
parametrized harness would also need the cargo toolchain — splitting
the cargo path into its own file keeps the skip discipline localized.

This test is the canonical "no cross-talk" check: each fixture lands in
its expected mode and nowhere else. A regression that, for example,
flipped Path A's threshold and accidentally routed per-test coverage to
the aggregate path would surface here.
"""

from __future__ import annotations

import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from novetest.localization.derive import derive_localization_findings
from novetest.localization.symbol_resolver import clear_resolver_cache
from novetest.models.localization_finding import LocalizationFinding
from novetest.orchestration.workflows.init import initialize_project_workspace
from novetest.orchestration.workflows.run import run_target_in_store


_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "projects"


class _Scenario(NamedTuple):
    fixture_name: str
    collect_coverage: bool
    expected_mode: str
    expected_confidence: str


_SCENARIOS = [
    _Scenario(
        fixture_name="localization-branch",
        collect_coverage=True,
        expected_mode="sbfl_per_test",
        expected_confidence="high",
    ),
    _Scenario(
        fixture_name="localization-no-coverage",
        collect_coverage=False,
        expected_mode="failure_proximity",
        expected_confidence="low",
    ),
]


def _materialize_fixture(dest: Path, fixture_name: str) -> Path:
    target = dest / fixture_name
    shutil.copytree(
        _FIXTURES_ROOT / fixture_name,
        target,
        ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".novetest"
        ),
    )
    return target


@pytest.mark.parametrize(
    "scenario", _SCENARIOS, ids=[s.fixture_name for s in _SCENARIOS]
)
async def test_mode_selection_routes_to_expected_mode(
    tmp_path: Path, scenario: _Scenario
) -> None:
    """Each scenario lands in its expected (mode, confidence) tuple."""
    workspace = _materialize_fixture(tmp_path, scenario.fixture_name)
    clear_resolver_cache()

    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        "tests/",
        init.store,
        timeout=120.0,
        collect_coverage=scenario.collect_coverage,
    )

    run_reference = outcome.memory_entry.run_record.run_reference
    finding = derive_localization_findings(init.store, run_reference)
    assert isinstance(finding, LocalizationFinding), (
        f"scenario {scenario.fixture_name!r}: expected LocalizationFinding, "
        f"got {finding!r}"
    )
    assert finding.mode == scenario.expected_mode, (
        f"scenario {scenario.fixture_name!r}: expected mode="
        f"{scenario.expected_mode!r}, got {finding.mode!r}"
    )
    assert finding.confidence == scenario.expected_confidence, (
        f"scenario {scenario.fixture_name!r}: expected confidence="
        f"{scenario.expected_confidence!r}, got {finding.confidence!r}"
    )


async def test_per_test_path_does_not_cross_talk_to_aggregate(
    tmp_path: Path,
) -> None:
    """Regression-pinning check: the existing per-test fixture stays in
    Path A and does NOT accidentally hit Path B's helper after the
    fallback-modes slice landed.

    This is the canonical guard against a router bug that flipped the
    granularity check direction. The 2026-05-28 baseline expectation:
    ``localization-branch`` produces ``mode = "sbfl_per_test"`` with
    Ochiai score 1.0 for ``divide`` — the byte-identical assertion the
    existing ``test_localization_branch_basic.py`` makes. We re-assert
    a subset here so a regression in mode routing surfaces in BOTH
    places.
    """
    workspace = _materialize_fixture(tmp_path, "localization-branch")
    clear_resolver_cache()

    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        "tests/", init.store, timeout=120.0, collect_coverage=True
    )

    run_reference = outcome.memory_entry.run_record.run_reference
    finding = derive_localization_findings(init.store, run_reference)
    assert isinstance(finding, LocalizationFinding)
    # Specifically NOT the other two modes.
    assert finding.mode == "sbfl_per_test"
    assert finding.mode != "sbfl_aggregate"
    assert finding.mode != "failure_proximity"
    # sbfl_per_test carries the full 3-element alternate set (NO
    # deviation — only failure_proximity has the empty-tuple deviation).
    assert set(finding.alternate_scores_available) == {"op2", "dstar2", "tarantula"}
