"""Single-source guard for the run_id lookup predicate (ORC-05 / S18).

Before S18 the "first Memory Entry whose Run Reference matches ``run_id``"
linear scan was copy-pasted across the run_id-addressed CLI and orchestration
verbs (``memory show`` / ``memory delete`` / ``_resolve_run_reference``,
``inspect``, and ``build_test_outcome_from_run_id``). S18 folded them onto ONE
Memory-owned predicate — ``memory.find_entry_by_run_id`` — so the "corrupt is
a miss, not an absence" (S42 Q1-A) and history-order semantics live in exactly
one place.

This guard is the S13 divergence-guard pattern: it fails loudly if any
consumer module re-grows the raw scan predicate instead of calling the shared
API. It is scoped to the modules that carried the folded scan — ``citations``'
``rr.run_reference.run_id == hit.payload[...]`` is a DIFFERENT operation
(matching a run against a recommendation citation, not a history lookup by a
requested id) and is deliberately out of scope.
"""

from __future__ import annotations

import re
from pathlib import Path

import novetest.cli.app as app_mod
import novetest.orchestration.workflows.inspect as inspect_mod
import novetest.orchestration.workflows.test as test_mod

# The linear-scan predicate S18 folded into ``find_entry_by_run_id``: comparing
# an entry's Run Reference id against the requested ``run_id``.
_SCAN_PREDICATE = re.compile(r"run_record\.run_reference\.run_id\s*==\s*run_id")

_CONSUMER_MODULES = (app_mod, inspect_mod, test_mod)


def _module_source(module: object) -> str:
    path = getattr(module, "__file__", None)
    assert path is not None, module
    return Path(path).read_text(encoding="utf-8")


def test_no_consumer_reimplements_the_run_id_scan_predicate() -> None:
    """No CLI/orchestration consumer re-implements the folded scan (S18)."""

    offenders = {
        module.__name__: len(_SCAN_PREDICATE.findall(_module_source(module)))
        for module in _CONSUMER_MODULES
        if _SCAN_PREDICATE.search(_module_source(module))
    }
    assert not offenders, (
        "run_id linear scan re-implemented instead of calling "
        f"memory.find_entry_by_run_id: {offenders}. Route the lookup through "
        "the single Memory-owned predicate (ORC-05 / S18)."
    )


def test_every_run_id_consumer_routes_through_the_shared_api() -> None:
    """Each folded site references the shared predicate by name — the positive
    complement to the negative guard, so deleting a call (and silently
    reverting to an inline scan) fails here too."""

    missing = [
        module.__name__
        for module in _CONSUMER_MODULES
        if "find_entry_by_run_id" not in _module_source(module)
    ]
    assert not missing, (
        "these run_id-addressed modules no longer reference "
        f"find_entry_by_run_id: {missing}"
    )
