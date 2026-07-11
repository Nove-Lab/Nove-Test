"""``novetest localization`` workflows — flag-override cache policy (W2/S22).

Owns the Defect-5/Defect-7 cache-invalidation policy that previously
lived inline in ``cli/app.py`` (ORC-07 / XCT-02): explicit-flag
detection against the cache-served finding, cache invalidation through
the Localization engine's public ``invalidate_localization_findings``
API (never a direct file unlink — the on-disk layout stays engine-owned),
re-derive at the requested flags, and the decision of WHICH audit signal
the transport should surface.

The CLI is transport-only on this path: it parses flags, calls one of
the two workflow entry points below, and projects the returned audit
structure onto an ``EnvelopeWarning`` (warning construction stays in
``cli/app.py`` — this module never imports ``novetest.cli``).

Policy history:

- **Defect 5 fix (2026-06-01):** a cache hit that overrode explicitly
  passed ``--formula`` / ``--top-n`` used to return the stale cached
  finding with a ``localization-cache-args-ignored`` warning. Post-fix
  the cache is invalidated and the derive re-runs at the requested
  flags; the audit signal is the ``localization-cache-rederived``
  warning (built by the CLI from :class:`CacheRederivedAudit`).
- **Defect 7 fix (2026-06-08):** ``failure_proximity`` mode pins
  ``formula = "ochiai"`` as a structural placeholder, so a formula-only
  mismatch in that mode is a re-derive noop; the policy skips the
  re-derive and reports :class:`FormulaNoopAudit` instead (surfaced as
  the ``localization-formula-noop-in-mode`` warning) — breaking the
  pre-fix infinite warning loop.
"""

from __future__ import annotations

from dataclasses import dataclass

from novetest.localization import (
    LocalizationFinding,
    LocalizationUnavailable,
    derive_latest_localization,
    derive_localization_findings,
    invalidate_localization_findings,
)
from novetest.memory import ProjectStore
from novetest.models import RunReference


@dataclass(slots=True, frozen=True)
class CacheRederivedAudit:
    """Audit record for a cache-invalidation + re-derive event.

    Carries exactly what the CLI needs to build the
    ``localization-cache-rederived`` warning: the run whose cache was
    invalidated, the PREVIOUS cached ``(formula, top_n)`` pair, and the
    resolved request (values + explicitness flags). The workflow decides
    THAT the event happened; the CLI owns the wire wording.
    """

    run_id: str
    previous_formula: str
    previous_top_n: int
    requested_formula: str
    requested_top_n: int
    formula_explicit: bool
    top_n_explicit: bool


@dataclass(slots=True, frozen=True)
class FormulaNoopAudit:
    """Audit record for the Defect-7 structural formula noop.

    Emitted when an explicit ``--formula`` mismatches the returned
    finding but the finding's mode pins the formula as a placeholder
    (today: only ``failure_proximity``) — re-deriving cannot honor the
    request, so the policy deliberately skips it. The CLI projects this
    as the ``localization-formula-noop-in-mode`` warning ("structural
    noop, do not retry").
    """

    requested_formula: str
    returned_formula: str
    mode: str


LocalizationAudit = CacheRederivedAudit | FormulaNoopAudit


def derive_localization_with_flag_policy(
    store: ProjectStore,
    run_reference: RunReference,
    *,
    formula: str,
    top_n: int,
    formula_explicit: bool,
    top_n_explicit: bool,
) -> tuple[
    LocalizationFinding | LocalizationUnavailable,
    LocalizationAudit | None,
]:
    """Derive findings for ``run_reference`` under the flag-override policy.

    Composition behind ``novetest localization <run_id>``: call the
    engine's cache-aware ``derive_localization_findings`` at the resolved
    flags, then apply :func:`_apply_flag_override_policy` to the outcome.
    ``formula`` / ``top_n`` are the RESOLVED values (defaults already
    substituted); the ``*_explicit`` booleans say whether the user passed
    each flag — the CLI's ``None``-sentinel parse is the only place that
    distinction can be observed.
    """
    outcome = derive_localization_findings(
        store, run_reference, top_n=top_n, formula=formula
    )
    return _apply_flag_override_policy(
        store=store,
        outcome=outcome,
        resolved_formula=formula,
        resolved_top_n=top_n,
        formula_explicit=formula_explicit,
        top_n_explicit=top_n_explicit,
    )


def derive_latest_localization_with_flag_policy(
    store: ProjectStore,
    *,
    formula: str,
    top_n: int,
    formula_explicit: bool,
    top_n_explicit: bool,
) -> tuple[
    LocalizationFinding | LocalizationUnavailable,
    LocalizationAudit | None,
]:
    """Derive findings for the latest analyzable run under the flag policy.

    Composition behind ``novetest localization latest``: the engine's
    ``derive_latest_localization`` resolves the newest analyzable run and
    derives; the flag-override policy then applies exactly as on the
    explicit-run path (the re-derive, when triggered, calls
    ``derive_localization_findings`` directly — the run_reference is
    already resolved by the first call's returned finding).
    """
    outcome = derive_latest_localization(store, formula=formula, top_n=top_n)
    return _apply_flag_override_policy(
        store=store,
        outcome=outcome,
        resolved_formula=formula,
        resolved_top_n=top_n,
        formula_explicit=formula_explicit,
        top_n_explicit=top_n_explicit,
    )


def _apply_flag_override_policy(
    *,
    store: ProjectStore,
    outcome: LocalizationFinding | LocalizationUnavailable,
    resolved_formula: str,
    resolved_top_n: int,
    formula_explicit: bool,
    top_n_explicit: bool,
) -> tuple[
    LocalizationFinding | LocalizationUnavailable,
    LocalizationAudit | None,
]:
    """Cache-invalidation policy gate (Defect 5 fix, 2026-06-01).

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

    The ``*_explicit`` gating means a defaulted flag that happens to
    differ from the cache produces NO re-derive for that flag — the user
    did not ask for a specific value so the cached choice stands.

    Invalidation goes through the Localization engine's public
    ``invalidate_localization_findings(store, run_id)`` API — the on-disk
    findings layout is the engine's own concern (XCT-02); this workflow
    never touches engine file paths.
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
    # ``--formula`` flag. Skip the re-derive and report the distinct
    # noop audit so the transport can tell the consumer "structural
    # noop, do not retry" rather than "fixable misconfig, retry with a
    # different value".
    #
    # NOTE: a ``top_n`` mismatch in ``failure_proximity`` mode IS still
    # meaningful (the entry-count of the heuristic ranking changes), so
    # this carve-out only applies when ``formula_mismatch`` is the
    # *sole* trigger. A failure_proximity run with ``top_n_mismatch``
    # (whether or not formula also mismatches) still goes through the
    # normal re-derive path so the user's top_n request takes effect;
    # the cache-rederived audit's ``previous`` fields disclose the
    # formula placeholder transition without needing a second signal.
    is_failure_proximity_formula_noop = (
        outcome.mode == "failure_proximity"
        and formula_mismatch
        and not top_n_mismatch
    )
    if is_failure_proximity_formula_noop:
        return outcome, FormulaNoopAudit(
            requested_formula=resolved_formula,
            returned_formula=cached_formula,
            mode=outcome.mode,
        )

    # Cache hit served stale-vs-explicit-flags. Invalidate the persisted
    # findings so the second derive call sees a cache miss and runs the
    # full pipeline at the requested flags.
    run_reference = outcome.run_reference
    invalidate_localization_findings(store, run_reference.run_id)
    fresh = derive_localization_findings(
        store,
        run_reference,
        top_n=resolved_top_n,
        formula=resolved_formula,
    )
    audit = CacheRederivedAudit(
        run_id=run_reference.run_id,
        previous_formula=cached_formula,
        previous_top_n=cached_top_n,
        requested_formula=resolved_formula,
        requested_top_n=resolved_top_n,
        formula_explicit=formula_explicit,
        top_n_explicit=top_n_explicit,
    )
    return fresh, audit


__all__ = [
    "CacheRederivedAudit",
    "FormulaNoopAudit",
    "LocalizationAudit",
    "derive_latest_localization_with_flag_policy",
    "derive_localization_with_flag_policy",
]
