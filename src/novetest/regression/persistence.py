"""On-disk persistence helpers for ``RegressionFactSet``.

The path layout is **load-bearing**: Memory's ``_availability_flags``
probe scans ``<store>/regression/pairs/`` for any directory whose name
contains ``run_<run_id>`` (either the baseline or target position) to
auto-flip ``MemoryEntry.has_regression_facts``. Keep filename / directory
exactly as named here. See decision §1 and
``src/novetest/memory/store.py:_any_regression_pair_exists``.
"""

from __future__ import annotations

import json
from pathlib import Path

from novetest.memory import ProjectStore
from novetest.models.regression_fact_set import RegressionFactSet


REGRESSION_PAIRS_DIRNAME = "pairs"
REGRESSION_FACTS_FILENAME = "regression_facts.json"
_RUN_DIR_PREFIX = "run_"
# Literal double-underscore join between baseline and target run IDs in the
# pair directory name (decision §1). The joiner is part of the contract;
# Memory's probe uses ``run_<id>`` substring matching that does NOT depend
# on the joiner shape, but consumers parsing the directory name DO depend
# on the literal ``__``.
_PAIR_JOINER = "__"


def regression_pair_dirname(baseline_run_id: str, target_run_id: str) -> str:
    """Return the canonical pair directory name for a (baseline, target) pair.

    The pair key uses the **literal argument order** — ``(rA, rB)`` and
    ``(rB, rA)`` are distinct operations with distinct directory names,
    because transition direction is order-significant (pass→fail vs
    fail→pass).
    """
    return (
        f"{_RUN_DIR_PREFIX}{baseline_run_id}"
        f"{_PAIR_JOINER}"
        f"{_RUN_DIR_PREFIX}{target_run_id}"
    )


def regression_pair_dir(
    store: ProjectStore, baseline_run_id: str, target_run_id: str
) -> Path:
    """Return the directory where this pair's regression facts live."""
    return (
        store.path
        / "regression"
        / REGRESSION_PAIRS_DIRNAME
        / regression_pair_dirname(baseline_run_id, target_run_id)
    )


def regression_facts_path(
    store: ProjectStore, baseline_run_id: str, target_run_id: str
) -> Path:
    """Return the absolute path to this pair's ``regression_facts.json``."""
    return (
        regression_pair_dir(store, baseline_run_id, target_run_id)
        / REGRESSION_FACTS_FILENAME
    )


def write_regression_facts(
    store: ProjectStore, fact_set: RegressionFactSet
) -> Path:
    """Persist ``fact_set`` to its canonical location and return the path.

    The directory is created on demand. Re-writing an existing file is
    permitted (overwrite semantics) so a re-derivation refreshes the
    cached payload.
    """
    baseline_id = fact_set.baseline_run_reference.run_id
    target_id = fact_set.target_run_reference.run_id
    target_dir = regression_pair_dir(store, baseline_id, target_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / REGRESSION_FACTS_FILENAME
    target.write_text(
        json.dumps(fact_set.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return target


def read_regression_facts_raw(
    store: ProjectStore, baseline_run_id: str, target_run_id: str
) -> dict[str, object] | None:
    """Load the raw JSON dict for a pair's ``regression_facts.json``.

    Returns ``None`` when the canonical file does not exist. Returning the
    raw dict (rather than the parsed ``RegressionFactSet``) lets the
    retrieval layer inspect the embedded ``coverage_change.schema_version``
    for staleness detection (decision §C.6) before paying for the full
    ``from_dict`` decode.
    """
    target = regression_facts_path(store, baseline_run_id, target_run_id)
    if not target.is_file():
        return None
    raw = target.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(
            f"regression_facts.json at {target} is not a JSON object"
        )
    return parsed
