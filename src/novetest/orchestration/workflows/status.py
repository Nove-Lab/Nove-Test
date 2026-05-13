"""``novetest status`` workflow — Phase 1 simplified view.

Returns the latest Run Reference and Run History readiness, plus
per-sub-report availability flags. In Phase 1 the derived facts (Coverage,
Regression, Localization, Replay) are not produced, so every sub-report is
reported as ``unavailable``. Phase 2+ slices replace the constants with
real ``check_*_availability`` calls without changing this shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from novetest.memory import ProjectStore, list_run_history
from novetest.models import MemoryEntry


@dataclass(slots=True, frozen=True)
class StatusView:
    """Status entity surfaced by ``novetest status``."""

    latest_entry: MemoryEntry | None
    run_history_size: int
    coverage_available: bool = False
    regression_available: bool = False
    localization_available: bool = False
    replay_available: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "latest_run_reference": (
                self.latest_entry.run_record.run_reference.to_dict()
                if self.latest_entry is not None
                else None
            ),
            "run_history_size": self.run_history_size,
            "sub_reports": {
                "coverage": "available" if self.coverage_available else "unavailable",
                "regression": "available" if self.regression_available else "unavailable",
                "localization": (
                    "available" if self.localization_available else "unavailable"
                ),
                "replay": "available" if self.replay_available else "unavailable",
            },
        }


def build_status_view(store: ProjectStore) -> StatusView:
    """Aggregate the current Memory state into a Status view."""

    history = list_run_history(store)
    latest = history[0] if history else None
    return StatusView(latest_entry=latest, run_history_size=len(history))
