"""Memory sub-product: Project Store lifecycle + Run evidence persistence.

Public surface mirrors ``design/interace-contract/memory.md``. Phase 1
implements Section 1 (Project Store) in ``project_store`` and the Phase 1
subset of Section 2 (Memory) in ``store``. See those modules' docstrings for
scope notes.
"""

from __future__ import annotations

from novetest.memory.project_store import (
    ENV_NOVETEST_HOME,
    STORE_DIRNAME,
    STORE_METADATA_FILENAME,
    ProjectStore,
    ProjectStoreCorruptError,
    create_project_store,
    get_project_store_state,
    locate_project_store,
    sweep_staging_residue,
)
from novetest.memory.store import (
    RECORD_FILENAME,
    RUN_DIR_PREFIX,
    RunEvidenceAlreadyExistsError,
    RunEvidenceNotFoundError,
    SkippedRecord,
    delete_run_evidence,
    find_runs_for_target,
    get_memory_entry_availability,
    list_run_history,
    retrieve_run_evidence,
    store_run_evidence,
)


__all__ = [
    "ENV_NOVETEST_HOME",
    "RECORD_FILENAME",
    "RUN_DIR_PREFIX",
    "STORE_DIRNAME",
    "STORE_METADATA_FILENAME",
    "ProjectStore",
    "ProjectStoreCorruptError",
    "RunEvidenceAlreadyExistsError",
    "RunEvidenceNotFoundError",
    "SkippedRecord",
    "create_project_store",
    "delete_run_evidence",
    "find_runs_for_target",
    "get_memory_entry_availability",
    "get_project_store_state",
    "list_run_history",
    "locate_project_store",
    "retrieve_run_evidence",
    "store_run_evidence",
    "sweep_staging_residue",
]
