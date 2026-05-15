"""On-disk persistence helpers for ``CoverageFactSet``.

The path layout is **load-bearing**: Memory's ``_availability_flags`` probes
``<store>/coverage/facts/run_<run_id>/coverage_facts.json`` to auto-flip
``MemoryEntry.has_coverage_facts``. Keep filename / directory exactly as
named here. See ``design/interace-contract/coverage.md`` and the Memory
store code.
"""

from __future__ import annotations

import json
from pathlib import Path

from novetest.memory.project_store import ProjectStore
from novetest.models.coverage_fact_set import CoverageFactSet


COVERAGE_FACTS_DIRNAME = "facts"
COVERAGE_FACTS_FILENAME = "coverage_facts.json"
_RUN_DIR_PREFIX = "run_"


def coverage_facts_dir(store: ProjectStore, run_id: str) -> Path:
    """Return the directory where this run's coverage facts live."""
    return (
        store.path / "coverage" / COVERAGE_FACTS_DIRNAME / f"{_RUN_DIR_PREFIX}{run_id}"
    )


def coverage_facts_path(store: ProjectStore, run_id: str) -> Path:
    """Return the absolute path to this run's ``coverage_facts.json``."""
    return coverage_facts_dir(store, run_id) / COVERAGE_FACTS_FILENAME


def write_coverage_facts(store: ProjectStore, fact_set: CoverageFactSet) -> Path:
    """Persist ``fact_set`` to its canonical location and return the path.

    The directory is created on demand. Re-writing an existing file is
    permitted (overwrite semantics) so ``derive_coverage_facts`` can refresh
    facts when called again on the same run — callers control whether to
    re-derive.
    """
    target_dir = coverage_facts_dir(store, fact_set.run_reference.run_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / COVERAGE_FACTS_FILENAME
    target.write_text(
        json.dumps(fact_set.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return target


def read_coverage_facts(store: ProjectStore, run_id: str) -> CoverageFactSet | None:
    """Load a previously persisted ``CoverageFactSet`` for ``run_id``.

    Returns ``None`` when the canonical file does not exist. Corrupt JSON
    or schema mismatches raise (they are not the same kind of expected
    "no facts yet" condition).
    """
    target = coverage_facts_path(store, run_id)
    if not target.is_file():
        return None
    raw = target.read_text(encoding="utf-8")
    return CoverageFactSet.from_dict(json.loads(raw))
