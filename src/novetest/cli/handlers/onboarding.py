"""Onboarding verb handlers: ``init`` / ``reset`` + their refusal builders.

Extracted verbatim from ``cli/app.py`` at the W3/S47 decomposition (ORC-01).
``cli/app.py`` registers ``init`` / ``reset_cmd`` on the Cyclopts ``app`` and
these functions carry the full verb bodies + the D7 refusal-envelope builders
(``_no_engine_detected_envelope`` / ``_engine_ambiguous_envelope`` /
``_reset_refusal_envelope``). Pure motion — the wire contract is unchanged.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

from cyclopts import Parameter

from novetest.cli._shared import (
    _emit_and_exit,
    _engine_candidates_payload,
    _readiness_payload,
    _store_corrupt_envelope,
    _validate_engine_flag,
)
from novetest.cli.output import (
    EXIT_ENGINE_MISSING,
    EXIT_OK,
    EXIT_STORAGE,
    EXIT_USAGE,
    Envelope,
    EnvelopeError,
)
from novetest.memory import ProjectStoreCorruptError
from novetest.orchestration.workflows import (
    InitEngineAmbiguous,
    InitNoEngineDetected,
    initialize_project_workspace,
)
from novetest.run import EngineCandidate


def init(
    *,
    engine: Annotated[str | None, Parameter(name=["--engine"])] = None,
) -> None:
    """Initialize a Project Store in the current working directory.

    Anchors an engine pin per decision
    ``2026-07-03-engine-selection-policy.md`` (D1/D4/D7): exactly one viable
    engine pins automatically; a markerless directory creates NOTHING and
    reports discovered sub-project candidates (``no-engine-detected``,
    exit 4); an ambiguous workspace creates NOTHING and requires
    ``--engine <name>`` (``engine-ambiguous``, exit 2). ``--engine`` is
    optional in all cases and wins over detection; re-running
    ``init --engine <other>`` on an existing store re-pins in place (run
    history retained). Invalid ``--engine`` values fail flag validation
    (``invalid-flag``, exit 2).
    """
    workspace = Path.cwd()
    engine_pair = _validate_engine_flag("init", engine)
    try:
        result = asyncio.run(
            initialize_project_workspace(workspace, engine=engine_pair)
        )
    except FileNotFoundError as exc:
        _emit_and_exit(
            Envelope(
                command="init",
                ok=False,
                errors=(EnvelopeError(code="workspace-missing", message=str(exc)),),
            ),
            EXIT_USAGE,
        )
    except ProjectStoreCorruptError as exc:
        _emit_and_exit(_store_corrupt_envelope("init", str(exc)), EXIT_STORAGE)

    if isinstance(result, InitNoEngineDetected):
        _emit_and_exit(
            _no_engine_detected_envelope("init", workspace, result), EXIT_ENGINE_MISSING
        )
    if isinstance(result, InitEngineAmbiguous):
        _emit_and_exit(
            _engine_ambiguous_envelope("init", result.candidates), EXIT_USAGE
        )

    data: dict[str, Any] = {
        "store_path": str(result.store.path),
        "store_state": result.store.store_state,
        "initialized_at": result.store.initialized_at,
        "engine_readiness": _readiness_payload(result.engine_readiness),
        "pinned_engine": (
            result.store.pinned_engine.to_dict()
            if result.store.pinned_engine is not None
            else None
        ),
    }
    _emit_and_exit(Envelope(command="init", ok=True, data=data), EXIT_OK)


def _no_engine_detected_envelope(
    command: str, workspace: Path, outcome: InitNoEngineDetected
) -> Envelope:
    """D7 ``no-engine-detected`` envelope: nothing created, candidates reported."""
    if outcome.scan_refused:
        guidance = (
            "the candidate discovery scan is refused at a filesystem root or "
            "$HOME (decision D4); cd into your project directory and run "
            "`novetest init` there"
        )
    elif outcome.candidates:
        guidance = (
            "candidate projects were discovered below (data.candidates); "
            "cd into the one you want and run `novetest init` there — "
            "novetest never initializes a directory you are not standing in"
        )
    else:
        guidance = (
            "no candidate projects were found within the bounded discovery "
            "scan (depth <= 2); cd into your project directory and run "
            "`novetest init` there"
        )
    return Envelope(
        command=command,
        ok=False,
        data={
            "candidates": [c.to_dict() for c in outcome.candidates],
            "scan_refused": outcome.scan_refused,
        },
        errors=(
            EnvelopeError(
                code="no-engine-detected",
                message=(
                    f"No supported engine marker found at {workspace}; "
                    f"no Project Store was created. Note: {guidance}."
                ),
            ),
        ),
    )


def _engine_ambiguous_envelope(
    command: str, candidates: tuple[EngineCandidate, ...]
) -> Envelope:
    """D7 ``engine-ambiguous`` envelope: nothing created, explicit choice required."""
    names = ", ".join(c.engine_name for c in candidates)
    return Envelope(
        command=command,
        ok=False,
        data={"candidates": _engine_candidates_payload(candidates)},
        errors=(
            EnvelopeError(
                code="engine-ambiguous",
                message=(
                    f"Multiple viable engines detected ({names}); no Project "
                    "Store was created. Choose one explicitly: "
                    "`novetest init --engine <name>`."
                ),
            ),
        ),
    )


def reset_cmd(
    *,
    confirm: Annotated[bool, Parameter(name=["--confirm"])] = False,
) -> None:
    """Wipe the active Project Store and re-initialize. Requires ``--confirm``.

    Destructive: removes all Run Records, tombstones, and derived engine
    facts under ``.novetest/``, then re-creates a fresh store (equivalent to
    a bare ``novetest init``). The wipe is atomic — a corrupt or in-use store
    is left intact and surfaced as an error rather than half-deleted.
    """
    # The reset workflow + Memory's ``ProjectStoreNotFoundError`` are imported
    # lazily (reads the current symbol at call time → clean monkeypatch
    # isolation in unit tests; mirrors the ``licenses_cmd`` pattern). The
    # exception is on Memory's module path (``novetest.memory.project_store``),
    # NOT re-exported at the package path.
    if not confirm:
        _emit_and_exit(
            Envelope(
                command="reset",
                ok=False,
                errors=(
                    EnvelopeError(
                        code="confirm-required",
                        message=(
                            "`novetest reset` is destructive. "
                            "Pass --confirm to acknowledge."
                        ),
                    ),
                ),
            ),
            EXIT_USAGE,
        )

    from novetest.memory.project_store import ProjectStoreNotFoundError
    from novetest.orchestration.workflows import reset_project_workspace

    workspace = Path.cwd()
    try:
        result = asyncio.run(reset_project_workspace(workspace))
    except ProjectStoreNotFoundError as exc:
        _emit_and_exit(
            Envelope(
                command="reset",
                ok=False,
                errors=(EnvelopeError(code="uninitialized", message=str(exc)),),
            ),
            EXIT_USAGE,
        )
    except ProjectStoreCorruptError as exc:
        _emit_and_exit(_store_corrupt_envelope("reset", str(exc)), EXIT_STORAGE)
    except OSError as exc:
        _emit_and_exit(
            Envelope(
                command="reset",
                ok=False,
                errors=(EnvelopeError(code="store-wipe-failed", message=str(exc)),),
            ),
            EXIT_STORAGE,
        )

    if isinstance(result, (InitNoEngineDetected, InitEngineAmbiguous)):
        # Legacy pin-less store on an anchor with no single engine choice:
        # the workflow refused BEFORE wiping — the store is untouched.
        envelope, exit_code = _reset_refusal_envelope(result)
        _emit_and_exit(envelope, exit_code)

    data: dict[str, Any] = {
        "store_path": str(result.init_result.store.path),
        "store_state": result.init_result.store.store_state,
        "previous_initialized_at": result.wipe_report.previous_initialized_at,
        "initialized_at": result.init_result.store.initialized_at,
        "items_removed": result.wipe_report.items_removed,
        "engine_readiness": _readiness_payload(result.init_result.engine_readiness),
        # ORC-20: reset re-inits, so its envelope names what got pinned —
        # shape identical to init's ``pinned_engine`` (additive, W2/S27).
        "pinned_engine": (
            result.init_result.store.pinned_engine.to_dict()
            if result.init_result.store.pinned_engine is not None
            else None
        ),
    }
    _emit_and_exit(Envelope(command="reset", ok=True, data=data), EXIT_OK)


def _reset_refusal_envelope(
    outcome: InitNoEngineDetected | InitEngineAmbiguous,
) -> tuple[Envelope, int]:
    """``reset`` refusal for a legacy pin-less store (BEFORE any wipe).

    Same D7 codes as ``init`` (``no-engine-detected`` / ``engine-ambiguous``)
    with reset-specific guidance: the store was NOT wiped; pin an engine via
    ``novetest init --engine <name>`` (re-pins in place), then retry.
    """
    followup = (
        "the store was NOT wiped. Run `novetest init --engine <name>` at the "
        "workspace root to pin one (re-pins in place; run history retained), "
        "then retry `novetest reset --confirm`."
    )
    if isinstance(outcome, InitEngineAmbiguous):
        names = ", ".join(c.engine_name for c in outcome.candidates)
        return (
            Envelope(
                command="reset",
                ok=False,
                data={"candidates": _engine_candidates_payload(outcome.candidates)},
                errors=(
                    EnvelopeError(
                        code="engine-ambiguous",
                        message=(
                            "reset refused: this Project Store has no engine "
                            f"pin and the workspace matches multiple engines "
                            f"({names}); " + followup
                        ),
                    ),
                ),
            ),
            EXIT_USAGE,
        )
    return (
        Envelope(
            command="reset",
            ok=False,
            data={
                "candidates": [c.to_dict() for c in outcome.candidates],
                "scan_refused": outcome.scan_refused,
            },
            errors=(
                EnvelopeError(
                    code="no-engine-detected",
                    message=(
                        "reset refused: this Project Store has no engine pin "
                        "and no engine marker was found at the workspace root; "
                        + followup
                    ),
                ),
            ),
        ),
        EXIT_ENGINE_MISSING,
    )
