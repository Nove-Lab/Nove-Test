"""End-to-end activation of the ``flaky_suspected`` recommendation category.

Before this slice the ``flaky_suspected`` trigger
(``categories.py::match_flaky_suspected``) was only exercised against a mock
``ReplayResult`` (``tests/unit/orchestration/recommendation/test_categories.py``).
This test proves it fires for real: a genuine ``ReplayResult`` produced by the
Replay engine (classification ``inconsistent``) is placed in a ``FactBundle``
and synthesized, and the resulting recommendation's ``replay_result`` citation
round-trips back to ``get_replay_result`` byte-identically (NFR-ORCH-002).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from novetest.memory import retrieve_run_evidence
from novetest.models.replay_result import ReplayResult
from novetest.orchestration.recommendation import (
    CATEGORY_FLAKY_SUSPECTED,
    StageEligibility,
    build_fact_bundle,
    synthesize_recommendation,
)
from novetest.orchestration.workflows.init import initialize_project_workspace
from novetest.orchestration.workflows.run import run_target_in_store
from novetest.replay import get_replay_result, replay_run


_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "projects"


def _materialize(name: str, dest: Path) -> Path:
    target = dest / name
    shutil.copytree(
        _FIXTURE_ROOT / name,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".novetest"),
    )
    return target


async def test_flaky_suspected_fires_when_replay_result_inconsistent(
    tmp_path: Path,
) -> None:
    """A real ``inconsistent`` ReplayResult drives a ``flaky_suspected`` rec.

    Pipeline: ``flaky-python`` → ``novetest run`` → ``replay_run`` → build a
    ``FactBundle`` carrying the real ``ReplayResult`` → ``synthesize`` →
    assert ``flaky_suspected`` present, its citation carries
    ``kind="replay_result"``, and the citation resolves via
    ``get_replay_result`` to the same ``ReplayResult`` byte-identically.
    """

    workspace = _materialize("flaky-python", tmp_path)
    init = await initialize_project_workspace(workspace)
    outcome = await run_target_in_store(
        "tests/", init.store, timeout=120.0, collect_coverage=True
    )
    original_ref = outcome.memory_entry.run_record.run_reference

    result = await replay_run(init.store, original_ref, reruns=5)
    assert isinstance(result, ReplayResult)
    assert result.classification == "inconsistent"

    # Build a FactBundle carrying the real ReplayResult (mirrors how the
    # integrated ``novetest test --reruns N`` workflow passes it through
    # since the 2026-06-25 integration cycle — tuple-shaped slot).
    original_record = retrieve_run_evidence(init.store, original_ref).run_record
    eligibility = StageEligibility(
        coverage="available",
        regression="not_applicable",
        localization="not_applicable",
        replay="available",
        per_stage_reasons={},
    )
    bundle = build_fact_bundle(
        run_record=original_record,
        stage_eligibility=eligibility,
        coverage_facts=None,
        regression_facts=None,
        localization_findings=None,
        replay_results=(result,),
    )

    recommendations = synthesize_recommendation(bundle)
    flaky = next(
        (r for r in recommendations if r.category == CATEGORY_FLAKY_SUSPECTED),
        None,
    )
    assert flaky is not None, (
        f"Expected flaky_suspected; got {[r.category for r in recommendations]}"
    )

    # REQ-ORCH-005: the recommendation carries a replay_result citation.
    replay_citations = [
        c for c in flaky.evidence_citations if c["kind"] == "replay_result"
    ]
    assert len(replay_citations) == 1
    citation = replay_citations[0]

    # NFR-ORCH-002 round-trip: the citation resolves back to the SAME result.
    resolved = get_replay_result(init.store, original_ref)
    assert isinstance(resolved, ReplayResult)
    assert resolved.to_dict() == result.to_dict()

    selector = citation["selector"]
    assert selector["classification"] == resolved.classification
    assert selector["test_id"] == resolved.test_id
