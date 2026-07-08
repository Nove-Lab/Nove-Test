"""Typed errors surfaced from the Run engine.

`assess_engine_readiness` and `execute` both report adapter-side problems
through the same hierarchy so the CLI can map them to exit-code 4
(``engine missing/misconfigured``) per
`design/implementation-plan/foundations.md` §2.
"""

from __future__ import annotations

from novetest.run.types import EngineReadinessResult


class RunEngineError(Exception):
    """Base class for typed Run-engine errors."""


class EngineNotReadyError(RunEngineError):
    """Readiness check did not produce a ``ready`` state.

    The caller (orchestration / CLI) is expected to translate this into the
    structured envelope and exit code 4 without spawning the adapter.
    """

    def __init__(self, readiness: EngineReadinessResult) -> None:
        engine = (
            readiness.engine_context.engine_name
            if readiness.engine_context is not None
            else "(none detected)"
        )
        super().__init__(f"engine readiness state: {readiness.state} (engine={engine})")
        self.readiness = readiness


class EngineNotSupportedError(RunEngineError):
    """Selected engine is in the supported pairs but has no adapter yet.

    Phase 1 ships only the pytest adapter; selecting jest/junit/go-test/
    cargo-test/xunit raises this so the boundary stays explicit.
    """


class AdapterInvocationError(RunEngineError):
    """The native engine could not be invoked or produced unusable output.

    ``kind`` is a stable machine token (``missing-plugin``, ``missing-engine``,
    ``unparseable-output``, ``timed-out``, ``invalid-target``); the CLI
    projects it to the envelope error code ``adapter-<kind>``.
    ``unparseable-output`` is the invocation-level catch-all (build failures,
    unusable engine output); ``invalid-target`` is raised BEFORE any spawn
    when the target expression would be consumed as an engine flag (see
    ``adapters/_target_guard``). ``install_hint`` is text-only guidance for
    humans / agents — never auto-executed.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        install_hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.install_hint = install_hint
