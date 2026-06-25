from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Any, Callable, NoReturn

from cyclopts import App, Parameter

from novetest import __version__
from novetest.cli.handlers.test import build_test_envelope
from novetest.cli.output import (
    EXIT_ENGINE_MISSING,
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_STORAGE,
    EXIT_USAGE,
    EXIT_USER_TESTS_FAILED,
    Envelope,
    EnvelopeError,
    EnvelopeWarning,
    OutputMode,
    apply_no_color,
    emit_envelope,
    not_implemented_envelope,
    resolve_output_mode,
)
from novetest.coverage import (
    CoverageUnavailable,
    compare_coverage_facts,
    get_coverage_facts,
)
from novetest.coverage.compare import CoverageDelta
from novetest.localization import (
    DEFAULT_FORMULA,
    DEFAULT_TOP_N,
    FORMULAS,
    LocalizationFinding,
    LocalizationUnavailable,
    derive_latest_localization,
    derive_localization_findings,
)
from novetest.localization.persistence import localization_findings_path
from novetest.memory import (
    ProjectStore,
    ProjectStoreCorruptError,
    RunEvidenceNotFoundError,
    delete_run_evidence,
    list_run_history,
    locate_project_store,
    retrieve_run_evidence,
)
from novetest.models import ReplayResult, RunReference
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.orchestration.onboarding.command_surface import describe_command_surface
from novetest.orchestration.onboarding.identity import report_cli_identity
from novetest.orchestration.workflows import (
    build_inspect_view,
    build_status_view,
    initialize_project_workspace,
    run_target_in_store,
    test_target_in_store,
)
from novetest.regression import (
    RegressionFactSet,
    RegressionUnavailable,
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
from novetest.run import AdapterInvocationError, AdapterWarning, EngineNotReadyError


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
# Stub helpers (still used for Phase 1 commands without an orchestration path)
# ---------------------------------------------------------------------------


def _make_stub(command_path: str) -> Callable[..., None]:
    def _stub(*args: Any, **kwargs: Any) -> None:
        emit_envelope(not_implemented_envelope(command_path), _active_mode)
        sys.exit(EXIT_USAGE)

    _stub.__name__ = command_path.replace(".", "_")
    _stub.__doc__ = f"Stub for {command_path}; not yet implemented."
    return _stub


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


def _require_store(command: str) -> ProjectStore:
    try:
        store = locate_project_store(Path.cwd())
    except ProjectStoreCorruptError as exc:
        _emit_and_exit(
            Envelope(
                command=command,
                ok=False,
                errors=(EnvelopeError(code="store-corrupt", message=str(exc)),),
            ),
            EXIT_STORAGE,
        )
    if store is None:
        _emit_and_exit(_uninitialized(command), EXIT_USAGE)
    return store


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
def init() -> None:
    """Initialize a Project Store in the current working directory."""
    workspace = Path.cwd()
    try:
        result = asyncio.run(initialize_project_workspace(workspace))
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
        _emit_and_exit(
            Envelope(
                command="init",
                ok=False,
                errors=(EnvelopeError(code="store-corrupt", message=str(exc)),),
            ),
            EXIT_STORAGE,
        )

    data: dict[str, Any] = {
        "store_path": str(result.store.path),
        "store_state": result.store.store_state,
        "initialized_at": result.store.initialized_at,
        "engine_readiness": _readiness_payload(result.engine_readiness),
    }
    _emit_and_exit(Envelope(command="init", ok=True, data=data), EXIT_OK)


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
    # The reset workflow + Memory's wipe primitive are imported lazily: the
    # primitive ships in the sibling Memory cycle, so deferring keeps the CLI
    # importable during parallel development and reads the current symbol at
    # call time (clean monkeypatch isolation in unit tests). Mirrors the
    # ``licenses_cmd`` deferred-import pattern.
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

    from novetest.memory import ProjectStoreNotFoundError
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
        _emit_and_exit(
            Envelope(
                command="reset",
                ok=False,
                errors=(EnvelopeError(code="store-corrupt", message=str(exc)),),
            ),
            EXIT_STORAGE,
        )
    except OSError as exc:
        _emit_and_exit(
            Envelope(
                command="reset",
                ok=False,
                errors=(EnvelopeError(code="store-wipe-failed", message=str(exc)),),
            ),
            EXIT_STORAGE,
        )

    data: dict[str, Any] = {
        "store_path": str(result.init_result.store.path),
        "store_state": result.init_result.store.store_state,
        "previous_initialized_at": result.wipe_report.previous_initialized_at,
        "initialized_at": result.init_result.store.initialized_at,
        "items_removed": result.wipe_report.items_removed,
        "engine_readiness": _readiness_payload(result.init_result.engine_readiness),
    }
    _emit_and_exit(Envelope(command="reset", ok=True, data=data), EXIT_OK)


@app.command(name="run")
def run_cmd(
    target: str = "",
    *,
    coverage: Annotated[bool, Parameter(name=["--coverage", "-c"])] = False,
) -> None:
    """Execute the resolved Test Target and persist the Run Record.

    With ``--coverage`` / ``-c``, the run is invoked with coverage
    instrumentation and Coverage's ``derive_coverage_facts`` is called
    after persistence. The resulting fact-set (or an explicit
    ``CoverageUnavailable`` outcome) is reported under the envelope's
    ``data.coverage_outcome`` block; without the flag, the key is omitted
    entirely so non-coverage runs stay byte-equivalent to Phase 1.
    """
    store = _require_store("run")
    try:
        outcome = asyncio.run(
            run_target_in_store(target, store, collect_coverage=coverage)
        )
    except EngineNotReadyError as exc:
        _emit_and_exit(
            Envelope(
                command="run",
                ok=False,
                data={"engine_readiness": _readiness_payload(exc.readiness)},
                errors=(
                    EnvelopeError(
                        code=f"engine-{exc.readiness.state}",
                        message=str(exc),
                    ),
                ),
            ),
            EXIT_ENGINE_MISSING,
        )
    except AdapterInvocationError as exc:
        _emit_and_exit(
            Envelope(
                command="run",
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
            EXIT_ENGINE_MISSING,
        )

    entry = outcome.memory_entry
    record = entry.run_record
    if record.status == "passed":
        exit_code = EXIT_OK
        ok = True
    elif record.status == "failed":
        exit_code = EXIT_USER_TESTS_FAILED
        ok = True  # the run itself succeeded; the *user's* tests failed
    else:
        exit_code = EXIT_GENERIC
        ok = False

    data: dict[str, Any] = {"memory_entry": entry.to_dict()}
    if outcome.coverage_outcome is not None:
        data["coverage_outcome"] = _coverage_outcome_payload(outcome.coverage_outcome)
    envelope_warnings = _adapter_to_envelope_warnings(outcome.warnings)
    _emit_and_exit(
        Envelope(command="run", ok=ok, data=data, warnings=envelope_warnings),
        exit_code,
    )


def _coverage_outcome_payload(
    outcome: CoverageFactSet | CoverageUnavailable,
) -> dict[str, Any]:
    """Project a Coverage derive outcome onto the envelope wire shape.

    Two ``kind`` values discriminate at parse time: ``fact-set`` carries
    the granularity + summary, ``unavailable`` carries the reason + detail.
    The ``run_reference`` block is present in both (None only when the
    Run Reference itself could not be resolved — which cannot happen on
    this code path because we just persisted the record).
    """
    if isinstance(outcome, CoverageFactSet):
        return {
            "kind": "fact-set",
            "run_reference": outcome.run_reference.to_dict(),
            "mapping_granularity": outcome.mapping_granularity,
            "summary": outcome.summary.to_dict(),
        }
    return {
        "kind": "unavailable",
        "run_reference": (
            outcome.run_reference.to_dict()
            if outcome.run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


@app.command
def status() -> None:
    """Summarize the current Project Store: latest run + sub-report availability."""
    store = _require_store("status")
    view = build_status_view(store)
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


@memory_app.command(name="list")
def memory_list() -> None:
    """List Run History newest-first."""
    store = _require_store("memory.list")
    entries = list_run_history(store)
    _emit_and_exit(
        Envelope(
            command="memory.list",
            ok=True,
            data={
                "count": len(entries),
                "entries": [e.to_dict() for e in entries],
            },
        ),
        EXIT_OK,
    )


@memory_app.command(name="show")
def memory_show(run_id: str) -> None:
    """Show the Memory Entry for ``run_id`` (live or tombstoned)."""
    store = _require_store("memory.show")
    entries = list_run_history(store)
    target = next(
        (e for e in entries if e.run_record.run_reference.run_id == run_id),
        None,
    )
    if target is None:
        _emit_and_exit(
            Envelope(
                command="memory.show",
                ok=False,
                errors=(
                    EnvelopeError(
                        code="not-found",
                        message=f"No Memory Entry for run_id={run_id!r}",
                    ),
                ),
            ),
            EXIT_USAGE,
        )
    ref = target.run_record.run_reference
    try:
        entry = retrieve_run_evidence(store, ref)
    except RunEvidenceNotFoundError as exc:
        _emit_and_exit(
            Envelope(
                command="memory.show",
                ok=False,
                errors=(EnvelopeError(code="not-found", message=str(exc)),),
            ),
            EXIT_USAGE,
        )
    _emit_and_exit(
        Envelope(command="memory.show", ok=True, data={"memory_entry": entry.to_dict()}),
        EXIT_OK,
    )


@memory_app.command(name="delete")
def memory_delete(run_id: str) -> None:
    """Tombstone the Memory Entry for ``run_id`` (POSIX-atomic rename)."""
    store = _require_store("memory.delete")
    entries = list_run_history(store)
    target = next(
        (e for e in entries if e.run_record.run_reference.run_id == run_id),
        None,
    )
    if target is None:
        _emit_and_exit(
            Envelope(
                command="memory.delete",
                ok=False,
                errors=(
                    EnvelopeError(
                        code="not-found",
                        message=f"No Memory Entry for run_id={run_id!r}",
                    ),
                ),
            ),
            EXIT_USAGE,
        )
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
            ),
            EXIT_USAGE,
        )
    _emit_and_exit(
        Envelope(
            command="memory.delete",
            ok=True,
            data={"memory_entry": entry.to_dict()},
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
    so coverage verbs surface the same ``not-found`` envelope (exit 2)
    when callers pass a stale or fake run_id.
    """
    entries = list_run_history(store)
    target = next(
        (e for e in entries if e.run_record.run_reference.run_id == run_id),
        None,
    )
    if target is None:
        _emit_and_exit(
            Envelope(
                command=command,
                ok=False,
                errors=(
                    EnvelopeError(
                        code="not-found",
                        message=f"No Memory Entry for run_id={run_id!r}",
                    ),
                ),
            ),
            EXIT_USAGE,
        )
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
    outcome = get_coverage_facts(store, ref)
    _emit_and_exit(
        Envelope(
            command="coverage.show",
            ok=True,
            data={"coverage_outcome": _coverage_outcome_payload(outcome)},
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
    outcome = compare_coverage_facts(store, baseline_ref, target_ref)
    _emit_and_exit(
        Envelope(
            command="coverage.diff",
            ok=True,
            data={"coverage_delta": _coverage_delta_payload(outcome)},
        ),
        EXIT_OK,
    )


def _coverage_delta_payload(
    outcome: CoverageDelta | CoverageUnavailable,
) -> dict[str, Any]:
    """Project a Coverage compare outcome onto the envelope wire shape.

    Two ``kind`` values discriminate at parse time: ``delta`` carries the
    full delta payload (baseline + target references, both summaries, file
    adds/removes, per-file deltas), ``unavailable`` carries the propagated
    reason + detail from whichever side lacked derived facts. The persisted
    ``schema_version`` is intentionally stripped on the wire (envelope
    versioning lives at the top-level ``schema`` field, not inside
    individual data blocks — same convention the ``coverage_outcome``
    projection follows for ``fact-set``).
    """
    if isinstance(outcome, CoverageDelta):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "delta", **body}
    return {
        "kind": "unavailable",
        "run_reference": (
            outcome.run_reference.to_dict()
            if outcome.run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


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
    outcome = compare_runs(store, baseline_ref, target_ref)
    _emit_and_exit(
        Envelope(
            command="regression.compare",
            ok=True,
            data={"regression_outcome": _regression_outcome_payload(outcome)},
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
    outcome = derive_latest_regression(store)
    _emit_and_exit(
        Envelope(
            command="regression.latest",
            ok=True,
            data={"regression_outcome": _regression_outcome_payload(outcome)},
        ),
        EXIT_OK,
    )


@app.command(name="compare")
def compare_cmd(baseline_run_id: str, target_run_id: str) -> None:
    """Composed Regression + Coverage view for a specific pair.

    Emits both ``regression_outcome`` (from ``compare_runs``) and
    ``coverage_delta`` (from ``compare_coverage_facts``) in the same
    envelope. When either side lacks coverage facts, ``coverage_delta``
    surfaces ``kind: "unavailable"`` with the propagated reason — the
    same projection ``coverage diff`` emits. Distinct from
    ``regression compare`` (which emits ``regression_outcome`` only).
    """

    store = _require_store("compare")
    baseline_ref = _resolve_run_reference(store, "compare", baseline_run_id)
    target_ref = _resolve_run_reference(store, "compare", target_run_id)
    regression_outcome = compare_runs(store, baseline_ref, target_ref)
    coverage_outcome = compare_coverage_facts(store, baseline_ref, target_ref)
    _emit_and_exit(
        Envelope(
            command="compare",
            ok=True,
            data={
                "regression_outcome": _regression_outcome_payload(regression_outcome),
                "coverage_delta": _coverage_delta_payload(coverage_outcome),
            },
        ),
        EXIT_OK,
    )


def _regression_outcome_payload(
    outcome: RegressionFactSet | RegressionUnavailable,
) -> dict[str, Any]:
    """Project a Regression outcome onto the envelope wire shape.

    Working draft for this slice — the shape is **not** frozen yet. Per
    ``decisions/2026-05-26-regression-facts-json-layout.md`` §C.2 cadence
    PM freezes the wire shape AFTER Manual Test fields it; until then
    consumers should pattern-match on ``kind`` only (the same advice the
    two Coverage envelope shapes followed before their decisions landed).

    Two ``kind`` values discriminate at parse time: ``fact-set`` carries
    the full persisted body (verbatim ``RegressionFactSet.to_dict()`` with
    ``schema_version`` stripped — envelope versioning lives at the top-
    level ``schema`` field, not inside individual data blocks), and
    ``unavailable`` carries both ``baseline_run_reference`` and
    ``target_run_reference`` as **independently nullable** fields so the
    consumer can tell which side was missing (richer than Coverage's
    single-``run_reference`` Unavailable shape).
    """

    if isinstance(outcome, RegressionFactSet):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "fact-set", **body}
    return {
        "kind": "unavailable",
        "baseline_run_reference": (
            outcome.baseline_run_reference.to_dict()
            if outcome.baseline_run_reference is not None
            else None
        ),
        "target_run_reference": (
            outcome.target_run_reference.to_dict()
            if outcome.target_run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


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
    ``--top-n`` differing from the cached values, the orchestration layer
    invalidates the cache and re-derives at the requested flags
    (``_rederive_if_cache_overrode_flags`` below). The audit signal
    surfaces as the ``localization-cache-rederived`` envelope warning;
    pre-Defect-5 the same condition surfaced as
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
    outcome = derive_localization_findings(
        store, ref, top_n=resolved_top_n, formula=resolved_formula
    )
    outcome, warning = _rederive_if_cache_overrode_flags(
        store=store,
        outcome=outcome,
        resolved_formula=resolved_formula,
        resolved_top_n=resolved_top_n,
        formula_explicit=formula_explicit,
        top_n_explicit=top_n_explicit,
    )
    _emit_and_exit(
        Envelope(
            command="localization",
            ok=True,
            data={"localization_outcome": _localization_outcome_payload(outcome)},
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
    surfaces ``unavailable`` with reason ``no_run_evidence``; a store whose
    runs are all non-analyzable surfaces ``run_not_analyzable``. Flag
    validation mirrors the explicit-run verb.

    Cache-invalidation policy matches the explicit-run verb (Defect 5 fix):
    the ``None`` sentinel defaults let the handler distinguish "user
    explicitly passed this value" from "Cyclopts default in effect", and an
    explicit-flag mismatch against the cached findings triggers a re-derive
    + ``localization-cache-rederived`` warning via
    ``_rederive_if_cache_overrode_flags``.
    """

    store = _require_store("localization.latest")
    formula_explicit = formula is not None
    top_n_explicit = top_n is not None
    resolved_formula = formula if formula is not None else DEFAULT_FORMULA
    resolved_top_n = top_n if top_n is not None else DEFAULT_TOP_N
    _validate_localization_flags(
        "localization.latest", resolved_formula, resolved_top_n
    )
    outcome = derive_latest_localization(
        store, formula=resolved_formula, top_n=resolved_top_n
    )
    outcome, warning = _rederive_if_cache_overrode_flags(
        store=store,
        outcome=outcome,
        resolved_formula=resolved_formula,
        resolved_top_n=resolved_top_n,
        formula_explicit=formula_explicit,
        top_n_explicit=top_n_explicit,
    )
    _emit_and_exit(
        Envelope(
            command="localization.latest",
            ok=True,
            data={"localization_outcome": _localization_outcome_payload(outcome)},
            warnings=(warning,) if warning is not None else (),
        ),
        EXIT_OK,
    )


def _rederive_if_cache_overrode_flags(
    *,
    store: ProjectStore,
    outcome: LocalizationFinding | LocalizationUnavailable,
    resolved_formula: str,
    resolved_top_n: int,
    formula_explicit: bool,
    top_n_explicit: bool,
) -> tuple[
    LocalizationFinding | LocalizationUnavailable,
    EnvelopeWarning | None,
]:
    """Cache-invalidation policy gate (Defect 5 fix, 2026-06-01).

    Pre-Defect-5 behavior: when the engine served from cache while the user
    explicitly passed ``--formula`` / ``--top-n`` differing from the cached
    values, the CLI surfaced a ``localization-cache-args-ignored`` warning
    AND returned the stale cached finding (so the AI agent saw a wire
    envelope claiming ``formula: "ochiai"`` while their request said
    ``--formula=op2``). The warning disclosed the bug; the behavior was
    still wrong.

    Post-Defect-5: same detection model — explicit-and-different becomes
    the trigger — but instead of returning stale + warning, we INVALIDATE
    the cache (unlink the on-disk ``localization_findings.json``) and
    invoke ``derive_localization_findings`` again. The second call sees a
    cache miss and runs the full pipeline at the requested flags,
    persisting the fresh result. The audit signal is preserved via a new
    warning code ``localization-cache-rederived`` whose details carry the
    PREVIOUS cached (formula, top_n) pair plus the resolved request — so
    AI agents know they paid the re-compute cost and what the cache used
    to be.

    Detection model — "peek-after-call" via the returned
    ``LocalizationFinding``:

    - A fresh derive (no prior cache) always returns a finding whose
      ``formula`` / ``top_n`` match the values passed to the engine
      (because the engine writes them straight onto the payload). So if
      ``outcome.formula == resolved_formula`` AND
      ``outcome.top_n == resolved_top_n``, either there was no prior
      cache OR the prior cache's stored flags happened to match — both
      cases require no re-derive.
    - A cache hit returns the cached finding verbatim, so its
      ``formula`` / ``top_n`` reflect the FLAGS the cache was originally
      derived with. A mismatch on either field — combined with the user
      having explicitly passed that flag — is the precise condition for
      cache invalidation + re-derive.
    - When the outcome is ``LocalizationUnavailable``, there's nothing
      cached to honor (or the engine pre-empted with an error reason);
      pass through.

    Per scope §1 of the task brief, the ``*_explicit`` gating means a
    defaulted flag that happens to differ from the cache produces NO
    re-derive for that flag — the user did not ask for a specific value
    so the cached choice stands.

    The on-disk path layout is pinned by ``localization/persistence.py``;
    we use the canonical ``localization_findings_path`` helper to compute
    the file to unlink so the invalidation point stays load-bearing-
    aligned with Memory's availability probe and the persistence layer's
    write path.
    """
    if not isinstance(outcome, LocalizationFinding):
        return outcome, None
    cached_formula = outcome.formula
    cached_top_n = outcome.top_n
    formula_mismatch = formula_explicit and resolved_formula != cached_formula
    top_n_mismatch = top_n_explicit and resolved_top_n != cached_top_n
    if not (formula_mismatch or top_n_mismatch):
        return outcome, None

    # Defect 7 fix (2026-06-08): ``failure_proximity`` mode reports
    # ``formula = "ochiai"`` as a structural placeholder regardless of
    # ``--formula`` input (the mode runs a heuristic frequency count, not
    # any SBFL formula — see ``localization/failure_proximity.py::
    # _PLACEHOLDER_FORMULA``). A formula-mismatch against this placeholder
    # is therefore a structural noop: re-deriving cannot resolve it
    # (engine returns the same placeholder on every call), and the
    # cache-rederived warning would keep firing on every user retry —
    # an infinite warning loop visible to AI agents iterating on the
    # ``--formula`` flag. Skip the re-derive and surface a distinct
    # ``localization-formula-noop-in-mode`` warning so the AI consumer
    # recognizes this as "structural noop, do not retry" rather than
    # "fixable misconfig, retry with a different value".
    #
    # NOTE: a ``top_n`` mismatch in ``failure_proximity`` mode IS still
    # meaningful (the entry-count of the heuristic ranking changes), so
    # this carve-out only applies when ``formula_mismatch`` is the
    # *sole* trigger. A failure_proximity run with ``top_n_mismatch``
    # (whether or not formula also mismatches) still goes through the
    # normal re-derive path so the user's top_n request takes effect;
    # the cache-rederived warning's ``previous`` field discloses the
    # formula placeholder transition without needing a second warning.
    is_failure_proximity_formula_noop = (
        outcome.mode == "failure_proximity"
        and formula_mismatch
        and not top_n_mismatch
    )
    if is_failure_proximity_formula_noop:
        warning = _build_localization_formula_noop_warning(
            requested_formula=resolved_formula,
            returned_formula=cached_formula,
            mode=outcome.mode,
        )
        return outcome, warning

    # Cache hit served stale-vs-explicit-flags. Invalidate the persisted
    # findings file so the second derive call sees a cache miss and runs
    # the full pipeline at the requested flags.
    run_reference = outcome.run_reference
    previous_cached_args = (cached_formula, cached_top_n)
    localization_findings_path(store, run_reference.run_id).unlink(missing_ok=True)
    fresh = derive_localization_findings(
        store,
        run_reference,
        top_n=resolved_top_n,
        formula=resolved_formula,
    )
    warning = _build_localization_cache_rederived_warning(
        run_id=run_reference.run_id,
        previous_cached_args=previous_cached_args,
        resolved_formula=resolved_formula,
        resolved_top_n=resolved_top_n,
        formula_explicit=formula_explicit,
        top_n_explicit=top_n_explicit,
    )
    return fresh, warning


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

    The caller (``_rederive_if_cache_overrode_flags``) has already
    determined that a re-derive happened, so this helper always emits a
    warning — its job is just payload construction. The ``details`` shape
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
    keeps the orchestration layer self-contained.
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

    Emitted by ``_rederive_if_cache_overrode_flags`` when the user passes
    an explicit ``--formula`` that mismatches the cached/returned value
    AND the engine's mode is one whose formula field is a structural
    placeholder rather than a real selection (today: only
    ``failure_proximity``, which always reports ``formula = "ochiai"``
    regardless of input — see ``localization/failure_proximity.py::
    _PLACEHOLDER_FORMULA``).

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


def _localization_outcome_payload(
    outcome: LocalizationFinding | LocalizationUnavailable,
) -> dict[str, Any]:
    """Project a Localization outcome onto the working-draft wire shape.

    Working draft for this slice — PM freezes it via a follow-up decision
    after Manual Test fields it (the 4th application of the ship →
    field-test → freeze cadence Coverage and Regression followed). Two
    ``kind`` values discriminate at parse time: ``fact-set`` carries the
    full persisted body (verbatim ``LocalizationFinding.to_dict()`` with the
    top-level ``schema_version`` stripped — envelope versioning lives at the
    top-level ``schema`` field, not inside data blocks), and ``unavailable``
    carries the 3-key ``LocalizationUnavailable.to_dict()`` (``run_reference``
    / ``reason`` / ``detail``, all always present; ``run_reference`` is
    ``null`` for the latest-resolution empty / non-analyzable cases). The
    nested ``LocalizationEntry`` / ``CodeLocation`` / ``EvidenceCitation``
    shapes round-trip verbatim — the projection's only job is to add ``kind``
    and strip the top-level ``schema_version``.
    """
    if isinstance(outcome, LocalizationFinding):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "fact-set", **body}
    return {"kind": "unavailable", **outcome.to_dict()}


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
    until its engine lands in Phase 5. ``inspect`` executes nothing — it is
    a pure read over stored evidence (no derivation, no subprocess).

    A stale or fake ``run_id`` surfaces a structured ``not-found`` error
    (exit 2), mirroring ``memory show``. Tombstoned runs remain inspectable.
    """
    store = _require_store("inspect")
    view = build_inspect_view(store, run_id)
    if view is None:
        _emit_and_exit(
            Envelope(
                command="inspect",
                ok=False,
                errors=(
                    EnvelopeError(
                        code="not-found",
                        message=f"No Memory Entry for run_id={run_id!r}",
                    ),
                ),
            ),
            EXIT_USAGE,
        )
    _emit_and_exit(
        Envelope(command="inspect", ok=True, data=view.to_dict()),
        EXIT_OK,
    )


# ---------------------------------------------------------------------------
# Integrated `novetest test [target]` workflow (Phase 6 entry)
# ---------------------------------------------------------------------------


@app.command(name="test")
def test_cmd(target: str = "") -> None:
    """Execute the integrated `novetest test [target]` workflow.

    Chains Run → Memory → Coverage → Regression → Localization →
    Recommendation synthesis. Stage failures (no baseline, no coverage,
    etc.) are surfaced via the ``data.stage_eligibility`` block — the
    workflow does NOT abort on a single-engine outage (brief §5 — Error
    policy). Run execution (step 2) is fatal; the handler maps the same
    exception surface ``run_cmd`` does (``EngineNotReadyError`` +
    ``AdapterInvocationError``) and re-uses the same envelope shape.

    Recommendations are synthesized in-memory from the
    ``FactBundle`` — never persisted (Open Q #9 / brief §2). Re-deriving
    against the same evidence yields a byte-identical recommendation
    list (determinism contract, design doc §4).

    The ``data.run_reference`` / ``data.stage_eligibility`` /
    ``data.recommendation_schema_version`` / ``data.recommendations``
    fields are the wire surface AI agents pin against (brief §5).
    """

    store = _require_store("test")
    try:
        outcome = asyncio.run(test_target_in_store(target, store))
    except EngineNotReadyError as exc:
        _emit_and_exit(
            Envelope(
                command="test",
                ok=False,
                data={"engine_readiness": _readiness_payload(exc.readiness)},
                errors=(
                    EnvelopeError(
                        code=f"engine-{exc.readiness.state}",
                        message=str(exc),
                    ),
                ),
            ),
            EXIT_ENGINE_MISSING,
        )
    except AdapterInvocationError as exc:
        _emit_and_exit(
            Envelope(
                command="test",
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
            EXIT_ENGINE_MISSING,
        )

    envelope, exit_code = build_test_envelope(outcome)
    _emit_and_exit(envelope, exit_code)


# ---------------------------------------------------------------------------
# `novetest replay <run_id>` verb (Phase 5 entry)
# ---------------------------------------------------------------------------


def _replay_outcome_payload(
    outcome: ReplayResult | ReplayUnavailable,
) -> dict[str, Any]:
    """Project a Replay outcome onto the frozen ``replay_outcome`` block.

    Identical wire shape to ``workflows/inspect.py::_replay_outcome_section``
    (the two cannot share without an orchestration↔cli import cycle). A
    ``ReplayResult`` surfaces as ``kind: "replay-result"`` with the full
    classification block (the original ``run_reference`` is dropped — the
    envelope carries it as ``data.original_run_reference``); a
    ``ReplayUnavailable`` surfaces as the 3-key ``kind: "unavailable"`` block.
    """
    if isinstance(outcome, ReplayResult):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        body.pop("run_reference", None)
        return {"kind": "replay-result", **body}
    return {"kind": "unavailable", **outcome.to_dict()}


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
        "replay_outcome": _replay_outcome_payload(outcome),
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
    outcome = asyncio.run(
        replay_run(store, original_ref, reruns=reruns, timeout=timeout)
    )
    envelope, exit_code = _build_replay_envelope(original_ref, outcome)
    _emit_and_exit(envelope, exit_code)


# ---------------------------------------------------------------------------
# Remaining stubs (not in Phase 1 Run+Memory scope)
# ---------------------------------------------------------------------------


def _register_flat_stub(name: str) -> None:
    stub = _make_stub(name)
    app.command(stub, name=name)


def _register_group_stub(group: str, verbs: tuple[str, ...]) -> None:
    sub = App(name=group, help=f"{group} commands (stub - not yet implemented).")
    app.command(sub)
    for verb in verbs:
        stub = _make_stub(f"{group}.{verb}")
        sub.command(stub, name=verb)


# ``compare`` promoted to a real verb above.
# ``regression`` promoted to a real sub-app above.
# ``test`` promoted to a real verb (Phase 6 entry).
# ``replay`` promoted to a real verb above (Phase 5 entry).


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
