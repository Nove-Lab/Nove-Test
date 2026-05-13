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
