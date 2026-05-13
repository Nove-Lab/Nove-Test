"""``novetest init`` workflow.

Composes Memory's `create_project_store` with Run's `assess_engine_readiness`
exactly as `design/workflows/orchestration.md` §1 prescribes. Engine
readiness is informational — a missing or misconfigured engine never rolls
back the freshly created Project Store (NFR-RUN-004).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from novetest.memory import ProjectStore, create_project_store
from novetest.run import EngineReadinessResult, assess_engine_readiness


@dataclass(slots=True, frozen=True)
class InitializationResult:
    """Combined onboarding outcome handed back to the CLI / agent caller."""

    store: ProjectStore
    engine_readiness: EngineReadinessResult


async def initialize_project_workspace(workspace_path: Path) -> InitializationResult:
    """Create or recover the Project Store, then probe engine readiness."""

    store = create_project_store(workspace_path)
    readiness = await assess_engine_readiness(workspace_path)
    return InitializationResult(store=store, engine_readiness=readiness)
