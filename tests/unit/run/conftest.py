"""Shared fixtures for `tests/unit/run/`."""

from __future__ import annotations

from pathlib import Path

import pytest


FIXTURE_PROJECTS_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "projects"
)


@pytest.fixture
def basic_workspace() -> Path:
    return FIXTURE_PROJECTS_ROOT / "pytest-basic"


@pytest.fixture
def failing_workspace() -> Path:
    return FIXTURE_PROJECTS_ROOT / "pytest-failing"


@pytest.fixture
def empty_workspace() -> Path:
    return FIXTURE_PROJECTS_ROOT / "empty-no-engine"


@pytest.fixture
def coverage_workspace() -> Path:
    return FIXTURE_PROJECTS_ROOT / "pytest-coverage"


@pytest.fixture
def jest_basic_workspace() -> Path:
    return FIXTURE_PROJECTS_ROOT / "jest-basic"


@pytest.fixture
def jest_basic_coverage_workspace() -> Path:
    return FIXTURE_PROJECTS_ROOT / "jest-basic-coverage"


@pytest.fixture
def gotest_basic_workspace() -> Path:
    return FIXTURE_PROJECTS_ROOT / "gotest-basic"


@pytest.fixture
def gotest_basic_coverage_workspace() -> Path:
    return FIXTURE_PROJECTS_ROOT / "gotest-basic-coverage"


@pytest.fixture
def cargo_test_basic_workspace() -> Path:
    return FIXTURE_PROJECTS_ROOT / "cargo-test-basic"


@pytest.fixture
def cargo_test_basic_coverage_workspace() -> Path:
    return FIXTURE_PROJECTS_ROOT / "cargo-test-basic-coverage"
