"""Text renderers for the ``memory`` sub-app: list / show / delete.

Command tokens ``"memory.list"`` / ``"memory.show"`` / ``"memory.delete"``.
"""

from __future__ import annotations

from typing import Any

from novetest.cli.output import Envelope
from novetest.cli.renderers._format import (
    GLYPH_OK,
    format_table,
    format_timestamp,
    target_label,
)

_KV_WIDTH = 12


def _kv_block(pairs: list[tuple[str, str]]) -> str:
    return "\n".join(f"{(label + ':').ljust(_KV_WIDTH)}{value}" for label, value in pairs)


def render_memory_list(envelope: Envelope) -> str:
    """Run-History table: run_id / target / status / created_at."""

    data = envelope.data
    entries = data.get("entries", [])
    count = data.get("count", len(entries))
    run_word = "run" if count == 1 else "runs"
    if not entries:
        return f"0 {run_word}"

    rows: list[list[str]] = []
    for entry in entries:
        record = entry.get("run_record", {})
        reference = record.get("run_reference", {})
        status = record.get("status", "?")
        if entry.get("tombstoned_at") is not None:
            status += " (tombstoned)"
        rows.append(
            [
                reference.get("run_id", "?"),
                target_label(record.get("target_expression", "")),
                status,
                format_timestamp(reference.get("created_at")),
            ]
        )
    table = format_table(["run_id", "target", "status", "created_at"], rows)
    return f"{count} {run_word}\n\n{table}"


def render_memory_show(envelope: Envelope) -> str:
    """Key-value block for a single Memory Entry."""

    data = envelope.data
    entry = data.get("memory_entry", {})
    record = entry.get("run_record", {})
    reference = record.get("run_reference", {})

    engine = record.get("engine_name", "?")
    engine_version = record.get("engine_version")
    ecosystem = record.get("ecosystem", "?")
    engine_str = (
        f"{engine} {engine_version} ({ecosystem})"
        if engine_version
        else f"{engine} ({ecosystem})"
    )

    started = record.get("started_at")
    completed = record.get("completed_at")
    duration = (
        f"{completed - started}ms"
        if isinstance(started, int) and isinstance(completed, int)
        else "—"
    )

    counts = record.get("summary_counts", {})
    counts_str = " ".join(f"{key}={counts[key]}" for key in sorted(counts))

    evidence = " ".join(
        f"{name}={'yes' if entry.get(flag) else 'no'}"
        for name, flag in (
            ("coverage", "has_coverage_facts"),
            ("regression", "has_regression_facts"),
            ("localization", "has_localization_findings"),
            ("replay", "has_replay_result"),
        )
    )

    pairs: list[tuple[str, Any]] = [
        ("run_id", reference.get("run_id", "?")),
        ("target", target_label(record.get("target_expression", ""))),
        ("status", record.get("status", "?")),
        ("engine", engine_str),
        ("created", format_timestamp(reference.get("created_at"))),
        ("duration", duration),
        ("tests", counts_str or "—"),
        ("evidence", evidence),
        ("tombstoned", "yes" if entry.get("tombstoned_at") is not None else "no"),
    ]
    return _kv_block([(label, str(value)) for label, value in pairs])


def render_memory_delete(envelope: Envelope) -> str:
    """One-line tombstone confirmation."""

    data = envelope.data
    run_id = (
        data.get("memory_entry", {})
        .get("run_record", {})
        .get("run_reference", {})
        .get("run_id", "?")
    )
    return f"{GLYPH_OK} Tombstoned run_id={run_id}"
