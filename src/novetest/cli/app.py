from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Any, Callable, NoReturn

from cyclopts import App, Parameter

from novetest import __version__
from novetest.cli.output import (
    EXIT_ENGINE_MISSING,
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_STORAGE,
    EXIT_USAGE,
    EXIT_USER_TESTS_FAILED,
    Envelope,
    EnvelopeError,
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
from novetest.memory import (
    ProjectStore,
    ProjectStoreCorruptError,
    RunEvidenceNotFoundError,
    delete_run_evidence,
    list_run_history,
    locate_project_store,
    retrieve_run_evidence,
)
from novetest.models import RunReference
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.orchestration.onboarding.command_surface import describe_command_surface
from novetest.orchestration.onboarding.identity import report_cli_identity
from novetest.orchestration.workflows import (
    build_status_view,
    initialize_project_workspace,
    run_target_in_store,
)
from novetest.run import AdapterInvocationError, EngineNotReadyError


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
        "init",
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
    _emit_and_exit(Envelope(command="run", ok=ok, data=data), exit_code)


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


for _name in ("test", "inspect", "compare", "replay", "localization"):
    _register_flat_stub(_name)
_register_group_stub("regression", ("compare", "latest"))


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
