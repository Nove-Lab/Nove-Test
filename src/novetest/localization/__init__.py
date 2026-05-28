"""Localization engine — SBFL-based fault localization.

Phase 4 entry slice. Produces ranked Code Locations from per-test
Coverage Facts + failed Test Results using the four canonical SBFL
formulas (Ochiai default; Op2, DStar(*=2), Tarantula computed in
parallel and persisted under ``LocalizationEntry.alternate_scores``).

Public API exposes the Internal interfaces from
``design/interace-contract/localization.md`` that this engine
implements:

- ``derive_localization_findings``      — engine entry point (cache-aware).
- ``get_localization_findings``         — cache-read helper.
- ``check_localization_availability``   — eligibility probe (bool).
- ``resolve_latest_analyzable_run``     — cheap "which run can be localized"
                                          resolver over Run History.
- ``derive_latest_localization``        — composition of the previous two
                                          (latest-analyzable → derive).

Plus the discriminator types callers need to ``isinstance``-match the
unavailable outcome (``LocalizationUnavailable`` + the five
``REASON_*`` constants).

Explicitly OUT of this slice (deferred to follow-up Localization slices
and a later Orchestration cycle):

- The CLI verbs ``novetest localization <run_id>`` /
  ``novetest localization latest`` — Orchestration territory, projected
  onto the JSON envelope in a future cycle (mirrors the Regression
  engine → Regression CLI cadence).
- ``sbfl_aggregate`` mode (FLUCCS-style regression-aware reweighting
  for coverage with ``mapping_granularity != "per-test"``).
- ``failure_proximity`` mode (no-coverage fallback ranking by stack
  frames + regression-modified files).
- Non-Python symbol resolvers (JS/TS, Java/Kotlin, Go, Rust, C#) —
  Python ``ast``-based resolver ships today; other ecosystems fall
  back to file-level ``CodeLocation(kind="file")``.

The wire shape for ``localization_findings.json`` is pinned by
``agent-comms/decisions/2026-05-28-localization-finding-shape.md``;
the engine surface here is complete.
"""

from novetest.localization.derive import (
    DEFAULT_FORMULA,
    DEFAULT_TOP_N,
    derive_latest_localization,
    derive_localization_findings,
    resolve_latest_analyzable_run,
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
    "derive_latest_localization",
    "derive_localization_findings",
    "get_localization_findings",
    "resolve_latest_analyzable_run",
]
