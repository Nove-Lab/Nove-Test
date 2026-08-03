"""Thin handler for the ``novetest test [target]`` verb.

Owns the v1 envelope projection for the integrated workflow's
``TestOutcome``. Pure function — no subprocess, no exit, no globals.
``cli/app.py`` invokes ``build_test_envelope`` after the orchestration
layer's ``test_target_in_store`` returns, then applies ``emit_envelope``
+ ``sys.exit(...)``.

Envelope shape pinned by the Phase 6 entry brief §5:

.. code-block:: json

    {
      "schema": "novetest/v1",
      "command": "test",
      "ok": true,
      "data": {
        "run_reference": { ... },
        "stage_eligibility": { ... },
        "recommendation_schema_version": 1,
        "recommendations": [ ... ]
      },
      "errors": [],
      "warnings": []
    }

Exit code mapping: the shared ``cli/output.py::run_status_to_ok_exit``
helper — the SAME single mapping ``run_cmd`` uses (W1/S8, ORC-04):

- Run Record status ``"passed"``  → ``EXIT_OK`` (0)
- Run Record status ``"failed"``  → ``EXIT_USER_TESTS_FAILED`` (3)
- Run Record status ``"errored"`` → ``EXIT_USER_TESTS_FAILED`` (3)

``ok`` is ``True`` whenever the transport itself succeeded; the user's
tests failing OR erroring (e.g. a pytest collection error) is **data**,
not a transport error (same convention ``novetest run`` follows since
Phase 1).
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from cyclopts import Parameter

from novetest.cli import _shared
from novetest.cli._shared import (
    _emit_and_exit,
    _require_store,
    _store_corrupt_envelope,
    _validate_engine_flag,
)
from novetest.cli.output import (
    EXIT_STORAGE,
    EXIT_USAGE,
    Envelope,
    EnvelopeError,
    EnvelopeWarning,
    run_status_to_ok_exit,
)
from novetest.memory import ProjectStoreCorruptError
from novetest.orchestration.anchor_resolution import EngineAmbiguousError
from novetest.orchestration.recommendation import RECOMMENDATION_SCHEMA_VERSION
from novetest.orchestration.recommendation.fact_bundle import (
    record_suite_did_not_execute,
    record_total_count,
)
from novetest.orchestration.workflows import test_target_in_store
from novetest.orchestration.workflows.test import TestOutcome
from novetest.run import RunEngineError


# Envelope warning emitted when the run's own status says the suite never
# executed and it produced zero test outcomes (delivery-phasing row 45).
#
# Deliberately NOT the Run engine's ``zero-tests-collected`` code, which
# covers a materially different run: one that executed, exited clean
# (``status: "passed"``) and simply had nothing to run. Routing both through
# one code would make the two indistinguishable to a consumer switching on
# ``warnings[].code`` — which is the only wire surface that separates
# "ran, found nothing" from "never ran".
WARNING_SUITE_DID_NOT_EXECUTE = "suite-did-not-execute"


def build_test_envelope(outcome: TestOutcome) -> tuple[Envelope, int]:
    """Project a ``TestOutcome`` onto the brief §5 envelope shape.

    Pure function — same input, byte-identical output. The exit code is
    keyed off the Run Record's normalized ``status``, NOT off the
    recommendation set (an ``all_green`` envelope still exits 0 even
    when downstream stages were unavailable, because the user's tests
    actually passed).

    Adapter-emitted warnings on ``TestOutcome.warnings`` are projected
    onto ``envelope.warnings[]`` via a field-by-field
    ``AdapterWarning → EnvelopeWarning`` copy. The two dataclasses share
    the ``code`` / ``message`` / ``details`` shape per decision
    2026-06-06 criterion #3. Empty input (the common case for runs
    without adapter warnings) returns an empty tuple unchanged.
    """

    data: dict[str, Any] = {
        "run_reference": outcome.memory_entry.run_record.run_reference.to_dict(),
        "stage_eligibility": outcome.stage_eligibility.to_dict(),
        "recommendation_schema_version": RECOMMENDATION_SCHEMA_VERSION,
        "recommendations": [r.to_dict() for r in outcome.recommendations],
    }
    # Single shared status→(ok, exit) mapping — see run_status_to_ok_exit
    # (W1/S8, ORC-04): failed AND errored are user results at exit 3.
    ok, exit_code = run_status_to_ok_exit(outcome.run_record_status)
    envelope_warnings: tuple[EnvelopeWarning, ...] = tuple(
        EnvelopeWarning(code=w.code, message=w.message, details=dict(w.details))
        for w in outcome.warnings
    ) + _suite_execution_warnings(outcome)
    return (
        Envelope(
            command="test",
            ok=ok,
            data=data,
            warnings=envelope_warnings,
        ),
        exit_code,
    )


def _suite_execution_warnings(outcome: TestOutcome) -> tuple[EnvelopeWarning, ...]:
    """Warn when the run never became a suite (row 45), else emit nothing.

    Pure projection — the *predicate* is orchestration's
    (``record_suite_did_not_execute``), this function only renders it onto
    the envelope's warning channel. The recommendation set answers "what
    should I do" (``unavailable_analysis``: which stages could not run);
    this warning answers "why is there nothing here" (the suite never
    executed), which no frozen ``unavailable_analysis`` slot can carry.
    """

    record = outcome.memory_entry.run_record
    if not record_suite_did_not_execute(record):
        return ()
    return (
        EnvelopeWarning(
            code=WARNING_SUITE_DID_NOT_EXECUTE,
            message=(
                f"The test suite did not execute: {record.engine_name} reported "
                f"status {record.status!r} with 0 collected tests, so no test "
                "outcomes were produced. A collection-time error (a syntax "
                "error or a failing module-scope import in a test file) is the "
                "usual cause; read the native engine output under "
                "data.run_reference's artifacts. Nothing about this run's "
                "correctness has been established."
            ),
            details={
                "run_status": record.status,
                "collected_tests": record_total_count(record),
                "engine_name": record.engine_name,
                "ecosystem": record.ecosystem,
            },
        ),
    )


def test_cmd(
    target: str = "",
    *,
    reruns: Annotated[int, Parameter(name=["--reruns"])] = 0,
    engine: Annotated[str | None, Parameter(name=["--engine"])] = None,
) -> None:
    """Execute the integrated `novetest test [target]` workflow.

    Chains Run → Memory → Coverage → Regression → Localization →
    Recommendation synthesis. Stage failures (no baseline, no coverage,
    etc.) are surfaced via the ``data.stage_eligibility`` block — the
    workflow does NOT abort on a single-engine outage (brief §5 — Error
    policy). Run execution (step 2) is fatal; the handler maps the same
    exception surface ``run_cmd`` does (``EngineNotReadyError`` +
    ``AdapterInvocationError``) and re-uses the same envelope shape.

    ``--reruns N`` (default 0 = off; decision
    ``2026-06-25-test-reruns-flag-and-replay-integration``) opts into the
    Replay sub-workflow: when the run has failed tests, one whole-run
    Replay Attempt executes with ``reruns=N`` and its result feeds the
    synthesizer — an ``inconsistent`` classification makes the
    ``flaky_suspected`` category reachable, and
    ``data.stage_eligibility.replay`` transitions ``"not_run"`` →
    ``"available"``. ``N=1`` is the cheapest opt-in; ``5`` is the
    recommended floor for flake detection. Negative values are rejected
    with ``invalid-flag`` (exit 2), mirroring the ``--formula`` pattern.

    Recommendations are synthesized in-memory from the
    ``FactBundle`` — never persisted (Open Q #9 / brief §2). Re-deriving
    against the same evidence yields a byte-identical recommendation
    list (determinism contract, design doc §4).

    The ``data.run_reference`` / ``data.stage_eligibility`` /
    ``data.recommendation_schema_version`` / ``data.recommendations``
    fields are the wire surface AI agents pin against (brief §5).

    ``--engine <name>`` executes a one-off override of the store's pinned
    engine WITHOUT re-pinning (decision 2026-07-03-engine-selection-policy
    D3); invalid names fail flag validation (``invalid-flag``, exit 2).
    """

    store = _require_store("test")
    if reruns < 0:
        _emit_and_exit(
            Envelope(
                command="test",
                ok=False,
                errors=(
                    EnvelopeError(
                        code="invalid-flag",
                        message=(
                            f"Invalid --reruns={reruns!r}; "
                            "expected a non-negative integer"
                        ),
                    ),
                ),
            ),
            EXIT_USAGE,
        )
    engine_pair = _validate_engine_flag("test", engine)
    try:
        outcome = asyncio.run(
            test_target_in_store(target, store, reruns=reruns, engine=engine_pair)
        )
    except (EngineAmbiguousError, RunEngineError) as exc:
        # ORC-02/ORC-21: same shared mapping as run_cmd — the two verbs cannot
        # drift because they thread their own ``command`` through one helper.
        # Post-S19, ``EngineAmbiguous`` reaches here as the primary legacy +
        # ambiguous refusal (see run_cmd's note), not a TOCTOU race.
        _emit_and_exit(*_shared._map_execution_exception("test", exc))
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (a stage's targeted read / the post-stage
        # refresh found a record corrupt — TOCTOU): storage failure, exit 5.
        _emit_and_exit(_store_corrupt_envelope("test", str(exc)), EXIT_STORAGE)

    envelope, exit_code = build_test_envelope(outcome)
    _emit_and_exit(envelope, exit_code)


__all__ = ["WARNING_SUITE_DID_NOT_EXECUTE", "build_test_envelope", "test_cmd"]
