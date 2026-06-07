"""Unit tests for ``novetest.run.types`` — the AdapterWarning + NativeResult
field contracts introduced by the 2026-06-06 envelope-warnings-projection
slice.

The ``AdapterWarning`` dataclass MUST stay structurally compatible with
``cli.output.EnvelopeWarning`` (criterion #3 of
``decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md``)
so the CLI handler's field-by-field projection at envelope-construction
time stays a one-liner. Mismatch in field names, types, or defaults
would force the projection helper into special-case branching — the
contract this test family pins.
"""

from __future__ import annotations

import dataclasses

import pytest

from novetest.cli.output import EnvelopeWarning
from novetest.run.types import AdapterWarning, NativeResult


class TestAdapterWarningShape:
    """Structural contract: ``AdapterWarning`` and ``EnvelopeWarning`` are
    field-by-field identical (criterion #3 of decision 2026-06-06)."""

    def test_adapter_warning_has_three_fields(self) -> None:
        fields = {f.name for f in dataclasses.fields(AdapterWarning)}
        assert fields == {"code", "message", "details"}

    def test_adapter_warning_field_names_match_envelope_warning(self) -> None:
        adapter_fields = {f.name for f in dataclasses.fields(AdapterWarning)}
        envelope_fields = {f.name for f in dataclasses.fields(EnvelopeWarning)}
        assert adapter_fields == envelope_fields, (
            f"AdapterWarning {adapter_fields!r} and EnvelopeWarning "
            f"{envelope_fields!r} must have identical field sets per "
            f"decision 2026-06-06 criterion #3"
        )

    def test_adapter_warning_is_frozen(self) -> None:
        warning = AdapterWarning(code="x", message="y")
        with pytest.raises(dataclasses.FrozenInstanceError):
            warning.code = "z"  # type: ignore[misc]

    def test_adapter_warning_details_defaults_to_empty_dict(self) -> None:
        warning = AdapterWarning(code="x", message="y")
        assert warning.details == {}

    def test_adapter_warning_accepts_arbitrary_detail_values(self) -> None:
        # Brief §2.1 Option β: ``details: dict[str, Any]``. Non-string
        # values (ints, nested dicts, lists) round-trip.
        details = {
            "count": 3,
            "nested": {"key": "value"},
            "list": [1, 2, 3],
        }
        warning = AdapterWarning(code="x", message="y", details=details)
        assert warning.details == details


class TestAdapterWarningEnvelopeWarningProjection:
    """The projection function the CLI handler uses is a field-by-field
    copy — verify the shape is preserved through that copy."""

    def test_field_by_field_copy_preserves_all_fields(self) -> None:
        adapter = AdapterWarning(
            code="engine-misconfigured",
            message="coverlet absent",
            details={"csproj": "MathLib.Tests.csproj"},
        )
        envelope = EnvelopeWarning(
            code=adapter.code,
            message=adapter.message,
            details=dict(adapter.details),
        )
        assert envelope.code == adapter.code
        assert envelope.message == adapter.message
        assert envelope.details == adapter.details
        # Confirm the copy is independent — mutating one doesn't bleed
        # into the other. Both are frozen so we cannot reassign, but
        # ``details`` is a mutable dict; the projection's ``dict(...)``
        # call must produce a fresh dict.
        envelope.details["new-key"] = "new-value"
        assert "new-key" not in adapter.details


class TestNativeResultWarningsField:
    """``NativeResult.warnings`` MUST default to the empty tuple so the
    five existing adapters (and any future adapter that emits no warnings)
    keep their construction call sites unchanged. Plumbing-only adapters
    rely on this default."""

    def _make_minimal_result(self, **overrides: object) -> NativeResult:
        defaults: dict[str, object] = dict(
            engine_name="pytest",
            payload={},
            artifact_paths={},
            returncode=0,
            started_at_ms=0,
            completed_at_ms=0,
        )
        defaults.update(overrides)
        return NativeResult(**defaults)  # type: ignore[arg-type]

    def test_warnings_defaults_to_empty_tuple(self) -> None:
        result = self._make_minimal_result()
        assert result.warnings == ()
        assert isinstance(result.warnings, tuple)

    def test_warnings_accepts_tuple_of_adapter_warnings(self) -> None:
        warnings = (
            AdapterWarning(code="a", message="m1"),
            AdapterWarning(code="b", message="m2"),
        )
        result = self._make_minimal_result(warnings=warnings)
        assert result.warnings == warnings
        assert len(result.warnings) == 2
        assert result.warnings[0].code == "a"
        assert result.warnings[1].code == "b"

    def test_warnings_is_immutable(self) -> None:
        result = self._make_minimal_result()
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.warnings = (AdapterWarning(code="x", message="y"),)  # type: ignore[misc]
