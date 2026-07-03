"""Run engine public surface.

Implements `design/interace-contract/run.md` §1. All six
(ecosystem, engine) pairs in `list_supported_engine_pairs` ship fully
implemented adapters (pytest, jest, junit, go-test, cargo-test, xunit).

Detection happens through `detect_engine_candidates` (init-time marker
scan, canonical priority order) and `probe_engine` (readiness of one
explicitly named engine — the store pin or a transient override), per
the anchored-pin model of `decisions/2026-07-03-engine-selection-policy.md`.
`execute` accepts the externally resolved pair via its ``engine``
parameter; ``engine=None`` preserves the legacy auto-detect path until
Orchestration wires pins through every caller.

Adapter entry points (``run_pytest``, ``run_jest``, ...) are deliberately
not re-exported here — the public Run surface is engine-agnostic.
Callers route through `execute` / `execute_with_engine_context`.
"""

from novetest.run.engine import execute, execute_with_engine_context
from novetest.run.engine_selector import (
    detect_engine_candidates,
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
from novetest.run.readiness import assess_engine_readiness, probe_engine
from novetest.run.reference import assign_run_reference
from novetest.run.target_resolver import resolve_test_target
from novetest.run.types import (
    AdapterWarning,
    EngineCandidate,
    EngineReadinessResult,
    NativeEngineContext,
    NativeResult,
    TestTarget,
)


__all__ = [
    "AdapterInvocationError",
    "AdapterWarning",
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
    "probe_engine",
    "resolve_test_target",
    "select_native_engine",
]
