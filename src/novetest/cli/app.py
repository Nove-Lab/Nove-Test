from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn

from cyclopts import App, Parameter

from novetest import __version__
from novetest.cli.handlers.test import build_test_envelope
from novetest.cli.output import (
    EXIT_ENGINE_MISSING,
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_STORAGE,
    EXIT_USAGE,
    Envelope,
    EnvelopeError,
    EnvelopeWarning,
    OutputMode,
    apply_no_color,
    emit_envelope,
    resolve_output_mode,
    run_status_to_ok_exit,
)
from novetest.coverage import (
    compare_coverage_facts,
    get_coverage_facts,
)
from novetest.localization import (
    DEFAULT_FORMULA,
    DEFAULT_TOP_N,
    FORMULAS,
)
from novetest.memory import (
    RUN_ID_NOT_FOUND_MESSAGE,
    ProjectStore,
    ProjectStoreCorruptError,
    RunEvidenceNotFoundError,
    SkippedRecord,
    delete_run_evidence,
    find_entry_by_run_id,
    list_run_history,
    retrieve_run_evidence,
)
from novetest.models import ReplayResult, RunReference
from novetest.orchestration.anchor_resolution import (
    EngineAmbiguousError,
    WorkspaceEngineUndetectedError,
    resolve_workspace,
)
from novetest.orchestration.onboarding.command_surface import describe_command_surface
from novetest.orchestration.onboarding.identity import report_cli_identity
from novetest.orchestration.projection import (
    coverage_delta_payload,
    coverage_outcome_payload,
    localization_outcome_payload,
    regression_outcome_payload,
    replay_outcome_payload,
)
from novetest.orchestration.workflows import (
    CacheRederivedAudit,
    InitEngineAmbiguous,
    InitNoEngineDetected,
    LocalizationAudit,
    build_compare_view,
    build_inspect_view,
    build_status_view,
    derive_latest_localization_with_flag_policy,
    derive_localization_with_flag_policy,
    initialize_project_workspace,
    run_target_in_store,
    test_target_in_store,
)
from novetest.regression import (
    compare_runs,
    derive_latest_regression,
)
from novetest.replay import (
    REASON_ENGINE_NOT_READY,
    REASON_ORIGINAL_NOT_FOUND,
    REASON_TARGET_MISSING,
    ReplayUnavailable,
    replay_run,
)
from novetest.run import (
    AdapterInvocationError,
    AdapterWarning,
    EngineCandidate,
    EngineNotReadyError,
    RunEngineError,
    list_supported_engine_pairs,
)


_SUBCOMMAND_TOKENS: frozenset[str] = frozenset(
    {
        "test",
        "run",
        "memory",
        "coverage",
        "regression",
        "localization",
        "replay",
        "inspect",
        "compare",
        "status",
        "licenses",
        "init",
        "reset",
    }
)

app = App(
    name="novetest",
    version=__version__,
    help="Nove Test - AI-first testing orchestration.",
)

_active_mode: OutputMode = OutputMode.JSON


# ---------------------------------------------------------------------------
# Envelope helpers
# ---------------------------------------------------------------------------


def _emit_and_exit(envelope: Envelope, code: int) -> NoReturn:
    emit_envelope(envelope, _active_mode)
    sys.exit(code)


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


# ---------------------------------------------------------------------------
# Onboarding + operating handlers
# ---------------------------------------------------------------------------


@app.command
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


@app.command(name="reset")
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


@app.command(name="run")
def run_cmd(
    target: str = "",
    *,
    coverage: Annotated[bool, Parameter(name=["--coverage", "-c"])] = False,
    engine: Annotated[str | None, Parameter(name=["--engine"])] = None,
) -> None:
    """Execute the resolved Test Target and persist the Run Record.

    With ``--coverage`` / ``-c``, the run is invoked with coverage
    instrumentation and Coverage's ``derive_coverage_facts`` is called
    after persistence. The resulting fact-set (or an explicit
    ``CoverageUnavailable`` outcome) is reported under the envelope's
    ``data.coverage_outcome`` block; without the flag, the key is omitted
    entirely so non-coverage runs stay byte-equivalent to Phase 1.

    ``--engine <name>`` executes a one-off override of the store's pinned
    engine WITHOUT re-pinning (decision 2026-07-03-engine-selection-policy
    D3); invalid names fail flag validation (``invalid-flag``, exit 2).
    """
    store = _require_store("run")
    engine_pair = _validate_engine_flag("run", engine)
    try:
        outcome = asyncio.run(
            run_target_in_store(
                target, store, collect_coverage=coverage, engine=engine_pair
            )
        )
    except (EngineAmbiguousError, RunEngineError) as exc:
        # ORC-02/ORC-21: one shared mapping for both verbs. Since the S19 seam
        # split ``resolve_workspace`` no longer migrates, so ``EngineAmbiguous``
        # now surfaces here as the PRIMARY path — ``resolve_execution_engine``
        # (called first in the workflow, before any subprocess) raises it on a
        # legacy + ambiguous store. The RunEngineError family (EngineNotReady /
        # AdapterInvocation / the structural fallback) maps to its structured
        # exit here.
        _emit_and_exit(*_map_execution_exception("run", exc))
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (the workflow's post-persist refresh /
        # coverage derive found the just-written record corrupt — TOCTOU):
        # a storage failure, not a cli-error.
        _emit_and_exit(_store_corrupt_envelope("run", str(exc)), EXIT_STORAGE)

    entry = outcome.memory_entry
    record = entry.run_record
    # Single shared status→(ok, exit) mapping — see run_status_to_ok_exit
    # (W1/S8, ORC-04): failed AND errored are user results at exit 3.
    ok, exit_code = run_status_to_ok_exit(record.status)

    data: dict[str, Any] = {"memory_entry": entry.to_dict()}
    if outcome.coverage_outcome is not None:
        data["coverage_outcome"] = coverage_outcome_payload(outcome.coverage_outcome)
    envelope_warnings = _adapter_to_envelope_warnings(outcome.warnings)
    _emit_and_exit(
        Envelope(command="run", ok=ok, data=data, warnings=envelope_warnings),
        exit_code,
    )


@app.command
def status() -> None:
    """Summarize the current Project Store: latest run + sub-report availability."""
    store = _require_store("status")
    try:
        view = build_status_view(store)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (the view's cache-only readers do targeted
        # reads via retrieve_run_evidence — TOCTOU): exit 5.
        _emit_and_exit(_store_corrupt_envelope("status", str(exc)), EXIT_STORAGE)
    _emit_and_exit(
        Envelope(command="status", ok=True, data=view.to_dict()),
        EXIT_OK,
    )


@app.command(name="licenses")
def licenses_cmd(
    *,
    full: Annotated[bool, Parameter(name=["--full"])] = False,
) -> None:
    """List third-party components Nove Test redistributes or links to.

    With ``--full``, the envelope also carries the verbatim NOTICES.md text
    body in ``data.notices_text`` (the complete attribution document, ~15 KB).
    Without it, ``data`` carries the compact 5-component summary list only.
    """
    from novetest.orchestration.licenses import build_licenses_view

    try:
        view = build_licenses_view(include_full=full)
    except LookupError as exc:
        _emit_and_exit(
            Envelope(
                command="licenses",
                ok=False,
                errors=(EnvelopeError(code="notices-unavailable", message=str(exc)),),
            ),
            EXIT_GENERIC,
        )
    _emit_and_exit(
        Envelope(command="licenses", ok=True, data=view.to_dict()),
        EXIT_OK,
    )


# ---------------------------------------------------------------------------
# Memory subcommand group
# ---------------------------------------------------------------------------


memory_app = App(name="memory", help="Memory commands: list / show / delete run evidence.")
app.command(memory_app)


def _corrupt_record_warnings(
    skipped: list[SkippedRecord],
) -> tuple[EnvelopeWarning, ...]:
    """Project MEM-05 scan skips onto envelope ``warnings[]`` entries.

    One warning per skipped record; the message carries the corrupt file's
    path verbatim so an operator can locate it without grepping. Emitted only
    by the memory verbs — non-CLI consumers of the scan interfaces get the
    isolation (skip, don't crash) without a warning channel.
    """
    return tuple(
        EnvelopeWarning(
            code="corrupt-run-record-skipped",
            message=f"Skipped unreadable run record at {s.path}: {s.error}",
            details={"path": str(s.path)},
        )
        for s in skipped
    )


@memory_app.command(name="list")
def memory_list() -> None:
    """List Run History newest-first."""
    store = _require_store("memory.list")
    skipped: list[SkippedRecord] = []
    entries = list_run_history(store, skipped=skipped)
    _emit_and_exit(
        Envelope(
            command="memory.list",
            ok=True,
            data={
                "count": len(entries),
                "entries": [e.to_dict() for e in entries],
            },
            warnings=_corrupt_record_warnings(skipped),
        ),
        EXIT_OK,
    )


@memory_app.command(name="show")
def memory_show(run_id: str) -> None:
    """Show the Memory Entry for ``run_id`` (live or tombstoned)."""
    store = _require_store("memory.show")
    skipped: list[SkippedRecord] = []
    target = find_entry_by_run_id(store, run_id, skipped=skipped)
    warnings = _corrupt_record_warnings(skipped)
    if target is None:
        # Q1-A: a miss on an id the scan skipped-as-corrupt escalates to
        # store-corrupt / exit 5; genuinely-absent ids stay not-found.
        _lookup_miss_exit("memory.show", run_id, skipped, warnings=warnings)
    ref = target.run_record.run_reference
    try:
        entry = retrieve_run_evidence(store, ref)
    except RunEvidenceNotFoundError as exc:
        _emit_and_exit(
            Envelope(
                command="memory.show",
                ok=False,
                errors=(EnvelopeError(code="not-found", message=str(exc)),),
                warnings=warnings,
            ),
            EXIT_USAGE,
        )
    except ProjectStoreCorruptError as exc:
        # Residual loud path (scan hit, then the targeted read found the
        # record corrupt — TOCTOU): typed storage error → exit 5.
        _emit_and_exit(
            _store_corrupt_envelope("memory.show", str(exc), warnings=warnings),
            EXIT_STORAGE,
        )
    _emit_and_exit(
        Envelope(
            command="memory.show",
            ok=True,
            data={"memory_entry": entry.to_dict()},
            warnings=warnings,
        ),
        EXIT_OK,
    )


@memory_app.command(name="delete")
def memory_delete(run_id: str) -> None:
    """Tombstone the Memory Entry for ``run_id`` (POSIX-atomic rename)."""
    store = _require_store("memory.delete")
    skipped: list[SkippedRecord] = []
    target = find_entry_by_run_id(store, run_id, skipped=skipped)
    warnings = _corrupt_record_warnings(skipped)
    if target is None:
        # Q1-A: a corrupt record CANNOT be tombstoned (tombstoning re-writes
        # the parsed record) — exit 5 with the path is the honest outcome;
        # manual removal of the named run dir is the recovery (docs).
        _lookup_miss_exit("memory.delete", run_id, skipped, warnings=warnings)
    ref = RunReference(
        run_id=target.run_record.run_reference.run_id,
        created_at=target.run_record.run_reference.created_at,
    )
    try:
        entry = delete_run_evidence(store, ref)
    except RunEvidenceNotFoundError as exc:
        _emit_and_exit(
            Envelope(
                command="memory.delete",
                ok=False,
                errors=(EnvelopeError(code="not-found", message=str(exc)),),
                warnings=warnings,
            ),
            EXIT_USAGE,
        )
    except ProjectStoreCorruptError as exc:
        # Residual loud path (record turned corrupt between scan and the
        # tombstone's own targeted read — TOCTOU): exit 5, nothing mutated.
        _emit_and_exit(
            _store_corrupt_envelope("memory.delete", str(exc), warnings=warnings),
            EXIT_STORAGE,
        )
    _emit_and_exit(
        Envelope(
            command="memory.delete",
            ok=True,
            data={"memory_entry": entry.to_dict()},
            warnings=warnings,
        ),
        EXIT_OK,
    )


# ---------------------------------------------------------------------------
# Coverage subcommand group
# ---------------------------------------------------------------------------


coverage_app = App(
    name="coverage",
    help="Coverage commands: show / diff Coverage Facts for stored runs.",
)
app.command(coverage_app)


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


@coverage_app.command(name="show")
def coverage_show(run_id: str) -> None:
    """Show the persisted Coverage Fact set for ``run_id``.

    Cache-read only — this verb never auto-derives. When the run exists
    but no ``coverage_facts.json`` is on disk, the envelope reports
    ``coverage_outcome.kind == "unavailable"`` with reason
    ``missing-derived-facts`` (the run was executed without
    ``novetest run --coverage``).
    """
    store = _require_store("coverage.show")
    ref = _resolve_run_reference(store, "coverage.show", run_id)
    try:
        outcome = get_coverage_facts(store, ref)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (record corrupted between the lookup scan
        # and the engine's targeted read — TOCTOU): storage error, exit 5.
        _emit_and_exit(_store_corrupt_envelope("coverage.show", str(exc)), EXIT_STORAGE)
    _emit_and_exit(
        Envelope(
            command="coverage.show",
            ok=True,
            data={"coverage_outcome": coverage_outcome_payload(outcome)},
        ),
        EXIT_OK,
    )


@coverage_app.command(name="diff")
def coverage_diff(baseline_run_id: str, target_run_id: str) -> None:
    """Diff the persisted Coverage Fact sets of two runs.

    Surfaces ``coverage_delta.kind == "delta"`` on success and
    ``coverage_delta.kind == "unavailable"`` when either side lacks
    derived facts (the unavailable outcome is propagated from
    ``compare_coverage_facts``).
    """
    store = _require_store("coverage.diff")
    baseline_ref = _resolve_run_reference(store, "coverage.diff", baseline_run_id)
    target_ref = _resolve_run_reference(store, "coverage.diff", target_run_id)
    try:
        outcome = compare_coverage_facts(store, baseline_ref, target_ref)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(_store_corrupt_envelope("coverage.diff", str(exc)), EXIT_STORAGE)
    _emit_and_exit(
        Envelope(
            command="coverage.diff",
            ok=True,
            data={"coverage_delta": coverage_delta_payload(outcome)},
        ),
        EXIT_OK,
    )


# ---------------------------------------------------------------------------
# Regression subcommand group + top-level `compare` verb
# ---------------------------------------------------------------------------


regression_app = App(
    name="regression",
    help="Regression commands: compare two runs / resolve the latest pair.",
)
app.command(regression_app)


@regression_app.command(name="compare")
def regression_compare(baseline_run_id: str, target_run_id: str) -> None:
    """Compare two specific Run Records and emit Regression Facts.

    Calls ``compare_runs(store, baseline_ref, target_ref)`` — the cache-
    aware entry point. On cache miss it derives and persists; on cache
    hit it reads. Tombstoned inputs surface ``REASON_RUN_TOMBSTONED`` per
    decision §C.1 even when a stale cached file exists on disk.

    A stale or fake ``run_id`` short-circuits BEFORE ``compare_runs`` is
    invoked: ``_resolve_run_reference`` emits a structured ``not-found``
    envelope and exits 2, mirroring ``coverage diff``. All other
    unavailable outcomes (engine-mismatch, target-mismatch, tombstoned,
    etc.) surface as ``regression_outcome.kind == "unavailable"`` with
    ``ok: true``, exit 0 — the transport succeeded, the unavailability
    is data.
    """

    store = _require_store("regression.compare")
    baseline_ref = _resolve_run_reference(store, "regression.compare", baseline_run_id)
    target_ref = _resolve_run_reference(store, "regression.compare", target_run_id)
    try:
        outcome = compare_runs(store, baseline_ref, target_ref)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(
            _store_corrupt_envelope("regression.compare", str(exc)), EXIT_STORAGE
        )
    _emit_and_exit(
        Envelope(
            command="regression.compare",
            ok=True,
            data={"regression_outcome": regression_outcome_payload(outcome)},
        ),
        EXIT_OK,
    )


@regression_app.command(name="latest")
def regression_latest() -> None:
    """Resolve the latest comparable pair for the active target and emit Regression Facts.

    Composes the engine's ``derive_latest_regression(store)`` end-to-end:
    latest live run → its ``target_expression`` → most recent prior live
    run on the same target → ``compare_runs`` of the pair. An empty store,
    or one whose runs are all tombstoned, surfaces
    ``regression_outcome.kind == "unavailable"`` with reason
    ``no-comparable-baseline``.
    """

    store = _require_store("regression.latest")
    try:
        outcome = derive_latest_regression(store)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(
            _store_corrupt_envelope("regression.latest", str(exc)), EXIT_STORAGE
        )
    _emit_and_exit(
        Envelope(
            command="regression.latest",
            ok=True,
            data={"regression_outcome": regression_outcome_payload(outcome)},
        ),
        EXIT_OK,
    )


@app.command(name="compare")
def compare_cmd(baseline_run_id: str, target_run_id: str) -> None:
    """Composed Regression + Coverage view for a specific pair.

    Thin transport over the ``build_compare_view`` workflow
    (``orchestration/workflows/compare.py``), which emits both
    ``regression_outcome`` (from ``compare_runs``) and ``coverage_delta``
    (from ``compare_coverage_facts``) in the same envelope. When either
    side lacks coverage facts, ``coverage_delta`` surfaces
    ``kind: "unavailable"`` with the propagated reason — the same
    projection ``coverage diff`` emits. Distinct from
    ``regression compare`` (which emits ``regression_outcome`` only).
    """

    store = _require_store("compare")
    baseline_ref = _resolve_run_reference(store, "compare", baseline_run_id)
    target_ref = _resolve_run_reference(store, "compare", target_run_id)
    try:
        view = build_compare_view(store, baseline_ref, target_ref)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(_store_corrupt_envelope("compare", str(exc)), EXIT_STORAGE)
    _emit_and_exit(
        Envelope(command="compare", ok=True, data=view.to_dict()),
        EXIT_OK,
    )


# ---------------------------------------------------------------------------
# Localization subcommand group
# ---------------------------------------------------------------------------


localization_app = App(
    name="localization",
    help="Localization commands: rank suspicious code locations (SBFL) for a run.",
)
app.command(localization_app)


def _validate_localization_flags(command: str, formula: str, top_n: int) -> None:
    """Reject bad ``--formula`` / ``--top-n`` at the CLI boundary (exit 2).

    The closed ``FORMULAS`` enum and the positive-integer ``top_n``
    contract are enforced HERE so the engine never sees an invalid value —
    a bad flag is a transport error (``invalid-flag``), distinct from the
    data-level ``unavailable`` outcomes the engine returns. ``_emit_and_exit``
    is ``NoReturn``, so a normal return means both flags are valid.
    """
    if formula not in FORMULAS:
        _emit_and_exit(
            Envelope(
                command=command,
                ok=False,
                errors=(
                    EnvelopeError(
                        code="invalid-flag",
                        message=(
                            f"Invalid --formula={formula!r}; "
                            f"expected one of {sorted(FORMULAS)!r}"
                        ),
                    ),
                ),
            ),
            EXIT_USAGE,
        )
    if top_n < 1:
        _emit_and_exit(
            Envelope(
                command=command,
                ok=False,
                errors=(
                    EnvelopeError(
                        code="invalid-flag",
                        message=(
                            f"Invalid --top-n={top_n!r}; expected a positive integer"
                        ),
                    ),
                ),
            ),
            EXIT_USAGE,
        )


@localization_app.default
def localization_run(
    run_id: str,
    *,
    formula: str | None = None,
    top_n: Annotated[int | None, Parameter(name=["--top-n"])] = None,
) -> None:
    """Rank suspicious code locations for RUN_ID via SBFL.

    Calls ``derive_localization_findings`` — the cache-aware engine entry
    point. On cache miss it derives + persists; on cache hit it reads the
    stored ``localization_findings.json`` (so ``derived_at`` is preserved
    across repeated invocations). Bad ``--formula`` / ``--top-n`` values are
    rejected up-front with ``invalid-flag`` (exit 2) so the engine never
    sees them. A stale or fake ``run_id`` short-circuits to a structured
    ``not-found`` envelope (exit 2) via ``_resolve_run_reference``.

    Engine-level unavailability (no failed tests, no per-test coverage, a
    tombstoned run) surfaces as ``localization_outcome.kind == "unavailable"``
    with ``ok: true``, exit 0 — the transport succeeded; the unavailability
    is data.

    ``--formula`` defaults to ``"ochiai"``; ``--top-n`` defaults to ``10``.
    Both flags use ``None`` sentinels here so the handler can distinguish
    "user explicitly passed this value" from "Cyclopts default in effect".

    Cache-invalidation policy (Defect 5 fix, 2026-06-01): when the engine
    serves from cache AND the user explicitly passed ``--formula`` /
    ``--top-n`` differing from the cached values, the orchestration
    workflow (``orchestration/workflows/localization.py``) invalidates
    the cache and re-derives at the requested flags. The audit signal
    surfaces as the ``localization-cache-rederived`` envelope warning
    (built HERE from the workflow's audit structure — warning wording is
    transport-owned); pre-Defect-5 the same condition surfaced as
    ``localization-cache-args-ignored`` and the stale cached result was
    returned. See task brief / history at
    ``agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md``
    §"Defect 5 surfaced".
    """

    store = _require_store("localization")
    formula_explicit = formula is not None
    top_n_explicit = top_n is not None
    resolved_formula = formula if formula is not None else DEFAULT_FORMULA
    resolved_top_n = top_n if top_n is not None else DEFAULT_TOP_N
    _validate_localization_flags("localization", resolved_formula, resolved_top_n)
    ref = _resolve_run_reference(store, "localization", run_id)
    try:
        outcome, audit = derive_localization_with_flag_policy(
            store,
            ref,
            formula=resolved_formula,
            top_n=resolved_top_n,
            formula_explicit=formula_explicit,
            top_n_explicit=top_n_explicit,
        )
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(_store_corrupt_envelope("localization", str(exc)), EXIT_STORAGE)
    warning = _localization_audit_warning(audit)
    _emit_and_exit(
        Envelope(
            command="localization",
            ok=True,
            data={"localization_outcome": localization_outcome_payload(outcome)},
            warnings=(warning,) if warning is not None else (),
        ),
        EXIT_OK,
    )


@localization_app.command(name="latest")
def localization_latest(
    *,
    formula: str | None = None,
    top_n: Annotated[int | None, Parameter(name=["--top-n"])] = None,
) -> None:
    """Rank suspicious code locations for the latest analyzable run.

    Composes the engine's ``derive_latest_localization`` end-to-end:
    newest-first walk of Run History → first run that passes the
    availability probe → ``derive_localization_findings``. An empty store
    surfaces ``unavailable`` with reason ``no-run-evidence``; a store whose
    runs are all non-analyzable surfaces ``run-not-analyzable``. Flag
    validation mirrors the explicit-run verb.

    Cache-invalidation policy matches the explicit-run verb (Defect 5 fix):
    the ``None`` sentinel defaults let the handler distinguish "user
    explicitly passed this value" from "Cyclopts default in effect", and an
    explicit-flag mismatch against the cached findings triggers a re-derive
    + ``localization-cache-rederived`` warning via the shared
    ``derive_latest_localization_with_flag_policy`` workflow.
    """

    store = _require_store("localization.latest")
    formula_explicit = formula is not None
    top_n_explicit = top_n is not None
    resolved_formula = formula if formula is not None else DEFAULT_FORMULA
    resolved_top_n = top_n if top_n is not None else DEFAULT_TOP_N
    _validate_localization_flags(
        "localization.latest", resolved_formula, resolved_top_n
    )
    try:
        outcome, audit = derive_latest_localization_with_flag_policy(
            store,
            formula=resolved_formula,
            top_n=resolved_top_n,
            formula_explicit=formula_explicit,
            top_n_explicit=top_n_explicit,
        )
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(
            _store_corrupt_envelope("localization.latest", str(exc)), EXIT_STORAGE
        )
    warning = _localization_audit_warning(audit)
    _emit_and_exit(
        Envelope(
            command="localization.latest",
            ok=True,
            data={"localization_outcome": localization_outcome_payload(outcome)},
            warnings=(warning,) if warning is not None else (),
        ),
        EXIT_OK,
    )


def _localization_audit_warning(
    audit: LocalizationAudit | None,
) -> EnvelopeWarning | None:
    """Project a localization workflow audit onto its ``EnvelopeWarning``.

    The cache-override POLICY (Defect 5 detection + invalidation +
    re-derive, Defect 7 formula-noop carve-out) lives in
    ``orchestration/workflows/localization.py`` (W2/S22, ORC-07/XCT-02);
    the workflow reports WHAT happened via an audit structure and this
    transport-side mapper owns the wire wording: a
    :class:`CacheRederivedAudit` becomes the
    ``localization-cache-rederived`` warning, a :class:`FormulaNoopAudit`
    becomes ``localization-formula-noop-in-mode``, and ``None`` (no
    policy event) stays warning-free.
    """
    if audit is None:
        return None
    if isinstance(audit, CacheRederivedAudit):
        return _build_localization_cache_rederived_warning(
            run_id=audit.run_id,
            previous_cached_args=(audit.previous_formula, audit.previous_top_n),
            resolved_formula=audit.requested_formula,
            resolved_top_n=audit.requested_top_n,
            formula_explicit=audit.formula_explicit,
            top_n_explicit=audit.top_n_explicit,
        )
    return _build_localization_formula_noop_warning(
        requested_formula=audit.requested_formula,
        returned_formula=audit.returned_formula,
        mode=audit.mode,
    )


def _build_localization_cache_rederived_warning(
    *,
    run_id: str,
    previous_cached_args: tuple[str, int],
    resolved_formula: str,
    resolved_top_n: int,
    formula_explicit: bool,
    top_n_explicit: bool,
) -> EnvelopeWarning:
    """Format the ``localization-cache-rederived`` warning payload.

    The workflow policy (``orchestration/workflows/localization.py``) has
    already determined that a re-derive happened — this helper is reached
    only via ``_localization_audit_warning`` on a ``CacheRederivedAudit``,
    so it always emits a warning; its job is just payload construction.
    The ``details`` shape
    is the symmetric counterpart of the pre-Defect-5
    ``localization-cache-args-ignored`` warning: ``previous`` (what the
    cache held), ``requested`` (what the user asked for), ``cache_path``
    (where the fresh derive was just persisted). AI consumers can diff
    ``previous`` vs ``requested`` to know what changed and learn that the
    re-compute cost was paid.

    The ``cache_path`` is computed by template — the on-disk layout is
    pinned by ``localization/persistence.py`` and Memory's availability
    probe both reference the exact
    ``<store>/localization/findings/run_<id>/localization_findings.json``
    path. Hardcoding the template here avoids a redundant disk read and
    keeps the transport-side warning construction self-contained.
    """
    prev_formula, prev_top_n = previous_cached_args
    cache_path = (
        f".novetest/localization/findings/run_{run_id}/localization_findings.json"
    )
    message = (
        f"cached findings (--formula='{prev_formula}' --top-n={prev_top_n}) "
        f"were re-derived at requested --formula='{resolved_formula}' "
        f"--top-n={resolved_top_n}; cache overwritten at {cache_path}"
    )
    return EnvelopeWarning(
        code="localization-cache-rederived",
        message=message,
        details={
            "previous": {
                "formula": prev_formula,
                "top_n": prev_top_n,
            },
            "requested": {
                "formula": resolved_formula,
                "top_n": resolved_top_n,
                "formula_explicit": formula_explicit,
                "top_n_explicit": top_n_explicit,
            },
            "cache_path": cache_path,
        },
    )


def _build_localization_formula_noop_warning(
    *,
    requested_formula: str,
    returned_formula: str,
    mode: str,
) -> EnvelopeWarning:
    """Format the ``localization-formula-noop-in-mode`` warning payload.

    Emitted (via ``_localization_audit_warning`` on a ``FormulaNoopAudit``
    from the workflow policy) when the user passes an explicit
    ``--formula`` that mismatches the cached/returned value AND the
    engine's mode is one whose formula field is a structural placeholder
    rather than a real selection (today: only ``failure_proximity``,
    which always reports ``formula = "ochiai"`` regardless of input —
    see ``localization/failure_proximity.py::_PLACEHOLDER_FORMULA``).

    This warning is the AI-agent-facing signal that the requested
    ``--formula`` is a noop in the current mode: re-running with a
    different formula value will NOT produce different results, so the
    consumer should not retry. The single-shot ``EnvelopeWarning`` —
    rather than the pre-Defect-7 ``localization-cache-rederived`` loop —
    is what the 2026-06-08 task brief calls "structural noop signal,
    not a fixable misconfig signal".

    The details schema is intentionally minimal (three flat fields
    matching the task brief literal): ``requested_formula`` (what the
    user passed), ``returned_formula`` (the placeholder the engine
    served), ``mode`` (the mode that pins the formula). Forward-compat:
    if a future mode is added with a different placeholder, this
    warning's shape requires no change — only the ``mode`` carve-out
    in the caller broadens.
    """
    message = (
        f"requested --formula='{requested_formula}' is a no-op in "
        f"'{mode}' mode; engine pins formula='{returned_formula}' as a "
        f"placeholder for this mode (no SBFL formula is computed). "
        f"Re-running with a different --formula value will not change "
        f"the result."
    )
    return EnvelopeWarning(
        code="localization-formula-noop-in-mode",
        message=message,
        details={
            "requested_formula": requested_formula,
            "returned_formula": returned_formula,
            "mode": mode,
        },
    )


# ---------------------------------------------------------------------------
# Aggregated single-run view
# ---------------------------------------------------------------------------


@app.command(name="inspect")
def inspect_cmd(run_id: str) -> None:
    """Show the aggregated single-run view for ``run_id``.

    Composes the Run Record summary with the persisted Coverage Facts (the
    same ``coverage_outcome`` block ``coverage show`` emits), a Regression
    section computed against the most-recent live prior run on the same
    target, AND a Localization section read cache-only from the per-run
    ``localization_findings.json`` (the same ``localization_outcome`` block
    ``novetest localization`` emits) — each flips its
    ``sub_reports[...]`` marker from ``"unavailable"`` to ``"available"``
    when its evidence resolves. Replay remains present-but-``unavailable``
    until its engine lands in Phase 5. ``inspect`` spawns no engine
    subprocess (it runs no test); its Coverage / Localization / Replay
    sections are strictly cache-only reads. Its Regression section, by
    contrast, COMPOSES ``resolve_baseline_for_run`` + ``compare_runs`` and so
    DERIVES the pair's facts on a cache miss (self-heal) — the intended
    ORC-25 asymmetry with ``status``, which is strictly cache-only (Gate-1
    D3=A, 2026-07-20; see ``workflows/inspect.py``).

    A stale or fake ``run_id`` surfaces a structured ``not-found`` error
    (exit 2), mirroring ``memory show``. Tombstoned runs remain inspectable.
    An id whose record is corrupt on disk escalates to ``store-corrupt``
    (exit 5) instead — the Gate-1 Q1-A addressed-lookup convention
    (``_lookup_miss_exit``); warning-free like every non-memory verb.
    """
    store = _require_store("inspect")
    skipped: list[SkippedRecord] = []
    try:
        view = build_inspect_view(store, run_id, skipped=skipped)
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(_store_corrupt_envelope("inspect", str(exc)), EXIT_STORAGE)
    if view is None:
        _lookup_miss_exit("inspect", run_id, skipped)
    _emit_and_exit(
        Envelope(command="inspect", ok=True, data=view.to_dict()),
        EXIT_OK,
    )


# ---------------------------------------------------------------------------
# Integrated `novetest test [target]` workflow (Phase 6 entry)
# ---------------------------------------------------------------------------


@app.command(name="test")
def test_cmd(
    target: str = "",
    *,
    reruns: Annotated[int, Parameter(name=["--reruns"])] = 0,
    engine: Annotated[str | None, Parameter(name=["--engine"])] = None,
) -> None:
    """Execute the integrated `novetest test [target]` workflow.

    Chains Run → Memory → Coverage → Regression → Localization →
    Recommendation synthesis. Stage failures (no baseline, no coverage,
    etc.) are surfaced via the ``data.stage_eligibility`` block — the
    workflow does NOT abort on a single-engine outage (brief §5 — Error
    policy). Run execution (step 2) is fatal; the handler maps the same
    exception surface ``run_cmd`` does (``EngineNotReadyError`` +
    ``AdapterInvocationError``) and re-uses the same envelope shape.

    ``--reruns N`` (default 0 = off; decision
    ``2026-06-25-test-reruns-flag-and-replay-integration``) opts into the
    Replay sub-workflow: when the run has failed tests, one whole-run
    Replay Attempt executes with ``reruns=N`` and its result feeds the
    synthesizer — an ``inconsistent`` classification makes the
    ``flaky_suspected`` category reachable, and
    ``data.stage_eligibility.replay`` transitions ``"not_run"`` →
    ``"available"``. ``N=1`` is the cheapest opt-in; ``5`` is the
    recommended floor for flake detection. Negative values are rejected
    with ``invalid-flag`` (exit 2), mirroring the ``--formula`` pattern.

    Recommendations are synthesized in-memory from the
    ``FactBundle`` — never persisted (Open Q #9 / brief §2). Re-deriving
    against the same evidence yields a byte-identical recommendation
    list (determinism contract, design doc §4).

    The ``data.run_reference`` / ``data.stage_eligibility`` /
    ``data.recommendation_schema_version`` / ``data.recommendations``
    fields are the wire surface AI agents pin against (brief §5).

    ``--engine <name>`` executes a one-off override of the store's pinned
    engine WITHOUT re-pinning (decision 2026-07-03-engine-selection-policy
    D3); invalid names fail flag validation (``invalid-flag``, exit 2).
    """

    store = _require_store("test")
    if reruns < 0:
        _emit_and_exit(
            Envelope(
                command="test",
                ok=False,
                errors=(
                    EnvelopeError(
                        code="invalid-flag",
                        message=(
                            f"Invalid --reruns={reruns!r}; "
                            "expected a non-negative integer"
                        ),
                    ),
                ),
            ),
            EXIT_USAGE,
        )
    engine_pair = _validate_engine_flag("test", engine)
    try:
        outcome = asyncio.run(
            test_target_in_store(target, store, reruns=reruns, engine=engine_pair)
        )
    except (EngineAmbiguousError, RunEngineError) as exc:
        # ORC-02/ORC-21: same shared mapping as run_cmd — the two verbs cannot
        # drift because they thread their own ``command`` through one helper.
        # Post-S19, ``EngineAmbiguous`` reaches here as the primary legacy +
        # ambiguous refusal (see run_cmd's note), not a TOCTOU race.
        _emit_and_exit(*_map_execution_exception("test", exc))
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (a stage's targeted read / the post-stage
        # refresh found a record corrupt — TOCTOU): storage failure, exit 5.
        _emit_and_exit(_store_corrupt_envelope("test", str(exc)), EXIT_STORAGE)

    envelope, exit_code = build_test_envelope(outcome)
    _emit_and_exit(envelope, exit_code)


# ---------------------------------------------------------------------------
# `novetest replay <run_id>` verb (Phase 5 entry)
# ---------------------------------------------------------------------------


def _build_replay_envelope(
    original_ref: RunReference, outcome: ReplayResult | ReplayUnavailable
) -> tuple[Envelope, int]:
    """Map a Replay outcome onto an ``(Envelope, exit_code)`` pair.

    Exit-code split (rationale in the handoff §5.3): a classify-able outcome
    (``ReplayResult`` of any classification, including the valid
    ``unable_to_replay``) is a success at exit 0. A ``ReplayUnavailable`` is
    a user/engine error: ``engine-not-ready`` / ``target-missing`` map to
    exit 4 (``EXIT_ENGINE_MISSING``, mirroring ``run`` / ``test``);
    ``original-not-found`` maps to exit 2 (``EXIT_USAGE``, mirroring
    ``inspect``); the remaining "structured unavailable" reasons
    (``tombstoned-original`` / ``context-reconstruction-failed`` /
    ``missing-derived-facts``) are non-error data outcomes at exit 0.
    """
    data: dict[str, Any] = {
        "original_run_reference": original_ref.to_dict(),
        "replay_outcome": replay_outcome_payload(outcome),
    }
    if isinstance(outcome, ReplayResult):
        return Envelope(command="replay", ok=True, data=data), EXIT_OK

    reason = outcome.reason
    if reason in (REASON_ENGINE_NOT_READY, REASON_TARGET_MISSING):
        exit_code = EXIT_ENGINE_MISSING
    elif reason == REASON_ORIGINAL_NOT_FOUND:
        exit_code = EXIT_USAGE
    else:
        # tombstoned-original / context-reconstruction-failed /
        # missing-derived-facts — structured outcome, not an error.
        return Envelope(command="replay", ok=True, data=data), EXIT_OK

    return (
        Envelope(
            command="replay",
            ok=False,
            data=data,
            errors=(
                EnvelopeError(
                    code=f"replay-{reason}",
                    message=outcome.detail or reason,
                ),
            ),
        ),
        exit_code,
    )


@app.command(name="replay")
def replay_cmd(run_id: str, *, reruns: int = 1, timeout: float = 600.0) -> None:
    """Replay a prior run and classify its reproducibility.

    Reconstructs the original run's context from stored evidence, re-executes
    it ``--reruns`` times through the SAME governed native engine path
    (``run/execute_with_engine_context``), and classifies the result as
    ``reproducible`` / ``inconsistent`` / ``unable_to_replay`` (REQ-REP-003).

    ``<run_id>`` is the ORIGINAL run's id; a stale/fake id surfaces a
    structured ``not-found`` error (exit 2), mirroring ``inspect``. The
    replay-execution runs are persisted as first-class Memory Entries (they
    appear in ``memory list``); the Replay Result is cached at
    ``<store>/replay/results/run_<id>/replay_result.json``.

    ``--reruns`` defaults to 1 (cheap single replay). Investigating flakiness
    typically wants ``--reruns 5``. ``unable_to_replay`` is a VALID
    classification (exit 0), not an error.
    """
    store = _require_store("replay")
    original_ref = _resolve_run_reference(store, "replay", run_id)
    try:
        outcome = asyncio.run(
            replay_run(store, original_ref, reruns=reruns, timeout=timeout)
        )
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (TOCTOU targeted read): exit 5.
        _emit_and_exit(_store_corrupt_envelope("replay", str(exc)), EXIT_STORAGE)
    envelope, exit_code = _build_replay_envelope(original_ref, outcome)
    _emit_and_exit(envelope, exit_code)


# ---------------------------------------------------------------------------
# Top-level argv plumbing (unchanged from Phase 0)
# ---------------------------------------------------------------------------


def _extract_output_flag(argv: list[str]) -> tuple[str | None, list[str]]:
    """Pull --output / --output=<v> out of argv; return (value, argv_without_flag)."""
    value: str | None = None
    cleaned: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--output":
            if i + 1 < len(argv):
                value = argv[i + 1]
                i += 2
                continue
            i += 1
            continue
        if tok.startswith("--output="):
            value = tok.split("=", 1)[1]
            i += 1
            continue
        cleaned.append(tok)
        i += 1
    return value, cleaned


def _scan_top_level_intent(argv: list[str]) -> str | None:
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in _SUBCOMMAND_TOKENS:
            return None
        if tok in ("-v", "--version"):
            return "version"
        if tok in ("-h", "--help"):
            return "help"
        if tok == "--output":
            i += 2
            continue
        if tok.startswith("--output="):
            i += 1
            continue
        i += 1
    return None


def _inject_default_verb_alias(argv: list[str]) -> list[str]:
    """Inject ``"test"`` before the first positional when it is not a verb.

    Implements the Phase 6 brief §6 default-verb alias:
    ``novetest <target>`` ≡ ``novetest test <target>`` whenever
    ``<target>`` is not in ``_SUBCOMMAND_TOKENS`` (the reserved verb set)
    and not a flag.

    Disambiguation rule: if the first positional token IS a reserved
    verb, ALWAYS route to that verb's handler even when a directory of
    the same name exists in the workspace. The reserved set wins
    unconditionally (so a workspace with a directory literally named
    ``inspect/`` cannot shadow ``novetest inspect <run_id>``).

    This is called from ``main()`` AFTER ``_extract_output_flag``
    (so ``--output`` and its value are already stripped) AND AFTER the
    top-level intent scan (so ``-v`` / ``-h`` keep their precedence).
    Bare ``novetest`` (empty argv after stripping) is handled separately
    in ``main()`` — that surface emits the help envelope directly per
    REQ-ORCH-006.

    Pure function — no side effects. Returns the (possibly-augmented)
    argv list; the original list is not mutated.
    """

    if not argv:
        return argv
    # Find the first positional (non-flag) token.
    for tok in argv:
        if tok.startswith("-"):
            continue
        # First positional. If it is a reserved verb, leave argv alone.
        if tok in _SUBCOMMAND_TOKENS:
            return argv
        # Else, inject "test" as the verb. Prepending preserves any
        # leading flags Cyclopts may consume at the top level.
        return ["test", *argv]
    # All tokens were flags — let Cyclopts handle (or reject) them.
    return argv


def _emit_version(mode: OutputMode) -> None:
    identity = report_cli_identity()
    emit_envelope(Envelope(command="version", ok=True, data=identity.to_dict()), mode)


def _emit_help(mode: OutputMode) -> None:
    surface = describe_command_surface()
    emit_envelope(Envelope(command="help", ok=True, data=surface.to_dict()), mode)


def main(argv: list[str] | None = None) -> None:
    global _active_mode
    raw = list(sys.argv[1:] if argv is None else argv)
    explicit, args = _extract_output_flag(raw)
    mode = resolve_output_mode(explicit)
    apply_no_color(mode)
    _active_mode = mode

    intent = _scan_top_level_intent(args)
    if intent == "version":
        _emit_version(mode)
        sys.exit(EXIT_OK)
    if intent == "help":
        _emit_help(mode)
        sys.exit(EXIT_OK)

    # Bare ``novetest`` (no positional / no verb / no recognized flag) —
    # per Phase 6 brief §6 + REQ-ORCH-006, emit the help envelope and
    # exit 0. This MUST come before the alias injection: bare-novetest
    # must NOT silently become ``novetest test`` (which would try to
    # invoke the integrated workflow with an empty target).
    if not args:
        _emit_help(mode)
        sys.exit(EXIT_OK)

    # Default-verb alias: ``novetest <target>`` → ``novetest test <target>``
    # when ``<target>`` is not in the reserved verb set. Pure-function
    # transformation; the alias hook itself is testable in isolation
    # (see ``tests/unit/cli/test_default_verb_alias.py``).
    args = _inject_default_verb_alias(args)

    try:
        app(args)
    except SystemExit:
        raise
    except Exception as exc:
        emit_envelope(
            Envelope(
                command="cli",
                ok=False,
                errors=(EnvelopeError(code="cli-error", message=str(exc)),),
            ),
            mode,
        )
        sys.exit(EXIT_GENERIC)
