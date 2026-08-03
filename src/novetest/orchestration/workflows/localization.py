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
- **Row-41 determinism fix (2026-08-03):** the mismatch check used to be
  gated on ``*_explicit``, so a DEFAULTED flag that differed from the
  cache produced no re-derive — a bare ``localization latest`` served
  back whatever formula was last explicitly requested (``ochiai`` ->
  ``--formula op2`` -> bare call still ``op2``), making the same command
  on the same inputs history-dependent (REQ-FOUND). The mismatch is now
  computed on the RESOLVED values alone; ``*_explicit`` survives only as
  audit disclosure on :class:`CacheRederivedAudit`. Explicit flags still
  win over the cache exactly as Defect 5 made them.
- **Row-43 stale-build fix (2026-08-03):** the derived finding is cached
  per run reference with no version component, so a store written by a
  pre-``088091e`` build served its ranking back verbatim under a current
  build — ``ok: true``, exit 0, no warning — reintroducing the very
  test-file misroute the SBFL exclusion work removed. The policy now
  applies the documented four-key detector (an SBFL-mode finding whose
  ``metadata`` lacks ``test_file_exclusion_basis`` cannot have been
  derived by a build carrying ``derive.py::_exclusion_metadata``),
  invalidates and re-derives, and reports the distinct
  :class:`StaleBuildRederivedAudit` (``localization-stale-build-rederived``
  warning) so a consumer can tell a stale-build re-derive from a flag
  override.
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


# Modes whose findings are produced by the two SBFL pipelines in
# ``localization/derive.py``. Both call ``_exclusion_metadata``, so both
# ALWAYS publish ``test_file_exclusion_basis``. ``failure_proximity`` does
# not (it is not an SBFL mode in this sense) and is deliberately excluded
# from the staleness check below.
_SBFL_MODES: frozenset[str] = frozenset({"sbfl_per_test", "sbfl_aggregate"})

# The staleness tell (row 43). ``localization/derive.py::_exclusion_metadata``
# — the single renderer both SBFL modes use — has published this key on every
# finding since ``088091e`` (v0.3.0). A fresh derive by THIS build therefore
# cannot lack it, so an SBFL-mode finding without it can only have come from
# the on-disk cache, written by an older build. Documented as the consumer-
# facing rule in ``docs/release-notes/v0.3.0.md`` and
# ``design/interace-contract/localization.md``; this constant is where the
# same rule is enforced.
_EXCLUSION_BASIS_KEY: str = "test_file_exclusion_basis"


@dataclass(slots=True, frozen=True)
class CacheRederivedAudit:
    """Audit record for a cache-invalidation + re-derive event.

    Carries exactly what the CLI needs to build the
    ``localization-cache-rederived`` warning: the run whose cache was
    invalidated, the PREVIOUS cached ``(formula, top_n)`` pair, and the
    resolved request (values + explicitness flags). The workflow decides
    THAT the event happened; the CLI owns the wire wording.

    Since the row-41 fix the ``*_explicit`` booleans no longer gate the
    mismatch — they are pure disclosure, telling a consumer whether the
    re-derive honored a flag the user typed or the flag's DEFAULT value.
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


@dataclass(slots=True, frozen=True)
class StaleBuildRederivedAudit:
    """Audit record for the row-43 stale-build cache invalidation.

    Emitted when the served finding is an SBFL-mode payload whose
    ``metadata`` lacks ``test_file_exclusion_basis`` — impossible for a
    finding derived by this build, therefore a cached payload written by
    a build older than ``088091e``. The policy invalidates and re-derives
    at the resolved flags; the CLI projects this as the
    ``localization-stale-build-rederived`` warning.

    Deliberately distinct from :class:`CacheRederivedAudit`: nothing about
    the user's FLAGS was wrong, so a consumer reading ``warnings[].code``
    must be able to tell "your cached ranking predates the test-file
    exclusion fix" from "your explicit flag overrode the cache".
    """

    run_id: str
    mode: str
    missing_metadata_key: str
    requested_formula: str
    requested_top_n: int


LocalizationAudit = CacheRederivedAudit | FormulaNoopAudit | StaleBuildRederivedAudit


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
      cases require no re-derive on FLAG grounds.
    - A cache hit returns the cached finding verbatim, so its
      ``formula`` / ``top_n`` reflect the FLAGS the cache was originally
      derived with. A mismatch on either field is the precise condition
      for cache invalidation + re-derive.
    - When the outcome is ``LocalizationUnavailable``, there's nothing
      cached to honor (or the engine pre-empted with an error reason);
      pass through.

    Row-41 fix (2026-08-03): the mismatch is computed on the RESOLVED
    values only. ``resolved_formula`` / ``resolved_top_n`` already carry
    the defaults (``DEFAULT_FORMULA`` / ``DEFAULT_TOP_N``) substituted by
    the caller, so an omitted flag now means "give me the default value",
    not "keep whatever the cache holds". Pre-fix the mismatch was gated
    on ``*_explicit``, which made a bare ``localization latest`` return
    the last EXPLICITLY requested formula — same command, same inputs,
    history-dependent answer. The ``*_explicit`` booleans remain in the
    signature because :class:`CacheRederivedAudit` discloses them; they
    no longer decide anything.

    Row-43 fix (2026-08-03): when the flags agree, the remaining reason
    to distrust the served payload is the build that derived it — see
    :func:`_is_stale_build_finding`. That check runs ONLY on the
    flags-agree path: when a flag mismatch already forces a re-derive,
    the payload is refreshed by this build anyway and the
    ``localization-cache-rederived`` warning already discloses it, so a
    second signal would add nothing.

    Invalidation goes through the Localization engine's public
    ``invalidate_localization_findings(store, run_id)`` API — the on-disk
    findings layout is the engine's own concern (XCT-02); this workflow
    never touches engine file paths.
    """
    if not isinstance(outcome, LocalizationFinding):
        return outcome, None
    cached_formula = outcome.formula
    cached_top_n = outcome.top_n
    formula_mismatch = resolved_formula != cached_formula
    top_n_mismatch = resolved_top_n != cached_top_n
    if not (formula_mismatch or top_n_mismatch):
        if not _is_stale_build_finding(outcome):
            return outcome, None
        run_reference = outcome.run_reference
        fresh = _invalidate_and_rederive(
            store=store,
            run_reference=run_reference,
            formula=resolved_formula,
            top_n=resolved_top_n,
        )
        return fresh, StaleBuildRederivedAudit(
            run_id=run_reference.run_id,
            mode=outcome.mode,
            missing_metadata_key=_EXCLUSION_BASIS_KEY,
            requested_formula=resolved_formula,
            requested_top_n=resolved_top_n,
        )

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
    #
    # Row-41 interaction (2026-08-03), the reason the loop did NOT come
    # back when defaulted flags started counting as mismatches: the
    # placeholder IS ``DEFAULT_FORMULA`` (both ``"ochiai"``), so a bare
    # call in this mode produces no formula mismatch at all and never
    # reaches here. Only an explicitly-typed non-ochiai ``--formula``
    # does — one warning per invocation, no re-derive, exactly as
    # Defect 7 specified. If ``DEFAULT_FORMULA`` and
    # ``failure_proximity``'s ``_PLACEHOLDER_FORMULA`` ever diverge, the
    # bare-call path starts landing here and the carve-out (not the
    # mismatch computation) is what keeps it single-shot.
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

    # Cache hit served flags other than the resolved ones. Invalidate the
    # persisted findings so the second derive call sees a cache miss and
    # runs the full pipeline at the requested flags.
    run_reference = outcome.run_reference
    fresh = _invalidate_and_rederive(
        store=store,
        run_reference=run_reference,
        formula=resolved_formula,
        top_n=resolved_top_n,
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


def _is_stale_build_finding(finding: LocalizationFinding) -> bool:
    """Was this finding derived by a build older than the exclusion fix?

    The four-key detector, exactly as documented for consumers: an SBFL
    mode (``sbfl_per_test`` / ``sbfl_aggregate``) whose ``metadata`` has
    no ``test_file_exclusion_basis``. Both SBFL pipelines render that key
    unconditionally through ``derive.py::_exclusion_metadata``, so this
    build cannot produce such a finding — it can only have been read back
    from the on-disk cache, written by a build predating ``088091e``.
    Serving it verbatim silently reintroduces the test-file misroute the
    exclusion work exists to eliminate (row 43).

    ``failure_proximity`` is excluded BY DESIGN: it never carried those
    keys, on any build, so their absence says nothing about its age.
    Evaluated purely from the already-returned finding — the engine's
    cache-read boundary stays policy-free (S22).
    """
    return (
        finding.mode in _SBFL_MODES
        and _EXCLUSION_BASIS_KEY not in finding.metadata
    )


def _invalidate_and_rederive(
    *,
    store: ProjectStore,
    run_reference: RunReference,
    formula: str,
    top_n: int,
) -> LocalizationFinding | LocalizationUnavailable:
    """Drop the persisted findings, then derive fresh at ``formula``/``top_n``.

    The one place both re-derive triggers (flag mismatch, stale build)
    converge, so they cannot drift in HOW they invalidate: always the
    engine's public ``invalidate_localization_findings`` (never a direct
    unlink — XCT-02), always followed by exactly one derive call, which
    now sees a cache miss and runs the full pipeline.
    """
    invalidate_localization_findings(store, run_reference.run_id)
    return derive_localization_findings(
        store,
        run_reference,
        top_n=top_n,
        formula=formula,
    )


__all__ = [
    "CacheRederivedAudit",
    "FormulaNoopAudit",
    "LocalizationAudit",
    "StaleBuildRederivedAudit",
    "derive_latest_localization_with_flag_policy",
    "derive_localization_with_flag_policy",
]
