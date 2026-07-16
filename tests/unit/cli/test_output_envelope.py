from __future__ import annotations

import io
import json

from novetest import models
from novetest.cli import output as output_module
from novetest.cli.output import (
    EXIT_USER_TESTS_FAILED,
    SCHEMA,
    Envelope,
    EnvelopeError,
    EnvelopeWarning,
    OutputMode,
    emit_envelope,
    run_status_to_ok_exit,
)


def test_envelope_to_dict_has_contract_shape() -> None:
    env = Envelope(command="memory.show", ok=True, data={"runId": "abc"})
    payload = env.to_dict()
    assert payload["schema"] == SCHEMA
    assert payload["command"] == "memory.show"
    assert payload["ok"] is True
    assert payload["data"] == {"runId": "abc"}
    assert payload["errors"] == []
    assert payload["warnings"] == []


def test_envelope_errors_and_warnings_serialize() -> None:
    env = Envelope(
        command="run",
        ok=False,
        errors=(EnvelopeError(code="engine-missing", message="pytest not found"),),
        warnings=(EnvelopeWarning(code="stale-readiness", message="cache miss"),),
    )
    payload = env.to_dict()
    assert payload["errors"][0]["code"] == "engine-missing"
    assert payload["errors"][0]["message"] == "pytest not found"
    assert payload["errors"][0]["details"] == {}
    assert payload["warnings"][0]["code"] == "stale-readiness"


def test_emit_envelope_json_is_pretty_and_parses() -> None:
    buf = io.StringIO()
    emit_envelope(Envelope(command="x", ok=True, data={"a": 1}), OutputMode.JSON, stream=buf)
    out = buf.getvalue()
    assert out.count("\n") > 1
    parsed = json.loads(out)
    assert parsed["command"] == "x"


def test_emit_envelope_ndjson_is_single_line() -> None:
    buf = io.StringIO()
    emit_envelope(Envelope(command="x", ok=True), OutputMode.NDJSON, stream=buf)
    out = buf.getvalue()
    assert out.count("\n") == 1
    assert out.endswith("\n")
    json.loads(out.strip())


def test_run_status_mapping_consumes_fail_like_ssot() -> None:
    """``run_status_to_ok_exit`` reads the ``models`` fail-like SSoT rather than a
    re-declared local literal (S25 discipline; W2/S28 fold of the last CLI-side
    ``("failed", "errored")`` tuple). Mirrors the per-consumer identity pins in
    ``tests/unit/models/test_fail_like_outcomes_ssot.py`` — a contributor who
    re-forks the literal here (dropping the SSoT import) trips this pin.
    """
    assert output_module.FAIL_LIKE_OUTCOMES is models.FAIL_LIKE_OUTCOMES
    # Behavior parity: every fail-like outcome maps to (ok=True, exit 3), the
    # byte-identical result of the pre-fold literal branch.
    for status in models.FAIL_LIKE_OUTCOMES:
        assert run_status_to_ok_exit(status) == (True, EXIT_USER_TESTS_FAILED)
