"""Unit tests for the ``_adapter_to_envelope_warnings`` projection helper
in ``cli/app.py``, plus the ``build_test_envelope`` warning-projection
contract.

These pin the field-by-field copy from ``AdapterWarning`` (run/cli-
boundary type) to ``EnvelopeWarning`` (envelope serialization type)
introduced by the 2026-06-06 envelope-warnings-projection slice.

Why this lives in a separate test module:
- ``test_run_cmd.py`` exercises ``run_cmd`` against stubbed workflows;
  threading the warning-projection check through every workflow stub
  would obscure the contract. A dedicated module makes the projection
  contract a discoverable test target.
- The projection function is pure (no side effects, no I/O) so the
  tests run instantly without any fixture state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from novetest.cli.app import _adapter_to_envelope_warnings
from novetest.cli.handlers.test import build_test_envelope
from novetest.cli.output import EnvelopeWarning
from novetest.run.types import AdapterWarning


class TestAdapterToEnvelopeWarningsHelper:
    def test_empty_input_returns_empty_tuple(self) -> None:
        assert _adapter_to_envelope_warnings(()) == ()

    def test_single_warning_round_trips_all_fields(self) -> None:
        adapter = AdapterWarning(
            code="engine-misconfigured",
            message="coverlet.collector not in package graph",
            details={"csproj": "MathLib.Tests.csproj", "coverlet_floor": "6.0.2"},
        )
        result = _adapter_to_envelope_warnings((adapter,))
        assert len(result) == 1
        envelope = result[0]
        assert isinstance(envelope, EnvelopeWarning)
        assert envelope.code == adapter.code
        assert envelope.message == adapter.message
        assert envelope.details == adapter.details

    def test_multiple_warnings_preserve_order(self) -> None:
        adapters = (
            AdapterWarning(code="ambiguous-build-tool", message="both pom + gradle"),
            AdapterWarning(code="missing-jacoco", message="no jacoco plugin"),
        )
        result = _adapter_to_envelope_warnings(adapters)
        assert [w.code for w in result] == [a.code for a in adapters]

    def test_details_dict_is_copied_not_aliased(self) -> None:
        """The projection's ``dict(w.details)`` call makes the envelope's
        details independent of the adapter's details. This prevents a
        post-projection mutation in one layer from bleeding into the
        other — defensive even though both layers are frozen at the
        dataclass level (the inner dict is still mutable)."""

        original_details = {"key": "value"}
        adapter = AdapterWarning(
            code="x", message="y", details=original_details
        )
        result = _adapter_to_envelope_warnings((adapter,))
        # Mutate the projected envelope's details — adapter's stay clean.
        result[0].details["mutation"] = "after-projection"
        assert "mutation" not in original_details
        assert "mutation" not in adapter.details

    def test_envelope_warning_to_dict_serializes_projected_payload(self) -> None:
        """End-to-end shape check: the projected EnvelopeWarning emits
        the same wire dict the existing localization handler emits."""

        adapter = AdapterWarning(
            code="my-kind", message="my msg", details={"a": 1}
        )
        envelope = _adapter_to_envelope_warnings((adapter,))[0]
        wire = envelope.to_dict()
        assert wire == {
            "code": "my-kind",
            "message": "my msg",
            "details": {"a": 1},
        }


class TestBuildTestEnvelopeWarningsProjection:
    """``build_test_envelope`` MUST project ``TestOutcome.warnings`` onto
    the resulting envelope's ``warnings`` field using the same
    AdapterWarning → EnvelopeWarning conversion."""

    def _build_outcome(
        self, *, warnings: tuple[AdapterWarning, ...]
    ) -> "_FakeTestOutcome":
        return _FakeTestOutcome.create(warnings=warnings)

    def test_empty_warnings_produces_empty_envelope_warnings(self) -> None:
        outcome = self._build_outcome(warnings=())
        envelope, _exit_code = build_test_envelope(outcome)  # type: ignore[arg-type]
        assert envelope.warnings == ()

    def test_single_warning_appears_on_envelope(self) -> None:
        adapter = AdapterWarning(
            code="missing-jacoco",
            message="add jacoco plugin",
            details={"build_tool": "maven"},
        )
        outcome = self._build_outcome(warnings=(adapter,))
        envelope, _exit_code = build_test_envelope(outcome)  # type: ignore[arg-type]
        assert len(envelope.warnings) == 1
        wire = envelope.warnings[0].to_dict()
        assert wire["code"] == adapter.code
        assert wire["message"] == adapter.message
        assert wire["details"] == adapter.details

    def test_multiple_warnings_preserved_in_envelope_order(self) -> None:
        warnings = (
            AdapterWarning(code="ambiguous-build-tool", message="m1"),
            AdapterWarning(code="missing-jacoco", message="m2"),
        )
        outcome = self._build_outcome(warnings=warnings)
        envelope, _exit_code = build_test_envelope(outcome)  # type: ignore[arg-type]
        assert [w.code for w in envelope.warnings] == [
            "ambiguous-build-tool",
            "missing-jacoco",
        ]


# ---------------------------------------------------------------------------
# Minimal TestOutcome stand-in. We can't easily instantiate TestOutcome
# because it requires a full MemoryEntry + StageEligibility + FactBundle
# graph; the build_test_envelope helper only reads four specific
# attributes on the outcome (``memory_entry.run_record.run_reference``,
# ``stage_eligibility``, ``recommendations``, ``run_record_status``,
# ``warnings``), so a fake satisfies the duck-typed surface.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _FakeRunReference:
    run_id: str = "01TESTTESTTESTTESTTESTTEST"
    created_at: int = 1_700_000_000_000

    def to_dict(self) -> dict[str, object]:
        return {"run_id": self.run_id, "created_at": self.created_at}


@dataclass(slots=True)
class _FakeRunRecord:
    run_reference: _FakeRunReference = field(default_factory=_FakeRunReference)


@dataclass(slots=True)
class _FakeMemoryEntry:
    run_record: _FakeRunRecord = field(default_factory=_FakeRunRecord)


@dataclass(slots=True)
class _FakeStageEligibility:
    def to_dict(self) -> dict[str, object]:
        return {
            "coverage": "available",
            "regression": "unavailable",
            "localization": "unavailable",
            "replay": "not_run",
            "per_stage_reasons": {
                "coverage": None,
                "regression": "no-comparable-baseline",
                "localization": "no-failed-tests",
                "replay": "replay_not_run",
            },
        }


@dataclass(slots=True)
class _FakeTestOutcome:
    memory_entry: _FakeMemoryEntry
    artifact_dir: Path
    stage_eligibility: _FakeStageEligibility
    fact_bundle: object  # opaque — build_test_envelope doesn't touch it
    recommendations: list[object]
    run_record_status: str
    warnings: tuple[AdapterWarning, ...]

    @classmethod
    def create(
        cls, *, warnings: tuple[AdapterWarning, ...]
    ) -> "_FakeTestOutcome":
        return cls(
            memory_entry=_FakeMemoryEntry(),
            artifact_dir=Path("/tmp/x"),
            stage_eligibility=_FakeStageEligibility(),
            fact_bundle=object(),
            recommendations=[],
            run_record_status="passed",
            warnings=warnings,
        )
