from __future__ import annotations

import io
import json

from novetest.cli.output import (
    SCHEMA,
    Envelope,
    EnvelopeError,
    EnvelopeWarning,
    OutputMode,
    emit_envelope,
    not_implemented_envelope,
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


def test_not_implemented_envelope_shape() -> None:
    env = not_implemented_envelope("memory.list")
    assert env.ok is False
    assert env.command == "memory.list"
    assert env.errors[0].code == "not-implemented"
    assert "memory.list" in env.errors[0].message
