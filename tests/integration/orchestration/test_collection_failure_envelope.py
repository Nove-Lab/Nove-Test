"""Wire tests: a suite that never executed is never reported green (row 45).

Delivery-phasing board row 45 — the only registered defect where novetest
asserted a *positive falsehood*. A pytest suite with a collection-time
error collects zero tests and exits non-zero; novetest correctly persisted
``status: "errored"`` and correctly exited 3, but the synthesizer still
emitted ``recommendations[0].category == "all_green"`` with the summary
"All tests green; no action recommended" and an empty ``warnings`` array.
The only signal that anything was wrong was the exit code, and the
structured payload — the thing the product exists to hand an agent —
actively contradicted it.

Everything here runs through the REAL ``novetest`` subprocess against
``tests/fixtures/projects/pytest-collection-error``. Nothing is
monkeypatched: the matcher-level pins live in
``tests/unit/orchestration/recommendation/test_categories.py::TestCollectionFailureRow45``,
and these assertions exist to prove the fix survives the whole chain out
to the bytes on stdout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def collection_failure_envelope(
    collection_error_workspace: Path, run_cli_in
) -> dict[str, Any]:
    """Run ``novetest test`` against the unparsable fixture, once."""

    init_result = run_cli_in(collection_error_workspace, ["init"])
    assert init_result.returncode == 0, init_result.stderr
    result = run_cli_in(collection_error_workspace, ["test", "tests/"])
    # Exit-code contract is UNCHANGED by this fix and re-pinned here so a
    # regression in either direction is loud: ``run_status_to_ok_exit``
    # already mapped "errored" to (True, EXIT_USER_TESTS_FAILED), and that
    # mapping was correct before row 45 and is untouched by it.
    assert result.returncode == 3, (result.returncode, result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


class TestCollectionFailureEnvelope:
    def test_envelope_is_a_transport_success(
        self, collection_failure_envelope: dict[str, Any]
    ) -> None:
        """A user's suite failing to parse is DATA, not a tool failure."""

        assert collection_failure_envelope["schema"] == "novetest/v1"
        assert collection_failure_envelope["ok"] is True
        assert collection_failure_envelope["errors"] == []

    def test_top_recommendation_is_not_all_green(
        self, collection_failure_envelope: dict[str, Any]
    ) -> None:
        recs = collection_failure_envelope["data"]["recommendations"]
        assert recs, "a collection failure must still produce a recommendation"
        assert recs[0]["category"] != "all_green"
        assert recs[0]["category"] == "unavailable_analysis"

    def test_no_recommendation_anywhere_claims_green(
        self, collection_failure_envelope: dict[str, Any]
    ) -> None:
        """Stronger than ``recommendations[0]``: sweep the whole list.

        Position 0 alone would be satisfied by an envelope that merely
        re-ordered ``all_green`` down the list.
        """

        recs = collection_failure_envelope["data"]["recommendations"]
        assert [r for r in recs if r["category"] == "all_green"] == []
        for rec in recs:
            assert "green" not in rec["summary"].lower(), rec["summary"]

    def test_the_recommendation_carries_evidence(
        self, collection_failure_envelope: dict[str, Any]
    ) -> None:
        """NFR-ORCH-002 holds on this path too."""

        recs = collection_failure_envelope["data"]["recommendations"]
        assert recs[0]["evidence_citations"], recs[0]

    def test_a_warning_names_the_collection_failure(
        self, collection_failure_envelope: dict[str, Any]
    ) -> None:
        """The "why", which no frozen ``unavailable_analysis`` slot carries.

        ``unavailable_analysis`` explains why each *stage* could not run
        (localization: ``no-failed-tests``) — which on its own still reads
        as "nothing failed, so nothing to analyse". The warning is what
        says the suite itself never executed.
        """

        warnings = collection_failure_envelope["warnings"]
        matching = [w for w in warnings if w["code"] == "suite-did-not-execute"]
        assert len(matching) == 1, warnings
        warning = matching[0]
        assert warning["details"]["run_status"] == "errored"
        assert warning["details"]["executed_tests"] == 0
        assert "collected_tests" not in warning["details"]
        assert "did not execute" in warning["message"]

    def test_warning_code_is_distinct_from_zero_tests_collected(
        self, collection_failure_envelope: dict[str, Any]
    ) -> None:
        """The two empty-run shapes must stay machine-distinguishable.

        ``zero-tests-collected`` is the Run engine's warning for a run
        that executed, exited CLEAN and found no tests (go / junit /
        xunit). This run never executed. A consumer switching on
        ``warnings[].code`` has to be able to tell them apart, so routing
        both through one code is forbidden.
        """

        codes = [w["code"] for w in collection_failure_envelope["warnings"]]
        assert "zero-tests-collected" not in codes
        assert "suite-did-not-execute" in codes

    def test_stage_eligibility_reports_the_outage(
        self, collection_failure_envelope: dict[str, Any]
    ) -> None:
        eligibility = collection_failure_envelope["data"]["stage_eligibility"]
        assert eligibility["localization"] == "unavailable"

    def test_still_refuses_green_once_a_regression_baseline_exists(
        self, collection_error_workspace: Path, run_cli_in
    ) -> None:
        """The fix must not be leaning on the stages happening to be out.

        Measured while writing these tests: a SECOND consecutive run finds
        the first one as a baseline, so ``stage_eligibility.regression``
        flips ``unavailable`` → ``available`` and
        ``unavailable_analysis``'s ``unavailable_stages`` slot shrinks from
        three entries to two. That is a genuinely different fact bundle,
        and it is exactly the sort of drift that would quietly re-open row
        45 if the refusal depended on how many stages were down. It does
        not: the refusal is keyed on ``run_record.status`` alone.
        """

        assert run_cli_in(collection_error_workspace, ["init"]).returncode == 0
        first = run_cli_in(collection_error_workspace, ["test", "tests/"])
        second = run_cli_in(collection_error_workspace, ["test", "tests/"])
        assert first.returncode == second.returncode == 3

        first_payload = json.loads(first.stdout)
        second_payload = json.loads(second.stdout)
        # The precondition this test exists for — if the baseline stops
        # resolving, the assertions below stop being adversarial.
        assert first_payload["data"]["stage_eligibility"]["regression"] == "unavailable"
        assert second_payload["data"]["stage_eligibility"]["regression"] == "available"

        for payload in (first_payload, second_payload):
            recs = payload["data"]["recommendations"]
            assert [r for r in recs if r["category"] == "all_green"] == []
            codes = [w["code"] for w in payload["warnings"]]
            assert "suite-did-not-execute" in codes

        # The warning is the one signal that does NOT depend on stage
        # eligibility at all, so it is identical across both runs.
        def _warning(payload: dict[str, Any]) -> dict[str, Any]:
            return next(
                w for w in payload["warnings"] if w["code"] == "suite-did-not-execute"
            )

        assert _warning(first_payload) == _warning(second_payload)

    def test_determinism_holds_on_this_shape(
        self, collection_error_workspace: Path, run_cli_in
    ) -> None:
        """Same fact bundle in → byte-identical recommendations out.

        Re-derives against the ALREADY-SEEDED store (cache-only, no second
        execution) — the same strategy ``test_test_workflow.py`` uses, and
        the only way to hold the bundle genuinely constant here: simply
        invoking the CLI twice does not, because run #2 gains a regression
        baseline (see the test above). The determinism contract (synthesis
        design doc §4) is what makes this category set safe to pin, and a
        collection failure is a degenerate input worth re-proving it on.
        """

        from novetest.memory import locate_project_store
        from novetest.orchestration.workflows import build_test_outcome_from_run_id

        assert run_cli_in(collection_error_workspace, ["init"]).returncode == 0
        result = run_cli_in(collection_error_workspace, ["test", "tests/"])
        assert result.returncode == 3
        run_id = json.loads(result.stdout)["data"]["run_reference"]["run_id"]

        store = locate_project_store(collection_error_workspace)
        assert store is not None
        first = build_test_outcome_from_run_id(store, run_id)
        second = build_test_outcome_from_run_id(store, run_id)
        assert first is not None and second is not None
        assert [r.to_dict() for r in first.recommendations] == [
            r.to_dict() for r in second.recommendations
        ]
        assert [r.category for r in first.recommendations] == ["unavailable_analysis"]
