"""Top-level workflow compositions consumed by the CLI."""

from novetest.orchestration.workflows.init import (
    InitializationResult,
    initialize_project_workspace,
)
from novetest.orchestration.workflows.inspect import (
    InspectView,
    build_inspect_view,
)
from novetest.orchestration.workflows.run import RunOutcome, run_target_in_store
from novetest.orchestration.workflows.status import StatusView, build_status_view


__all__ = [
    "InitializationResult",
    "InspectView",
    "RunOutcome",
    "StatusView",
    "build_inspect_view",
    "build_status_view",
    "initialize_project_workspace",
    "run_target_in_store",
]
