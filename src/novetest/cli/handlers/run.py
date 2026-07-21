"""``novetest run [target]`` verb handler (W3/S47, ORC-01).

Extracted verbatim from ``cli/app.py``. Executes the resolved Test Target
via the Run engine, persists the Run Record through Memory, and projects the
``RunOutcome`` onto the v1 envelope (optionally with ``data.coverage_outcome``
under ``--coverage``). Pure motion — the wire contract is unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from cyclopts import Parameter

from novetest.cli import _shared
from novetest.cli._shared import (
    _adapter_to_envelope_warnings,
    _emit_and_exit,
    _require_store,
    _store_corrupt_envelope,
    _validate_engine_flag,
)
from novetest.cli.output import (
    EXIT_STORAGE,
    Envelope,
    run_status_to_ok_exit,
)
from novetest.memory import ProjectStoreCorruptError
from novetest.orchestration.anchor_resolution import EngineAmbiguousError
from novetest.orchestration.projection import coverage_outcome_payload
from novetest.orchestration.workflows import run_target_in_store
from novetest.run import RunEngineError


def run_cmd(
    target: str = "",
    *,
    coverage: Annotated[bool, Parameter(name=["--coverage", "-c"])] = False,
    engine: Annotated[str | None, Parameter(name=["--engine"])] = None,
) -> None:
    """Execute the resolved Test Target and persist the Run Record.

    With ``--coverage`` / ``-c``, the run is invoked with coverage
    instrumentation and Coverage's ``derive_coverage_facts`` is called
    after persistence. The resulting fact-set (or an explicit
    ``CoverageUnavailable`` outcome) is reported under the envelope's
    ``data.coverage_outcome`` block; without the flag, the key is omitted
    entirely so non-coverage runs stay byte-equivalent to Phase 1.

    ``--engine <name>`` executes a one-off override of the store's pinned
    engine WITHOUT re-pinning (decision 2026-07-03-engine-selection-policy
    D3); invalid names fail flag validation (``invalid-flag``, exit 2).
    """
    store = _require_store("run")
    engine_pair = _validate_engine_flag("run", engine)
    try:
        outcome = asyncio.run(
            run_target_in_store(
                target, store, collect_coverage=coverage, engine=engine_pair
            )
        )
    except (EngineAmbiguousError, RunEngineError) as exc:
        # ORC-02/ORC-21: one shared mapping for both verbs. Since the S19 seam
        # split ``resolve_workspace`` no longer migrates, so ``EngineAmbiguous``
        # now surfaces here as the PRIMARY path — ``resolve_execution_engine``
        # (called first in the workflow, before any subprocess) raises it on a
        # legacy + ambiguous store. The RunEngineError family (EngineNotReady /
        # AdapterInvocation / the structural fallback) maps to its structured
        # exit here.
        _emit_and_exit(*_shared._map_execution_exception("run", exc))
    except ProjectStoreCorruptError as exc:
        # S42 residual loud path (the workflow's post-persist refresh /
        # coverage derive found the just-written record corrupt — TOCTOU):
        # a storage failure, not a cli-error.
        _emit_and_exit(_store_corrupt_envelope("run", str(exc)), EXIT_STORAGE)

    entry = outcome.memory_entry
    record = entry.run_record
    # Single shared status→(ok, exit) mapping — see run_status_to_ok_exit
    # (W1/S8, ORC-04): failed AND errored are user results at exit 3.
    ok, exit_code = run_status_to_ok_exit(record.status)

    data: dict[str, Any] = {"memory_entry": entry.to_dict()}
    if outcome.coverage_outcome is not None:
        data["coverage_outcome"] = coverage_outcome_payload(outcome.coverage_outcome)
    envelope_warnings = _adapter_to_envelope_warnings(outcome.warnings)
    _emit_and_exit(
        Envelope(command="run", ok=ok, data=data, warnings=envelope_warnings),
        exit_code,
    )
