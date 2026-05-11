from __future__ import annotations

from novetest.orchestration.onboarding.command_surface import (
    COMMAND_SURFACE_SCHEMA_VERSION,
    describe_command_surface,
)


def test_surface_has_schema_version() -> None:
    surface = describe_command_surface()
    assert surface.schema_version == COMMAND_SURFACE_SCHEMA_VERSION


def test_onboarding_includes_version_help_init() -> None:
    surface = describe_command_surface()
    names = {c.name for c in surface.onboarding}
    assert "novetest --version" in names
    assert "novetest --help" in names
    assert "novetest init" in names


def test_operating_covers_all_documented_subcommands() -> None:
    surface = describe_command_surface()
    names = {c.name for c in surface.operating}
    for expected in (
        "novetest test",
        "novetest run",
        "novetest memory list",
        "novetest memory show",
        "novetest memory delete",
        "novetest coverage show",
        "novetest coverage diff",
        "novetest regression compare",
        "novetest regression latest",
        "novetest localization",
        "novetest replay",
        "novetest inspect",
        "novetest compare",
        "novetest status",
    ):
        assert expected in names


def test_phase_numbers_are_sane() -> None:
    surface = describe_command_surface()
    for spec in surface.onboarding + surface.operating:
        assert 0 <= spec.available_in_phase <= 6


def test_to_dict_round_trip_keys() -> None:
    payload = describe_command_surface().to_dict()
    assert set(payload) == {"schemaVersion", "onboarding", "operating"}
    sample = payload["onboarding"][0]
    assert set(sample) == {"name", "summary", "group", "availableInPhase"}
