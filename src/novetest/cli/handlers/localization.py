"""Localization handlers: ``localization <run_id>`` / ``localization latest``.

Extracted verbatim from ``cli/app.py`` at the W3/S47 decomposition (ORC-01),
including the flag validator (``_validate_localization_flags``) and the
transport-owned cache-policy warning builders (``_localization_audit_warning``
/ ``_build_localization_cache_rederived_warning`` /
``_build_localization_formula_noop_warning``). The cache-invalidation POLICY
itself lives in ``orchestration/workflows/localization.py`` (W2/S22); this
module only maps the workflow's audit structure onto envelope warnings. Pure
motion — the wire contract is unchanged.
"""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter

from novetest.cli._shared import (
    _emit_and_exit,
    _require_store,
    _resolve_run_reference,
    _store_corrupt_envelope,
)
from novetest.cli.output import (
    EXIT_OK,
    EXIT_STORAGE,
    EXIT_USAGE,
    Envelope,
    EnvelopeError,
    EnvelopeWarning,
)
from novetest.localization import DEFAULT_FORMULA, DEFAULT_TOP_N, FORMULAS
from novetest.memory import ProjectStoreCorruptError
from novetest.orchestration.projection import localization_outcome_payload
from novetest.orchestration.workflows import (
    CacheRederivedAudit,
    LocalizationAudit,
    derive_latest_localization_with_flag_policy,
    derive_localization_with_flag_policy,
)


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
