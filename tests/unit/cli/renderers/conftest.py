"""Shared deterministic envelope builders for the renderer unit tests.

Every renderer is a pure function over a constructed ``Envelope`` (no engine
invocation needed — the brief §"Verification surface" mandates inline
fixture envelopes), so these builders pin stable run ids / timestamps that
keep the syrupy snapshots reproducible. Exposed as fixtures returning the
builder callables so test modules stay import-path-agnostic.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

RUN_ID = "01TESTRUN000000000000000000"
BASELINE_RUN_ID = "01TESTBASELINE00000000000000"
CREATED_AT = 1700000000000  # 2023-11-14T22:13:20Z
BASELINE_CREATED_AT = 1700000500000  # 2023-11-14T22:21:40Z


def _ref(run_id: str = RUN_ID, created_at: int = CREATED_AT) -> dict[str, Any]:
    return {"schema_version": 1, "run_id": run_id, "created_at": created_at}


@pytest.fixture
def ref() -> Callable[..., dict[str, Any]]:
    return _ref
