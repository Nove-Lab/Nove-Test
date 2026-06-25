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


def test_onboarding_includes_reset() -> None:
    """``reset`` is a setup-class verb enumerated beside ``init`` in the
    onboarding surface (the first post-MVP verb)."""
    surface = describe_command_surface()
    reset = next(
        (c for c in surface.onboarding if c.name == "novetest reset"), None
    )
    assert reset is not None, "novetest reset must be enumerated in onboarding"
    assert reset.group == "onboarding"
    assert reset.available_in_phase == 7


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
    # Upper bound is 7: the MVP spans phases 0–6; ``novetest reset`` is the
    # first post-MVP verb (decision 2026-06-24-reset-verb-and-store-wipe-
    # primitive), so the surface now reaches phase 7.
    surface = describe_command_surface()
    for spec in surface.onboarding + surface.operating:
        assert 0 <= spec.available_in_phase <= 7


def test_to_dict_round_trip_keys() -> None:
    payload = describe_command_surface().to_dict()
    assert set(payload) == {"schemaVersion", "onboarding", "operating"}
    sample = payload["onboarding"][0]
    assert set(sample) == {"name", "summary", "group", "availableInPhase"}
