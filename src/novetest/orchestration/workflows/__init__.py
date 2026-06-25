"""Top-level workflow compositions consumed by the CLI."""

from novetest.orchestration.workflows.init import (
    InitializationResult,
    initialize_project_workspace,
)
from novetest.orchestration.workflows.inspect import (
    InspectView,
    build_inspect_view,
)
from novetest.orchestration.workflows.reset import (
    ResetResult,
    reset_project_workspace,
)
from novetest.orchestration.workflows.run import RunOutcome, run_target_in_store
from novetest.orchestration.workflows.status import StatusView, build_status_view
from novetest.orchestration.workflows.test import (
    TestOutcome,
    build_test_outcome_from_run_id,
    test_target_in_store,
)


__all__ = [
    "InitializationResult",
    "InspectView",
    "ResetResult",
    "RunOutcome",
    "StatusView",
    "TestOutcome",
    "build_inspect_view",
    "build_status_view",
    "build_test_outcome_from_run_id",
    "initialize_project_workspace",
    "reset_project_workspace",
    "run_target_in_store",
    "test_target_in_store",
]
