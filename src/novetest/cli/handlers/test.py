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

from typing import Any

from novetest.cli.output import (
    Envelope,
    EnvelopeWarning,
    run_status_to_ok_exit,
)
from novetest.orchestration.recommendation import RECOMMENDATION_SCHEMA_VERSION
from novetest.orchestration.workflows.test import TestOutcome


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
    )
    return (
        Envelope(
            command="test",
            ok=ok,
            data=data,
            warnings=envelope_warnings,
        ),
        exit_code,
    )


__all__ = ["build_test_envelope"]
