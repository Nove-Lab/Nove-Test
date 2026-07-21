"""Shared CLI transport seams (W3/S47, ORC-01).

The thin, verb-agnostic plumbing every ``cli/handlers/*`` command routes
through: the active output-mode state + ``_emit_and_exit`` emitter, the
workspace-resolution seam (``_require_store``), the run_id-addressed lookup
helpers (``_resolve_run_reference`` / ``_lookup_miss_exit``), the flag
validators, and the run/test execution-exception mapper. Extracted verbatim
from ``cli/app.py`` at the S47 decomposition so the per-verb handlers can bind
these seams without importing the Cyclopts registration surface (breaking the
``app.py`` -> ``handlers`` -> ``app.py`` cycle a direct import would create).

Pure motion: byte-for-byte identical behavior to the pre-S47 ``cli/app.py``
inlined seams; the wire contract is unchanged. ``cli/app.py`` re-exports the
symbols other modules / tests import by name (e.g. ``_map_execution_exception``).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, NoReturn

from novetest.cli.output import (
    EXIT_ENGINE_MISSING,
    EXIT_STORAGE,
    EXIT_USAGE,
    Envelope,
    EnvelopeError,
    EnvelopeWarning,
    OutputMode,
    emit_envelope,
)
from novetest.memory import (
    RUN_ID_NOT_FOUND_MESSAGE,
    ProjectStore,
    ProjectStoreCorruptError,
    SkippedRecord,
    find_entry_by_run_id,
)
from novetest.models import RunReference
from novetest.orchestration.anchor_resolution import (
    EngineAmbiguousError,
    WorkspaceEngineUndetectedError,
    resolve_workspace,
)
from novetest.run import (
    AdapterInvocationError,
    AdapterWarning,
    EngineCandidate,
    EngineNotReadyError,
    RunEngineError,
    list_supported_engine_pairs,
)


# ---------------------------------------------------------------------------
# Active output mode + envelope emit
# ---------------------------------------------------------------------------


_active_mode: OutputMode = OutputMode.JSON


def set_active_mode(mode: OutputMode) -> None:
    """Pin the process-wide output mode resolved by ``main`` (entrypoint)."""
    global _active_mode
    _active_mode = mode


def _emit_and_exit(envelope: Envelope, code: int) -> NoReturn:
    emit_envelope(envelope, _active_mode)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Envelope helpers
# ---------------------------------------------------------------------------


def _uninitialized(command: str) -> Envelope:
    return Envelope(
        command=command,
        ok=False,
        errors=(
            EnvelopeError(
                code="uninitialized",
                message=(
                    "No Project Store found in this directory or any ancestor. "
                    "Run `novetest init` to create one."
                ),
            ),
        ),
    )


def _store_corrupt_envelope(
    command: str,
    message: str,
    warnings: tuple[EnvelopeWarning, ...] = (),
) -> Envelope:
    """The ``store-corrupt`` error envelope (emitted with ``EXIT_STORAGE``).

    One shape for every storage-corruption surface: the workspace-resolution
    seam (``_require_store``), ``init``/``reset``'s store readers, and the
    S42 run-record corruption paths — residual loud targeted reads plus the
    Q1-A addressed-lookup escalation. The message carries the corrupt file's
    path verbatim (same operator doctrine as ``corrupt-run-record-skipped``).
    """
    return Envelope(
        command=command,
        ok=False,
        errors=(EnvelopeError(code="store-corrupt", message=message),),
        warnings=warnings,
    )


def _lookup_miss_exit(
    command: str,
    run_id: str,
    skipped: list[SkippedRecord],
    warnings: tuple[EnvelopeWarning, ...] = (),
) -> NoReturn:
    """Exit for a run_id-addressed lookup miss: ``not-found`` — unless corrupt.

    Gate-1 Q1 Option A (S42 / XCT-03): when the miss is really a
    corrupt-on-disk record (a ``SkippedRecord`` whose ``run_id`` matches the
    requested id), ``not-found`` would be dishonest — the run EXISTS but its
    storage is unreadable, and the "re-run / wrong id" remediation that
    ``not-found`` steers agents toward cannot help. That case escalates to
    ``store-corrupt`` / exit 5 with the skipped record's path-bearing error.
    Genuinely-absent ids keep ``not-found`` / exit 2; list-scan verbs keep
    S41's skip+warning behavior (this helper only fires on addressed misses).
    """
    corrupt = next((s for s in skipped if s.run_id == run_id), None)
    if corrupt is not None:
        # `error` is normally already path-bearing (the S42 typed wrap);
        # the fallback keeps the path doctrine for raw skip classes
        # (e.g. a UnicodeDecodeError message names no file).
        message = (
            corrupt.error
            if str(corrupt.path) in corrupt.error
            else f"Corrupt run record at {corrupt.path}: {corrupt.error}"
        )
        _emit_and_exit(
            _store_corrupt_envelope(command, message, warnings=warnings),
            EXIT_STORAGE,
        )
    _emit_and_exit(
        Envelope(
            command=command,
            ok=False,
            errors=(
                EnvelopeError(
                    code="not-found",
                    message=RUN_ID_NOT_FOUND_MESSAGE.format(run_id=run_id),
                ),
            ),
            warnings=warnings,
        ),
        EXIT_USAGE,
    )


def _require_store(command: str) -> ProjectStore:
    """Resolve the governing Project Store for a verb (anchored-pin D2).

    THE single workspace-resolution seam every verb routes through: wraps
    ``orchestration.anchor_resolution.resolve_workspace`` (upward walk to the
    nearest ``.novetest/``). Since the S19 seam split (D1=A / D2=A) this seam
    performs NO engine-pin migration — a legacy pre-pin store returns with
    ``pinned_engine is None`` and read-only verbs proceed engine-less over
    it. Pin backfill / the ``engine-ambiguous`` refusal now happen only on
    the execution path (``run`` / ``test`` via ``resolve_execution_engine``);
    hence this helper no longer catches ``EngineAmbiguousError`` — it is
    unreachable from ``resolve_workspace``.
    """
    try:
        store = asyncio.run(resolve_workspace(Path.cwd()))
    except ProjectStoreCorruptError as exc:
        _emit_and_exit(_store_corrupt_envelope(command, str(exc)), EXIT_STORAGE)
    if store is None:
        _emit_and_exit(_uninitialized(command), EXIT_USAGE)
    return store


def _engine_candidates_payload(
    candidates: tuple[EngineCandidate, ...],
) -> list[dict[str, str]]:
    """Project marker-level engine candidates onto the D7 ``data.candidates`` shape.

    Same three-key shape (``path`` / ``ecosystem`` / ``engine_name``) as the
    ``no-engine-detected`` discovery report, so agents parse one candidate
    schema across both error codes. ``path`` is ``"."`` here — ambiguity is
    always about the anchor/init directory itself.
    """
    return [
        {"path": ".", "ecosystem": c.ecosystem, "engine_name": c.engine_name}
        for c in candidates
    ]


def _validate_engine_flag(command: str, engine: str | None) -> tuple[str, str] | None:
    """Map ``--engine <name>`` onto its ``(ecosystem, engine_name)`` pair.

    ``None`` passes through (flag absent). Values outside the six-engine
    matrix fail flag validation (``invalid-flag``, exit 2) — mirroring the
    ``--formula`` pattern: a bad flag is a transport error, so the workflow
    layer never sees it (decision 2026-07-03-engine-selection-policy D1/D7).
    """
    if engine is None:
        return None
    for ecosystem, engine_name in list_supported_engine_pairs():
        if engine_name == engine:
            return (ecosystem, engine_name)
    supported = sorted(name for _, name in list_supported_engine_pairs())
    _emit_and_exit(
        Envelope(
            command=command,
            ok=False,
            errors=(
                EnvelopeError(
                    code="invalid-flag",
                    message=(
                        f"Invalid --engine={engine!r}; "
                        f"expected one of {supported!r}"
                    ),
                ),
            ),
        ),
        EXIT_USAGE,
    )


def _readiness_payload(readiness: Any) -> dict[str, Any]:
    ctx = readiness.engine_context
    return {
        "state": readiness.state,
        "engine": ctx.engine_name if ctx is not None else None,
        "ecosystem": ctx.ecosystem if ctx is not None else None,
        "engine_version": ctx.engine_version if ctx is not None else None,
        "evidence": list(readiness.evidence),
        "issues": list(readiness.issues),
    }


def _engine_not_ready_code(exc: EngineNotReadyError) -> str:
    """D7 error-code token for an ``EngineNotReadyError`` (W1/S8).

    Readiness states are ALREADY complete wire tokens (``engine-missing``
    / ``engine-misconfigured`` — see ``run/readiness.py``), so the code is
    the state itself, never a prefixed composite (ORC-03: the old
    ``f"engine-{state}"`` emitted ``engine-engine-missing``). The
    markerless branch — orchestration's ``WorkspaceEngineUndetectedError``,
    raised only when a pin-less store's anchor has no engine marker at
    all — maps to the D7 standard ``no-engine-detected``, matching
    ``init`` / ``reset`` (ORC-23). Shared by ``run_cmd`` and ``test_cmd``
    so the two verbs cannot drift.
    """
    if isinstance(exc, WorkspaceEngineUndetectedError):
        return "no-engine-detected"
    return exc.readiness.state


def _map_execution_exception(
    command: str, exc: EngineAmbiguousError | RunEngineError
) -> tuple[Envelope, int]:
    """Single source of truth for run/test execution-exception → (envelope, exit).

    ORC-02 (dedup) + ORC-21 (structural fallback for the RunEngineError family).
    ``run_cmd`` and ``test_cmd`` used to carry a verbatim-duplicated three-block
    ``except`` tree; both now collapse to one
    ``except (EngineAmbiguousError, RunEngineError)`` that calls this helper,
    threading ``command`` (``"run"`` / ``"test"``) into every envelope so the two
    verbs cannot drift (the ORC-03 doubled-prefix bug was born of exactly such a
    copy-paste pair).

    ``isinstance`` order is load-bearing: ``WorkspaceEngineUndetectedError`` is an
    ``EngineNotReadyError`` subclass, so it must reach the readiness branch (where
    ``_engine_not_ready_code`` maps it to the D7 ``no-engine-detected`` token).

    - ``EngineAmbiguousError`` (post-S19, the primary legacy + ambiguous
      refusal: ``resolve_execution_engine`` raises it when an execution verb
      finds a pin-less store whose anchor matches multiple engines —
      ``resolve_workspace`` no longer migrates, so reads never reach it) →
      ``engine-ambiguous`` + ``data.candidates``, exit 2.
    - ``EngineNotReadyError`` → ``data.engine_readiness`` + the D7 readiness token,
      exit 4.
    - ``AdapterInvocationError`` → ``adapter-<kind>`` (``install_hint`` in
      ``details`` when present), exit 4 — EXCEPT ``kind == "invalid-target"``,
      which is a caller usage error (a dash-/flag-/metachar-shaped target) and
      maps to exit 2 (``EXIT_USAGE``), not the engine-missing class
      (``decisions/2026-07-09-adapter-invalid-target-exit-code-reclassification.md``).
      The error-code STRING (``adapter-invalid-target``) and the envelope shape
      are unchanged; only this one kind's exit code differs.
    - **ORC-21 structural fallback** — any OTHER ``RunEngineError`` subclass
      (today only ``EngineNotSupportedError``, which is UNREACHABLE from these
      verbs — every supported pair has both a marker-table entry and an
      ``_invoke_adapter`` branch, and ``--engine`` is validated upstream) → a
      structured ``engine-not-supported`` envelope at exit 4, NOT a fall-through
      to the generic exit-1 ``cli-error`` handler that would drop the verb name
      and the structured engine-missing exit. Defensive today; the guard is what
      keeps a future 7th engine / new subclass structured.
    """
    if isinstance(exc, EngineAmbiguousError):
        return (
            Envelope(
                command=command,
                ok=False,
                data={"candidates": _engine_candidates_payload(exc.candidates)},
                errors=(EnvelopeError(code="engine-ambiguous", message=str(exc)),),
            ),
            EXIT_USAGE,
        )
    if isinstance(exc, EngineNotReadyError):
        return (
            Envelope(
                command=command,
                ok=False,
                data={"engine_readiness": _readiness_payload(exc.readiness)},
                errors=(
                    EnvelopeError(
                        code=_engine_not_ready_code(exc),
                        message=str(exc),
                    ),
                ),
            ),
            EXIT_ENGINE_MISSING,
        )
    if isinstance(exc, AdapterInvocationError):
        # ``invalid-target`` (a dash-/flag-/metachar-shaped target rejected at
        # the adapter boundary) is a caller USAGE error → exit 2, not the
        # engine-missing class; every other adapter kind stays exit 4. Only the
        # exit code differs — the error-code string and envelope shape are
        # unchanged (2026-07-09 reclassification decision).
        adapter_exit = (
            EXIT_USAGE if exc.kind == "invalid-target" else EXIT_ENGINE_MISSING
        )
        return (
            Envelope(
                command=command,
                ok=False,
                errors=(
                    EnvelopeError(
                        code=f"adapter-{exc.kind}",
                        message=str(exc),
                        details=(
                            {"install_hint": exc.install_hint}
                            if exc.install_hint is not None
                            else {}
                        ),
                    ),
                ),
            ),
            adapter_exit,
        )
    return (
        Envelope(
            command=command,
            ok=False,
            errors=(EnvelopeError(code="engine-not-supported", message=str(exc)),),
        ),
        EXIT_ENGINE_MISSING,
    )


def _adapter_to_envelope_warnings(
    warnings: tuple[AdapterWarning, ...],
) -> tuple[EnvelopeWarning, ...]:
    """Project ``AdapterWarning`` records onto ``EnvelopeWarning`` records.

    Per
    ``decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md``
    §"Option C follow-up slice scope" criterion #3, the two dataclasses
    are structurally compatible — same three fields ``code`` / ``message``
    / ``details``. The conversion is a field-by-field copy at the CLI
    boundary so the orchestration layer never imports from ``cli/output.py``
    (the existing dependency direction is ``cli → orchestration → run``;
    inverting it would introduce a cycle).

    Empty input is the common case (non-warning runs across all six
    adapters) — return an empty tuple unchanged.
    """
    if not warnings:
        return ()
    return tuple(
        EnvelopeWarning(code=w.code, message=w.message, details=dict(w.details))
        for w in warnings
    )


def _resolve_run_reference(
    store: ProjectStore, command: str, run_id: str
) -> RunReference:
    """Look up a Memory Entry by run_id and return its Run Reference.

    Mirrors the lookup pattern used by ``memory_show`` / ``memory_delete``
    so run_id-addressed verbs surface the same ``not-found`` envelope
    (exit 2) for stale or fake ids — and the same S42 ``store-corrupt``
    escalation (exit 5) when the requested id names a corrupt-on-disk
    record the isolated scan skipped (Gate-1 Q1 Option A). The ``skipped``
    collector here feeds only that corrupt-match check — warnings stay
    memory-verb-only (S41's deliberate transport choice).
    """
    skipped: list[SkippedRecord] = []
    target = find_entry_by_run_id(store, run_id, skipped=skipped)
    if target is None:
        _lookup_miss_exit(command, run_id, skipped)
    return target.run_record.run_reference
