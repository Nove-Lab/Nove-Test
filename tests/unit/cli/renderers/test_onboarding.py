"""Renderer tests for the onboarding surfaces (``version`` / ``help``)."""

from __future__ import annotations

from typing import Any

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text


def test_version(snapshot: SnapshotAssertion) -> None:
    envelope = Envelope(
        command="version",
        ok=True,
        data={
            "installedVersion": "0.1.1",
            "commandName": "novetest",
            "installLocation": "/usr/bin/python3",
            "pythonVersion": "3.11.9",
            "platform": "linux-x86_64",
            "verifiedAt": "2026-06-18T00:00:00Z",
        },
    )
    assert render_text(envelope) == snapshot


def test_help(snapshot: SnapshotAssertion) -> None:
    onboarding: list[dict[str, Any]] = [
        {
            "name": "novetest --version",
            "summary": "Print CLI identity envelope.",
            "group": "onboarding",
            "availableInPhase": 0,
        },
        {
            "name": "novetest init",
            "summary": "Initialize a Project Store under .novetest/.",
            "group": "onboarding",
            "availableInPhase": 1,
        },
    ]
    operating: list[dict[str, Any]] = [
        {
            "name": "novetest test",
            "summary": "Run tests with integrated orchestration.",
            "group": "orchestration",
            "availableInPhase": 6,
        },
        {
            "name": "novetest run",
            "summary": "Execute a Test Target via the native engine.",
            "group": "run",
            "availableInPhase": 1,
        },
    ]
    envelope = Envelope(
        command="help",
        ok=True,
        data={"schemaVersion": 1, "onboarding": onboarding, "operating": operating},
    )
    assert render_text(envelope) == snapshot
