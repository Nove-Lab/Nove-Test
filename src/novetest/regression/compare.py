"""Run-to-run behavior comparison.

Workflow (from ``design/workflows/regression.md``):

    compare_runs(run_reference_1, run_reference_2)
        -> memory/retrieve_run_evidence
        -> coverage/compare_coverage_facts

Public entry point ``compare_runs`` resolves both Memory entries, enforces
the cross-run invariants (tombstones / engine names / target expression),
then either reads cached facts via ``get_regression_facts`` or derives
fresh facts via ``derive_regression_facts``. Argument order is
``(baseline, target)`` end-to-end per decision §2.

Argument-order recap (decision §1):
- arg1 = baseline (older / reference)
- arg2 = target  (newer / candidate)

So ``compare_runs(rA, rB)`` and ``compare_runs(rB, rA)`` are distinct
operations with distinct on-disk pair directories — transition direction
is order-significant.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from novetest.coverage.compare import CoverageDelta, compare_coverage_facts
from novetest.coverage.results import CoverageUnavailable
from novetest.memory.project_store import ProjectStore
from novetest.memory.store import RunEvidenceNotFoundError, retrieve_run_evidence
from novetest.models.memory_entry import MemoryEntry
from novetest.models.regression_fact_set import (
    OutputDiffRecord,
    RegressionFactSet,
    RegressionSummary,
    TestTransition,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.regression.persistence import write_regression_facts
from novetest.regression.results import (
    REASON_ENGINE_MISMATCH,
    REASON_MISSING_DERIVED_FACTS,
    REASON_RUN_NOT_FOUND,
    REASON_RUN_TOMBSTONED,
    REASON_TARGET_MISMATCH,
    RegressionUnavailable,
)
from novetest.regression.retrieval import get_regression_facts


# Bucket sets for outcome classification (decision §3 / §5.2). Native
# engines emit raw outcome strings; we map them onto three coarse buckets
# so the 9-category transition taxonomy stays closed.
_PASS_LIKE: frozenset[str] = frozenset({"passed", "xpassed"})
_FAIL_LIKE: frozenset[str] = frozenset({"failed", "errored"})
_SKIP_LIKE: frozenset[str] = frozenset({"skipped", "xfailed"})

# Artifact-path keys Run Team's adapters register for the captured native
# stdout/stderr. Both pytest and jest emit these keys (see
# ``src/novetest/run/adapters/pytest_adapter.py`` and ``jest_adapter.py``).
_STDOUT_ARTIFACT_KEY = "stdout"
_STDERR_ARTIFACT_KEY = "stderr"

# Well-known warning codes (decision §5 / §8).
_WARN_ENGINE_VERSION_DRIFT = "engine-version-drift"
_WARN_TARGET_TYPE_DRIFT = "target-type-drift"
_WARN_UNKNOWN_OUTCOME_PREFIX = "unknown-outcome:"  # full code: "<prefix><engine>:<raw>"


def compare_runs(
    store: ProjectStore,
    baseline_run_reference: RunReference,
    target_run_reference: RunReference,
) -> RegressionFactSet | RegressionUnavailable:
    """Return regression facts comparing ``baseline`` to ``target``.

    Reads from cache when the canonical ``regression_facts.json`` exists
    AND the embedded Coverage payload (if any) is current; otherwise
    derives fresh facts and writes them. Tombstoned baseline OR target
    short-circuits to ``REASON_RUN_TOMBSTONED`` regardless of cache state
    (decision §C.1).
    """
    # 1) Resolve both Memory entries; surface RunEvidenceNotFoundError as
    #    a clean unavailable. The detail field distinguishes which side
    #    failed so the caller can render a useful message.
    baseline_entry = _resolve_entry(store, baseline_run_reference, "baseline")
    if isinstance(baseline_entry, RegressionUnavailable):
        return _with_run_refs(
            baseline_entry, baseline_run_reference, target_run_reference
        )
    target_entry = _resolve_entry(store, target_run_reference, "target")
    if isinstance(target_entry, RegressionUnavailable):
        return _with_run_refs(
            target_entry, baseline_run_reference, target_run_reference
        )

    # 2) Tombstone check (fail-hard per decision §C.1). Both sides
    #    independently checked; ``detail`` distinguishes which side(s)
    #    were tombstoned.
    tombstone_detail = _tombstone_detail(baseline_entry, target_entry)
    if tombstone_detail is not None:
        return RegressionUnavailable(
            reason=REASON_RUN_TOMBSTONED,
            detail=tombstone_detail,
            baseline_run_reference=baseline_entry.run_record.run_reference,
            target_run_reference=target_entry.run_record.run_reference,
        )

    # 3) Cache lookup. ``get_regression_facts`` is a pure file read; on
    #    "missing-derived-facts" we derive. Note: the coverage-schema-stale
    #    sub-case also surfaces as REASON_MISSING_DERIVED_FACTS — same
    #    re-derive path handles it.
    cached = get_regression_facts(
        store, baseline_run_reference, target_run_reference
    )
    if isinstance(cached, RegressionFactSet):
        return cached
    if cached.reason != REASON_MISSING_DERIVED_FACTS:
        # Defensive: no other reason should surface from a pure file read
        # today, but propagate cleanly if a future change adds one.
        return cached

    # 4) Derive (also writes to disk).
    return derive_regression_facts(
        store, baseline_run_reference, target_run_reference
    )


def derive_regression_facts(
    store: ProjectStore,
    baseline_run_reference: RunReference,
    target_run_reference: RunReference,
) -> RegressionFactSet | RegressionUnavailable:
    """Build fresh regression facts for ``(baseline, target)`` and persist them.

    Performs the same Memory + tombstone validation as ``compare_runs``
    (so calling this directly is safe), then validates engine-name and
    target-expression compatibility, computes per-test transitions,
    fingerprints stdout/stderr, optionally embeds the Coverage delta, and
    writes the result to disk.
    """
    baseline_entry = _resolve_entry(store, baseline_run_reference, "baseline")
    if isinstance(baseline_entry, RegressionUnavailable):
        return _with_run_refs(
            baseline_entry, baseline_run_reference, target_run_reference
        )
    target_entry = _resolve_entry(store, target_run_reference, "target")
    if isinstance(target_entry, RegressionUnavailable):
        return _with_run_refs(
            target_entry, baseline_run_reference, target_run_reference
        )

    tombstone_detail = _tombstone_detail(baseline_entry, target_entry)
    if tombstone_detail is not None:
        return RegressionUnavailable(
            reason=REASON_RUN_TOMBSTONED,
            detail=tombstone_detail,
            baseline_run_reference=baseline_entry.run_record.run_reference,
            target_run_reference=target_entry.run_record.run_reference,
        )

    baseline_record = baseline_entry.run_record
    target_record = target_entry.run_record

    # Engine name mismatch = hard unavailable (decision §C.3). Engine
    # *version* drift is permitted with a warning, handled below.
    if baseline_record.engine_name != target_record.engine_name:
        return RegressionUnavailable(
            reason=REASON_ENGINE_MISMATCH,
            detail=(
                f"baseline engine_name={baseline_record.engine_name!r} "
                f"!= target engine_name={target_record.engine_name!r}"
            ),
            baseline_run_reference=baseline_record.run_reference,
            target_run_reference=target_record.run_reference,
        )

    # Target expression mismatch = hard unavailable. Target *type* drift
    # (same expression, different type) is a softer signal — warning.
    if baseline_record.target_expression != target_record.target_expression:
        return RegressionUnavailable(
            reason=REASON_TARGET_MISMATCH,
            detail=(
                f"baseline target_expression="
                f"{baseline_record.target_expression!r} != target "
                f"target_expression={target_record.target_expression!r}"
            ),
            baseline_run_reference=baseline_record.run_reference,
            target_run_reference=target_record.run_reference,
        )

    warnings: list[str] = []
    if _engine_version_drift(baseline_record, target_record):
        warnings.append(_WARN_ENGINE_VERSION_DRIFT)
    if baseline_record.target_type != target_record.target_type:
        warnings.append(_WARN_TARGET_TYPE_DRIFT)

    transitions, summary, unknown_warnings = _build_transitions(
        baseline_record, target_record
    )
    warnings.extend(unknown_warnings)

    output_diff = _build_output_diff(store, baseline_record, target_record)
    coverage_change = _maybe_coverage_change(
        store, baseline_record.run_reference, target_record.run_reference
    )

    fact_set = RegressionFactSet(
        baseline_run_reference=baseline_record.run_reference,
        target_run_reference=target_record.run_reference,
        baseline_engine_name=baseline_record.engine_name,
        target_engine_name=target_record.engine_name,
        baseline_engine_version=baseline_record.engine_version,
        target_engine_version=target_record.engine_version,
        derived_at=int(time.time() * 1000),
        summary=summary,
        test_transitions=transitions,
        output_diff=output_diff,
        coverage_change=coverage_change,
        warnings=tuple(warnings),
    )
    write_regression_facts(store, fact_set)
    return fact_set


# --- Memory resolution -------------------------------------------------------


def _resolve_entry(
    store: ProjectStore, run_reference: RunReference, side: str
) -> MemoryEntry | RegressionUnavailable:
    """Resolve a Memory entry; convert lookup failure into Unavailable."""
    try:
        return retrieve_run_evidence(store, run_reference)
    except RunEvidenceNotFoundError as exc:
        return RegressionUnavailable(
            reason=REASON_RUN_NOT_FOUND,
            detail=f"{side}: {exc}",
        )


def _with_run_refs(
    unavailable: RegressionUnavailable,
    baseline: RunReference,
    target: RunReference,
) -> RegressionUnavailable:
    """Populate ``baseline_run_reference`` / ``target_run_reference`` on a
    RunEvidenceNotFoundError-propagated Unavailable.

    The original ``_resolve_entry`` cannot fill these because at the time
    one side failed to resolve, we still want to surface BOTH refs for the
    caller's audit trail.
    """
    return RegressionUnavailable(
        reason=unavailable.reason,
        detail=unavailable.detail,
        baseline_run_reference=baseline,
        target_run_reference=target,
    )


def _tombstone_detail(
    baseline_entry: MemoryEntry, target_entry: MemoryEntry
) -> str | None:
    """Return the ``detail`` string for a tombstone-case Unavailable.

    Symmetric handling per decision §C.1: either side being tombstoned is
    fail-hard; ``detail`` distinguishes which side(s) for operator clarity.
    """
    baseline_t = baseline_entry.tombstoned_at is not None
    target_t = target_entry.tombstoned_at is not None
    if baseline_t and target_t:
        return "both"
    if baseline_t:
        return "baseline"
    if target_t:
        return "target"
    return None


# --- transition classification ----------------------------------------------


def _bucket_for_outcome(outcome: str) -> str | None:
    """Return ``pass`` / ``fail`` / ``skip`` for known outcomes; ``None`` else.

    The native ``TestResult.outcome`` is intentionally not enum-locked at
    v1 (per ``test_result.py:22-26``), so a downstream engine can emit a
    string we don't yet recognize. ``None`` means "unknown — defensive
    bucketing required at the call site". The closed set of six recognized
    outcomes is pinned by decision §5.2.
    """
    if outcome in _PASS_LIKE:
        return "pass"
    if outcome in _FAIL_LIKE:
        return "fail"
    if outcome in _SKIP_LIKE:
        return "skip"
    return None


def _bucket_defensively(outcome: str) -> str:
    """Fallback classifier for outcome strings outside the known set.

    Cheap substring heuristic — prefer the most semantically alarming
    bucket (fail) so unknowns surface in regression-style reports rather
    than hiding as "still_passing". The accompanying warning code emitted
    at the call site (``unknown-outcome:<engine>:<raw>``) keeps the
    defensive choice auditable for the consumer.
    """
    lowered = outcome.lower()
    if "pass" in lowered:
        return "pass"
    if "skip" in lowered:
        return "skip"
    # "fail", "error", and any unrecognized string default to fail-like —
    # surfaces in regression dashboards instead of silently passing.
    return "fail"


def _classify(baseline_bucket: str, target_bucket: str) -> str:
    """Map a (baseline_bucket, target_bucket) tuple to a TRANSITION_CATEGORIES value.

    Both buckets are ``"pass"`` / ``"fail"`` / ``"skip"``. ``added`` /
    ``removed`` are handled separately (no opposite-side outcome exists).
    """
    if baseline_bucket == "pass" and target_bucket == "fail":
        return "regressed"
    if baseline_bucket == "fail" and target_bucket == "pass":
        return "fixed"
    if baseline_bucket == "fail" and target_bucket == "fail":
        return "still_failing"
    if baseline_bucket == "pass" and target_bucket == "pass":
        return "still_passing"
    if baseline_bucket == "skip" and target_bucket == "skip":
        return "still_skipped"
    if baseline_bucket != "skip" and target_bucket == "skip":
        return "newly_skipped"
    # baseline_bucket == "skip" and target_bucket != "skip"
    return "newly_active"


def _build_transitions(
    baseline_record: RunRecord, target_record: RunRecord
) -> tuple[tuple[TestTransition, ...], RegressionSummary, list[str]]:
    """Compute the per-test transitions, summary, and unknown-outcome warnings.

    Transitions are sorted by ``node_id`` ascending (decision §5 constraint
    #3 — determinism is load-bearing for NFR-REG-001). Unknown outcome
    warnings are deduplicated per ``(engine, raw)`` pair to avoid noisy
    repetition when the same unrecognized string appears across many tests.
    """
    baseline_by_id = {tr.node_id: tr for tr in baseline_record.test_results}
    target_by_id = {tr.node_id: tr for tr in target_record.test_results}
    all_node_ids = sorted(set(baseline_by_id) | set(target_by_id))

    transitions: list[TestTransition] = []
    counts: dict[str, int] = {cat: 0 for cat in (
        "regressed",
        "fixed",
        "still_failing",
        "still_passing",
        "still_skipped",
        "newly_skipped",
        "newly_active",
        "added",
        "removed",
    )}
    seen_unknowns: set[tuple[str, str]] = set()
    unknown_warnings: list[str] = []

    # ``engine_name`` already validated identical at the call site, but use
    # baseline's value defensively for warning code construction.
    engine_name = baseline_record.engine_name

    for node_id in all_node_ids:
        baseline_tr = baseline_by_id.get(node_id)
        target_tr = target_by_id.get(node_id)

        if baseline_tr is None and target_tr is not None:
            category = "added"
        elif target_tr is None and baseline_tr is not None:
            category = "removed"
        else:
            assert baseline_tr is not None and target_tr is not None
            baseline_bucket = _resolve_bucket(
                baseline_tr.outcome, engine_name, seen_unknowns, unknown_warnings
            )
            target_bucket = _resolve_bucket(
                target_tr.outcome, engine_name, seen_unknowns, unknown_warnings
            )
            category = _classify(baseline_bucket, target_bucket)

        counts[category] += 1
        transitions.append(
            TestTransition(
                node_id=node_id,
                category=category,
                baseline_outcome=(
                    None if baseline_tr is None else baseline_tr.outcome
                ),
                target_outcome=(
                    None if target_tr is None else target_tr.outcome
                ),
                baseline_failure_reference=_failure_ref(baseline_tr),
                target_failure_reference=_failure_ref(target_tr),
                baseline_duration_ms=_duration(baseline_tr),
                target_duration_ms=_duration(target_tr),
            )
        )

    in_both = len(set(baseline_by_id) & set(target_by_id))
    summary = RegressionSummary(
        regressed=counts["regressed"],
        fixed=counts["fixed"],
        still_failing=counts["still_failing"],
        still_passing=counts["still_passing"],
        still_skipped=counts["still_skipped"],
        newly_skipped=counts["newly_skipped"],
        newly_active=counts["newly_active"],
        added=counts["added"],
        removed=counts["removed"],
        total_baseline_tests=in_both + counts["removed"],
        total_target_tests=in_both + counts["added"],
    )
    return tuple(transitions), summary, unknown_warnings


def _resolve_bucket(
    outcome: str,
    engine_name: str,
    seen_unknowns: set[tuple[str, str]],
    unknown_warnings: list[str],
) -> str:
    """Return a known bucket, emitting an unknown-outcome warning if defensive.

    Mutates ``seen_unknowns`` and ``unknown_warnings`` in place — keeps
    the dedup state at the comparison's scope rather than threading it
    through more arguments.
    """
    known = _bucket_for_outcome(outcome)
    if known is not None:
        return known
    key = (engine_name, outcome)
    if key not in seen_unknowns:
        seen_unknowns.add(key)
        unknown_warnings.append(
            f"{_WARN_UNKNOWN_OUTCOME_PREFIX}{engine_name}:{outcome}"
        )
    return _bucket_defensively(outcome)


def _failure_ref(tr: TestResult | None) -> str | None:
    return None if tr is None else tr.failure_reference


def _duration(tr: TestResult | None) -> int | None:
    return None if tr is None else tr.duration_ms


# --- output diff -------------------------------------------------------------


def _build_output_diff(
    store: ProjectStore, baseline: RunRecord, target: RunRecord
) -> OutputDiffRecord | None:
    """SHA-256 + path-ref output diff per decision §4 constraint #4.

    Returns ``None`` when neither side has stdout NOR stderr registered in
    ``artifact_paths`` (and confirmable on disk). Any single artifact
    present on either side flips this to a populated record so downstream
    consumers see the partial signal.
    """
    baseline_stdout_rel = baseline.artifact_paths.get(_STDOUT_ARTIFACT_KEY)
    target_stdout_rel = target.artifact_paths.get(_STDOUT_ARTIFACT_KEY)
    baseline_stderr_rel = baseline.artifact_paths.get(_STDERR_ARTIFACT_KEY)
    target_stderr_rel = target.artifact_paths.get(_STDERR_ARTIFACT_KEY)

    baseline_stdout_sha, baseline_stdout_path = _sha_and_path(store, baseline_stdout_rel)
    target_stdout_sha, target_stdout_path = _sha_and_path(store, target_stdout_rel)
    baseline_stderr_sha, baseline_stderr_path = _sha_and_path(store, baseline_stderr_rel)
    target_stderr_sha, target_stderr_path = _sha_and_path(store, target_stderr_rel)

    nothing_to_report = all(
        v is None
        for v in (
            baseline_stdout_sha,
            target_stdout_sha,
            baseline_stderr_sha,
            target_stderr_sha,
            baseline_stdout_path,
            target_stdout_path,
            baseline_stderr_path,
            target_stderr_path,
        )
    )
    if nothing_to_report:
        return None

    return OutputDiffRecord(
        baseline_stdout_sha256=baseline_stdout_sha,
        target_stdout_sha256=target_stdout_sha,
        baseline_stderr_sha256=baseline_stderr_sha,
        target_stderr_sha256=target_stderr_sha,
        stdout_identical=(
            baseline_stdout_sha is not None
            and target_stdout_sha is not None
            and baseline_stdout_sha == target_stdout_sha
        ),
        stderr_identical=(
            baseline_stderr_sha is not None
            and target_stderr_sha is not None
            and baseline_stderr_sha == target_stderr_sha
        ),
        baseline_stdout_path=baseline_stdout_path,
        target_stdout_path=target_stdout_path,
        baseline_stderr_path=baseline_stderr_path,
        target_stderr_path=target_stderr_path,
    )


def _sha_and_path(
    store: ProjectStore, rel_path: str | None
) -> tuple[str | None, str | None]:
    """Read the artifact bytes at ``store.path / rel_path`` and return SHA-256.

    Returns ``(None, None)`` when ``rel_path`` is ``None`` OR the file is
    missing on disk (artifact pruned). The path component of the return
    tuple is the same Project-Store-relative string we got in — never
    absolute — preserving the convention used by ``RunRecord.artifact_paths``.
    """
    if rel_path is None:
        return None, None
    absolute = store.path / rel_path
    if not absolute.is_file():
        return None, None
    digest = hashlib.sha256()
    # Read in chunks to keep peak memory bounded for multi-MB captures.
    with absolute.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest(), rel_path


# --- coverage embed ----------------------------------------------------------


def _maybe_coverage_change(
    store: ProjectStore,
    baseline_run_reference: RunReference,
    target_run_reference: RunReference,
) -> dict[str, Any] | None:
    """Embed ``CoverageDelta.to_dict()`` when both sides have facts; else None.

    A ``CoverageUnavailable`` on either side (either missing native
    payload, missing derived facts, or any other reason Coverage surfaces)
    folds into ``coverage_change = None`` — we don't surface the coverage
    failure reason into Regression's payload. Consumers wanting per-side
    coverage status can call the Coverage engine directly.
    """
    delta = compare_coverage_facts(
        store, baseline_run_reference, target_run_reference
    )
    if isinstance(delta, CoverageUnavailable):
        return None
    assert isinstance(delta, CoverageDelta)
    return delta.to_dict()


# --- engine-version drift ----------------------------------------------------


def _engine_version_drift(baseline: RunRecord, target: RunRecord) -> bool:
    """True iff both versions are known AND they differ.

    Per decision §C.3, missing version on either side does NOT count as
    drift — the engine adapter may simply have not captured it. We only
    flag the *observable* case where both runs reported a version and the
    versions disagree.
    """
    if baseline.engine_version is None or target.engine_version is None:
        return False
    return baseline.engine_version != target.engine_version
