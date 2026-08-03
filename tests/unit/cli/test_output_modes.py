from __future__ import annotations

import io
from typing import Any

import pytest

from novetest.cli.output import (
    InvalidOutputModeError,
    OutputMode,
    emit_envelope,
    fallback_output_mode,
    invalid_output_mode_envelope,
    resolve_output_mode,
)


class _TTYStream(io.StringIO):
    def isatty(self) -> bool:
        return True


class _NonTTYStream(io.StringIO):
    def isatty(self) -> bool:
        return False


def test_explicit_takes_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVETEST_OUTPUT", "json")
    assert resolve_output_mode("ndjson", stream=_TTYStream()) == OutputMode.NDJSON


def test_env_used_when_no_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVETEST_OUTPUT", "ndjson")
    assert resolve_output_mode(None, stream=_TTYStream()) == OutputMode.NDJSON


def test_falls_back_to_text_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOVETEST_OUTPUT", raising=False)
    assert resolve_output_mode(None, stream=_TTYStream()) == OutputMode.TEXT


def test_falls_back_to_json_when_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOVETEST_OUTPUT", raising=False)
    assert resolve_output_mode(None, stream=_NonTTYStream()) == OutputMode.JSON


def test_empty_env_is_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVETEST_OUTPUT", "")
    assert resolve_output_mode(None, stream=_TTYStream()) == OutputMode.TEXT


def test_invalid_explicit_raises() -> None:
    with pytest.raises(ValueError):
        resolve_output_mode("bogus", stream=_NonTTYStream())


# ---------------------------------------------------------------------------
# Row 48 — the refusal carries enough to build an envelope from
# ---------------------------------------------------------------------------


def test_invalid_explicit_raises_the_typed_subclass() -> None:
    """Still a ``ValueError`` (nothing downstream had to change), but typed.

    The bare enum ``ValueError`` carried no machine-readable provenance,
    so ``main`` could not say whether ``--output`` or ``NOVETEST_OUTPUT``
    was at fault.
    """

    with pytest.raises(InvalidOutputModeError) as excinfo:
        resolve_output_mode("bogus", stream=_NonTTYStream())
    assert excinfo.value.value == "bogus"
    assert excinfo.value.source == "--output"
    assert issubclass(InvalidOutputModeError, ValueError)


def test_invalid_env_value_names_the_env_var() -> None:
    with pytest.raises(InvalidOutputModeError) as excinfo:
        resolve_output_mode(None, stream=_NonTTYStream(), env={"NOVETEST_OUTPUT": "bogus"})
    assert excinfo.value.source == "NOVETEST_OUTPUT"


def test_case_variants_are_refused_not_coerced() -> None:
    """``JSON`` must not silently resolve to ``json``.

    Exact matching is the contract; a mode that depends on capitalization
    would be a worse one. This pins the refusal so a future "be lenient"
    change is a deliberate decision rather than a drive-by.
    """

    for value in ("JSON", "Json", " json", "json "):
        with pytest.raises(InvalidOutputModeError):
            resolve_output_mode(value, stream=_NonTTYStream())


def test_fallback_mirrors_the_no_value_default() -> None:
    """The error path's rendering choice is the same isatty rule.

    When the requested mode is what failed to resolve, something still has
    to decide how to render the refusal. Reusing ``fallback_output_mode``
    keeps that deterministic per stream — and keeps non-interactive stdout
    (every agent invocation) on JSON, which is the case row 48 protects.
    """

    assert fallback_output_mode(_NonTTYStream()) == OutputMode.JSON
    assert fallback_output_mode(_TTYStream()) == OutputMode.TEXT
    assert fallback_output_mode(_NonTTYStream()) == resolve_output_mode(
        None, stream=_NonTTYStream(), env={}
    )


def test_envelope_shape_is_the_v1_contract() -> None:
    exc = InvalidOutputModeError("bogus", "NOVETEST_OUTPUT")
    payload = invalid_output_mode_envelope(exc).to_dict()
    assert payload["schema"] == "novetest/v1"
    assert payload["command"] == "cli"
    assert payload["ok"] is False
    assert payload["warnings"] == []
    assert payload["errors"][0]["code"] == "invalid-output-mode"
    assert payload["errors"][0]["details"] == {
        "value": "bogus",
        "source": "NOVETEST_OUTPUT",
        "supported": ["text", "json", "ndjson"],
    }


def test_envelope_renders_in_every_mode() -> None:
    """The refusal must survive the renderer it fell back to.

    ``main`` picks the fallback mode and then emits — if TEXT rendering of
    an error-only ``command="cli"`` envelope threw, the fix would have
    replaced one traceback with another on exactly the tty path.
    """

    exc = InvalidOutputModeError("bogus", "--output")
    envelope = invalid_output_mode_envelope(exc)
    for mode in OutputMode:
        stream = io.StringIO()
        emit_envelope(envelope, mode, stream=stream)
        assert "invalid-output-mode" in stream.getvalue(), mode


def test_uses_injected_env_mapping() -> None:
    assert resolve_output_mode(None, stream=_TTYStream(), env={"NOVETEST_OUTPUT": "ndjson"}) == OutputMode.NDJSON


def test_injected_empty_env_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVETEST_OUTPUT", "json")
    assert resolve_output_mode(None, stream=_NonTTYStream(), env={}) == OutputMode.JSON
