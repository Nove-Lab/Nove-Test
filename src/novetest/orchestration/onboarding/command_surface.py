from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COMMAND_SURFACE_SCHEMA_VERSION = 1


@dataclass(slots=True, frozen=True)
class CommandSpec:
    name: str
    summary: str
    group: str
    available_in_phase: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "group": self.group,
            "availableInPhase": self.available_in_phase,
        }


@dataclass(slots=True, frozen=True)
class CommandSurface:
    schema_version: int
    onboarding: tuple[CommandSpec, ...]
    operating: tuple[CommandSpec, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "onboarding": [c.to_dict() for c in self.onboarding],
            "operating": [c.to_dict() for c in self.operating],
        }


_ONBOARDING: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="novetest --version",
        summary="Print CLI identity envelope.",
        group="onboarding",
        available_in_phase=0,
    ),
    CommandSpec(
        name="novetest --help",
        summary="Print command surface envelope.",
        group="onboarding",
        available_in_phase=0,
    ),
    CommandSpec(
        name="novetest init",
        summary="Initialize a Project Store under .novetest/ in the current workspace.",
        group="onboarding",
        available_in_phase=1,
    ),
)

_OPERATING: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="novetest test",
        summary="Run tests with integrated orchestration and synthesize a recommendation.",
        group="orchestration",
        available_in_phase=6,
    ),
    CommandSpec(
        name="novetest run",
        summary="Execute a Test Target via the native engine and persist a Run Record.",
        group="run",
        available_in_phase=1,
    ),
    CommandSpec(
        name="novetest memory list",
        summary="List Memory Entries in Run History.",
        group="memory",
        available_in_phase=1,
    ),
    CommandSpec(
        name="novetest memory show",
        summary="Show a Memory Entry by Run Reference.",
        group="memory",
        available_in_phase=1,
    ),
    CommandSpec(
        name="novetest memory delete",
        summary="Tombstone a Memory Entry; Run Reference remains resolvable.",
        group="memory",
        available_in_phase=1,
    ),
    CommandSpec(
        name="novetest inspect",
        summary="Aggregate run view across Memory and derived facts.",
        group="orchestration",
        available_in_phase=1,
    ),
    CommandSpec(
        name="novetest status",
        summary="Latest run plus per-sub-report availability summary.",
        group="orchestration",
        available_in_phase=1,
    ),
    CommandSpec(
        name="novetest coverage show",
        summary="Show Coverage Facts for a run.",
        group="coverage",
        available_in_phase=2,
    ),
    CommandSpec(
        name="novetest coverage diff",
        summary="Diff Coverage Facts between two runs.",
        group="coverage",
        available_in_phase=2,
    ),
    CommandSpec(
        name="novetest regression compare",
        summary="Compare two runs into a Regression Fact set.",
        group="regression",
        available_in_phase=3,
    ),
    CommandSpec(
        name="novetest regression latest",
        summary="Compute Regression Facts versus the latest baseline.",
        group="regression",
        available_in_phase=3,
    ),
    CommandSpec(
        name="novetest compare",
        summary="Composed Regression and Coverage delta between two runs.",
        group="orchestration",
        available_in_phase=3,
    ),
    CommandSpec(
        name="novetest localization",
        summary="Ranked suspicious code locations for a run.",
        group="localization",
        available_in_phase=4,
    ),
    CommandSpec(
        name="novetest replay",
        summary="Re-execute a stored run and classify reproducibility.",
        group="replay",
        available_in_phase=5,
    ),
)


def describe_command_surface() -> CommandSurface:
    return CommandSurface(
        schema_version=COMMAND_SURFACE_SCHEMA_VERSION,
        onboarding=_ONBOARDING,
        operating=_OPERATING,
    )
