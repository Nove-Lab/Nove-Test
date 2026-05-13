"""Normalize a raw target expression into a Test Target."""

from __future__ import annotations

from pathlib import Path

from novetest.run.types import TestTarget


def resolve_test_target(target_expression: str, workspace_context: Path) -> TestTarget:
    """Classify ``target_expression`` against ``workspace_context``.

    Classification:
    - empty / whitespace → ``workspace`` (run the whole workspace)
    - contains ``::`` → ``nodeid`` (engine-native node identifier)
    - existing directory → ``directory``
    - anything else → ``file`` (the engine will surface its own error if the
      file does not exist; we do not pre-validate to keep parity with the
      native engine's resolution rules)
    """

    expression = target_expression.strip()
    if not expression:
        return TestTarget(
            target_expression="",
            target_type="workspace",
            workspace_path=workspace_context,
        )
    if "::" in expression:
        return TestTarget(
            target_expression=expression,
            target_type="nodeid",
            workspace_path=workspace_context,
        )
    candidate = workspace_context / expression
    if candidate.is_dir():
        return TestTarget(
            target_expression=expression,
            target_type="directory",
            workspace_path=workspace_context,
        )
    return TestTarget(
        target_expression=expression,
        target_type="file",
        workspace_path=workspace_context,
    )
