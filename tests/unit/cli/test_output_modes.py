from __future__ import annotations

import io
from typing import Any

import pytest

from novetest.cli.output import OutputMode, resolve_output_mode


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


def test_uses_injected_env_mapping() -> None:
    assert resolve_output_mode(None, stream=_TTYStream(), env={"NOVETEST_OUTPUT": "ndjson"}) == OutputMode.NDJSON


def test_injected_empty_env_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVETEST_OUTPUT", "json")
    assert resolve_output_mode(None, stream=_NonTTYStream(), env={}) == OutputMode.JSON
