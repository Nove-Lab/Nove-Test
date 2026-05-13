"""Run engine public surface.

Implements `design/interace-contract/run.md` §1. Phase 1 ships the pytest
adapter only; the other supported (ecosystem, engine) pairs in
`list_supported_engine_pairs` raise ``EngineNotSupportedError`` when
selected for execution.
"""

from novetest.run.engine import execute, execute_with_engine_context
from novetest.run.engine_selector import (
    list_supported_engine_pairs,
    select_native_engine,
)
from novetest.run.errors import (
    AdapterInvocationError,
    EngineNotReadyError,
    EngineNotSupportedError,
    RunEngineError,
)
from novetest.run.normalizer import normalize_native_result
from novetest.run.readiness import (
    assess_engine_readiness,
    detect_engine_candidates,
)
from novetest.run.reference import assign_run_reference
from novetest.run.target_resolver import resolve_test_target
from novetest.run.types import (
    EngineCandidate,
    EngineReadinessResult,
    NativeEngineContext,
    NativeResult,
    TestTarget,
)


__all__ = [
    "AdapterInvocationError",
    "EngineCandidate",
    "EngineNotReadyError",
    "EngineNotSupportedError",
    "EngineReadinessResult",
    "NativeEngineContext",
    "NativeResult",
    "RunEngineError",
    "TestTarget",
    "assess_engine_readiness",
    "assign_run_reference",
    "detect_engine_candidates",
    "execute",
    "execute_with_engine_context",
    "list_supported_engine_pairs",
    "normalize_native_result",
    "resolve_test_target",
    "select_native_engine",
]
