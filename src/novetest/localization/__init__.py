"""Localization engine — SBFL-based fault localization.

Phase 4 entry slice produced the per-test path; the 2026-05-31
fallback-modes slice closes the remaining two modes:

- ``sbfl_per_test``    — per-test coverage path (Ochiai default; Op2,
                          DStar(*=2), Tarantula computed in parallel and
                          persisted under ``LocalizationEntry.alternate_scores``).
                          ``confidence: "high"``.
- ``sbfl_aggregate``   — file-level FLUCCS-style ranking when coverage is
                          aggregate / per-test-file / per-test-class.
                          ``confidence: "medium"``. Regression-aware
                          reweighting (Sohn & Yoo ISSTA 2017) applies the
                          ``score *= (1 + 0.5)`` boost to files in the
                          regression "changed_files" set; the floor is
                          failure-only Ochiai with the same shape.
- ``failure_proximity``— last-resort ranking when no coverage exists.
                          File-level. Ranks by failing-test failure-log
                          mention counts + the same FLUCCS prior.
                          ``confidence: "low"``. NOT SBFL (no spectra
                          matrix, no formula computation); the wire-shape
                          deviation is documented in the brief §7 and on
                          the module docstring.

Public API exposes the Internal interfaces from
``design/interace-contract/localization.md`` that this engine
implements:

- ``derive_localization_findings``      — engine entry point (cache-aware,
                                          mode-dispatched).
- ``get_localization_findings``         — cache-read helper.
- ``check_localization_availability``   — eligibility probe (bool) for the
                                          per-test path.
- ``resolve_latest_analyzable_run``     — cheap "which run can be localized"
                                          resolver over Run History.
- ``derive_latest_localization``        — composition of the previous two
                                          (latest-analyzable → derive).
- ``try_get_latest_regression_facts``   — best-effort regression-prior
                                          probe; returns ``None`` when no
                                          comparable baseline pair has
                                          cached Regression Facts.
- ``parse_failure_log`` /
  ``resolve_failure_text`` /
  ``derive_failure_proximity``          — failure_proximity sub-module
                                          surface; useful for unit tests
                                          and future per-engine parser
                                          extensions.

Plus the discriminator types callers need to ``isinstance``-match the
unavailable outcome (``LocalizationUnavailable`` + the five
``REASON_*`` constants).

The persisted wire shape for ``localization_findings.json`` is pinned by
``agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md``;
the ``failure_proximity`` mode introduces one documented deviation
(``alternate_scores_available == ()`` and per-entry ``alternate_scores
== {}``) called out in the brief §7 — PM may amend the freeze decision
post-slice or just narrate the deviation in history.

Symbol resolvers ship Python only; other ecosystems use file-level
``CodeLocation(kind="file")`` as the v1 fallback per strategy doc §3.
"""

from novetest.localization.derive import (
    DEFAULT_FORMULA,
    DEFAULT_TOP_N,
    derive_latest_localization,
    derive_localization_findings,
    resolve_latest_analyzable_run,
    try_get_latest_regression_facts,
)
from novetest.localization.failure_proximity import (
    derive_failure_proximity,
    parse_failure_log,
    resolve_failure_text,
)
from novetest.localization.results import (
    KNOWN_REASONS,
    REASON_MISSING_DERIVED_FACTS,
    REASON_NO_COVERAGE,
    REASON_NO_FAILED_TESTS,
    REASON_NO_RUN_EVIDENCE,
    REASON_RUN_NOT_ANALYZABLE,
    LocalizationUnavailable,
)
from novetest.localization.retrieval import (
    check_localization_availability,
    get_localization_findings,
)
from novetest.models.localization_finding import (
    CODE_LOCATION_KINDS,
    EVIDENCE_KINDS,
    FORMULAS,
    LOCALIZATION_CONFIDENCES,
    LOCALIZATION_MODES,
    SCHEMA_VERSION,
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
    LocalizationFinding,
)


__all__ = [
    "CODE_LOCATION_KINDS",
    "CodeLocation",
    "DEFAULT_FORMULA",
    "DEFAULT_TOP_N",
    "EVIDENCE_KINDS",
    "EvidenceCitation",
    "FORMULAS",
    "KNOWN_REASONS",
    "LOCALIZATION_CONFIDENCES",
    "LOCALIZATION_MODES",
    "LocalizationEntry",
    "LocalizationFinding",
    "LocalizationUnavailable",
    "REASON_MISSING_DERIVED_FACTS",
    "REASON_NO_COVERAGE",
    "REASON_NO_FAILED_TESTS",
    "REASON_NO_RUN_EVIDENCE",
    "REASON_RUN_NOT_ANALYZABLE",
    "SCHEMA_VERSION",
    "check_localization_availability",
    "derive_failure_proximity",
    "derive_latest_localization",
    "derive_localization_findings",
    "get_localization_findings",
    "parse_failure_log",
    "resolve_failure_text",
    "resolve_latest_analyzable_run",
    "try_get_latest_regression_facts",
]
