from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TextIO

SCHEMA = "novetest/v1"

EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_USAGE = 2
EXIT_USER_TESTS_FAILED = 3
EXIT_ENGINE_MISSING = 4
EXIT_STORAGE = 5


class OutputMode(StrEnum):
    TEXT = "text"
    JSON = "json"
    NDJSON = "ndjson"


@dataclass(slots=True, frozen=True)
class EnvelopeError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


@dataclass(slots=True, frozen=True)
class EnvelopeWarning:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


@dataclass(slots=True, frozen=True)
class Envelope:
    command: str
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    errors: tuple[EnvelopeError, ...] = ()
    warnings: tuple[EnvelopeWarning, ...] = ()
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "command": self.command,
            "ok": self.ok,
            "data": dict(self.data),
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }


def resolve_output_mode(
    explicit: str | None, stream: TextIO | None = None, env: dict[str, str] | None = None
) -> OutputMode:
    if explicit is not None:
        return OutputMode(explicit)
    source_env = env if env is not None else os.environ
    env_value = source_env.get("NOVETEST_OUTPUT")
    if env_value:
        return OutputMode(env_value)
    target = stream if stream is not None else sys.stdout
    isatty = getattr(target, "isatty", None)
    if callable(isatty) and isatty():
        return OutputMode.TEXT
    return OutputMode.JSON


def apply_no_color(mode: OutputMode) -> None:
    if mode in (OutputMode.JSON, OutputMode.NDJSON):
        os.environ["NO_COLOR"] = "1"
        os.environ["FORCE_COLOR"] = "0"


def emit_envelope(envelope: Envelope, mode: OutputMode, stream: TextIO | None = None) -> None:
    target = stream if stream is not None else sys.stdout
    payload = envelope.to_dict()
    if mode == OutputMode.NDJSON:
        line = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        target.write(line + "\n")
    else:
        text = json.dumps(payload, indent=2, sort_keys=True)
        target.write(text + "\n")
    flush = getattr(target, "flush", None)
    if callable(flush):
        flush()


def not_implemented_envelope(command: str) -> Envelope:
    return Envelope(
        command=command,
        ok=False,
        errors=(
            EnvelopeError(
                code="not-implemented",
                message=f"{command} is not yet implemented",
            ),
        ),
    )
