"""``match_flaky_suspected`` against the tuple-shaped ``replay_results``.

The 2026-06-25 ``--reruns`` brief §3 renamed ``FactBundle.replay_result``
(single ``ReplayResult | None``) to ``replay_results: tuple[ReplayResult,
...]`` and made the matcher iterate — one ``CategoryHit`` per result
classified ``inconsistent``, in tuple order. Today the integrated workflow
performs at most one whole-run Replay Attempt per invocation (the Replay
engine has no per-test scoping), so real bundles carry 0 or 1 elements;
the multi-element cases below pin the forward-compatible list contract
the brief mandates.

Also pins the two consumers that ride on the tuple shape:

- ``match_all_green`` is suppressed by ANY inconsistent result in the tuple.
- ``cite_recommendation_evidence`` cites the Replay Result a hit was
  emitted from (matched on the payload's ``(run_reference, test_id)``).
"""

from __future__ import annotations

from novetest.models import RunRecord
from novetest.models.run_reference import RunReference
from novetest.orchestration.recommendation import (
    CATEGORY_ALL_GREEN,
    CATEGORY_FLAKY_SUSPECTED,
    FactBundle,
    ReplayResult,
    StageEligibility,
)
from novetest.orchestration.recommendation.categories import (
    match_all_green,
    match_flaky_suspected,
)
from novetest.orchestration.recommendation.citations import (
    KIND_REPLAY_RESULT,
    cite_recommendation_evidence,
)


# ---------------------------------------------------------------------------
# Fixture helpers (self-contained; mirrors test_categories.py's shapes)
# ---------------------------------------------------------------------------


_REF = RunReference(run_id="01FLAKYRUN00000000000000A", created_at=1000)


def _record(*, failed: int = 1, passed: int = 0) -> RunRecord:
    return RunRecord(
        run_reference=_REF,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="failed" if failed else "passed",
        started_at=1000,
        completed_at=1001,
        summary_counts={
            "passed": passed,
            "failed": failed,
            "total": passed + failed,
        },
    )


def _eligibility(replay: str = "available") -> StageEligibility:
    return StageEligibility(
        coverage="unavailable",
        regression="unavailable",
        localization="unavailable",
        replay=replay,
        per_stage_reasons={
            "coverage": "missing-derived-facts",
            "regression": "no-comparable-baseline",
            "localization": "no-coverage",
            "replay": None if replay == "available" else "replay_not_run",
        },
    )


def _replay(
    *,
    classification: str,
    test_id: str | None,
    reruns_total: int = 5,
    reruns_failed: int = 2,
) -> ReplayResult:
    return ReplayResult(
        run_reference=_REF,
        classification=classification,
        reruns_total=reruns_total,
        reruns_failed=reruns_failed if classification == "inconsistent" else 0,
        test_id=test_id,
    )


def _bundle(
    replay_results: tuple[ReplayResult, ...],
    *,
    failed: int = 1,
    passed: int = 0,
) -> FactBundle:
    record = _record(failed=failed, passed=passed)
    return FactBundle(
        run_reference=_REF,
        run_record=record,
        stage_eligibility=_eligibility(
            "available" if replay_results else "not_run"
        ),
        coverage_facts=None,
        regression_facts=None,
        localization_findings=None,
        replay_results=replay_results,
    )


# ---------------------------------------------------------------------------
# match_flaky_suspected over the tuple
# ---------------------------------------------------------------------------


class TestMatchFlakySuspectedTuple:
    def test_empty_tuple_yields_no_hits(self) -> None:
        assert match_flaky_suspected(_bundle(())) == []

    def test_single_reproducible_yields_no_hits(self) -> None:
        bundle = _bundle(
            (_replay(classification="reproducible", test_id=None),)
        )
        assert match_flaky_suspected(bundle) == []

    def test_single_unable_to_replay_yields_no_hits(self) -> None:
        bundle = _bundle(
            (
                _replay(
                    classification="unable_to_replay",
                    test_id=None,
                    reruns_total=0,
                ),
            )
        )
        assert match_flaky_suspected(bundle) == []

    def test_single_inconsistent_yields_one_hit_with_payload(self) -> None:
        bundle = _bundle(
            (
                _replay(
                    classification="inconsistent",
                    test_id="tests/test_a.py::test_flaky",
                ),
            )
        )
        hits = match_flaky_suspected(bundle)
        assert len(hits) == 1
        h = hits[0]
        assert h.category == CATEGORY_FLAKY_SUSPECTED
        assert h.primary_slot == "tests/test_a.py::test_flaky"
        assert h.payload == {
            "test_id": "tests/test_a.py::test_flaky",
            "reruns_total": 5,
            "reruns_failed": 2,
            "run_reference": _REF.run_id,
        }

    def test_inconsistent_without_focal_test_uses_empty_test_id(self) -> None:
        # ``ReplayResult.test_id`` is None when the divergence is spread
        # across multiple tests; the hit degrades to the empty-string
        # primary_slot exactly as the pre-rename matcher did.
        bundle = _bundle(
            (_replay(classification="inconsistent", test_id=None),)
        )
        hits = match_flaky_suspected(bundle)
        assert len(hits) == 1
        assert hits[0].primary_slot == ""
        assert hits[0].payload["test_id"] == ""

    def test_multi_result_emits_one_hit_per_inconsistent_in_order(self) -> None:
        # Brief §4 — 2 inconsistent + 1 reproducible → exactly 2 hits, in
        # deterministic (tuple) order.
        rr_a = _replay(
            classification="inconsistent", test_id="tests/test_a.py::test_one"
        )
        rr_ok = _replay(classification="reproducible", test_id=None)
        rr_b = _replay(
            classification="inconsistent", test_id="tests/test_b.py::test_two"
        )
        bundle = _bundle((rr_a, rr_ok, rr_b))
        hits = match_flaky_suspected(bundle)
        assert [h.category for h in hits] == [CATEGORY_FLAKY_SUSPECTED] * 2
        assert [h.primary_slot for h in hits] == [
            "tests/test_a.py::test_one",
            "tests/test_b.py::test_two",
        ]

    def test_deterministic_same_bundle_same_hits(self) -> None:
        bundle = _bundle(
            (
                _replay(
                    classification="inconsistent",
                    test_id="tests/test_a.py::test_one",
                ),
                _replay(
                    classification="inconsistent",
                    test_id="tests/test_b.py::test_two",
                ),
            )
        )
        assert match_flaky_suspected(bundle) == match_flaky_suspected(bundle)


# ---------------------------------------------------------------------------
# all_green suppression rides the tuple
# ---------------------------------------------------------------------------


class TestAllGreenSuppression:
    def test_all_green_suppressed_by_any_inconsistent_result(self) -> None:
        bundle = _bundle(
            (
                _replay(classification="reproducible", test_id=None),
                _replay(
                    classification="inconsistent",
                    test_id="tests/test_a.py::test_flaky",
                ),
            ),
            failed=0,
            passed=1,
        )
        assert match_all_green(bundle) == []

    def test_all_green_fires_when_all_results_reproducible(self) -> None:
        bundle = _bundle(
            (_replay(classification="reproducible", test_id=None),),
            failed=0,
            passed=1,
        )
        hits = match_all_green(bundle)
        assert len(hits) == 1
        assert hits[0].category == CATEGORY_ALL_GREEN


# ---------------------------------------------------------------------------
# Citations reference the hit's own Replay Result
# ---------------------------------------------------------------------------


class TestFlakyCitationsPerHit:
    def test_each_hit_cites_its_own_replay_result(self) -> None:
        rr_a = _replay(
            classification="inconsistent", test_id="tests/test_a.py::test_one"
        )
        rr_b = _replay(
            classification="inconsistent", test_id="tests/test_b.py::test_two"
        )
        bundle = _bundle((rr_a, rr_b))
        hits = match_flaky_suspected(bundle)
        assert len(hits) == 2
        for hit, source in zip(hits, (rr_a, rr_b)):
            cites = cite_recommendation_evidence(hit, bundle)
            replay_cites = [c for c in cites if c["kind"] == KIND_REPLAY_RESULT]
            assert len(replay_cites) == 1
            assert replay_cites[0]["selector"]["test_id"] == source.test_id
            assert (
                replay_cites[0]["selector"]["classification"]
                == source.classification
            )
