"""Unit tests for the `novetest localization latest` CLI handler.

``localization latest`` is a thin wrapper around
``derive_latest_localization``: resolve store → validate flags → call the
engine's latest-resolution composer → project the outcome onto the envelope.
Most branches live inside the engine; the CLI's only job is correct
projection, flag validation, and store handling.

NOTE: These tests require ``localization_latest`` to be registered in
``cli/app.py`` as a command on ``localization_app``. If the handler is not
yet present the tests will fail with ``AttributeError`` — add the handler
per the Phase-4 CLI task brief before running.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from novetest.cli import app as app_module
from novetest.cli.output import Envelope, EnvelopeError, OutputMode, emit_envelope
from novetest.localization import (
    DEFAULT_FORMULA,
    DEFAULT_TOP_N,
    FORMULAS,
    LocalizationFinding,
    LocalizationUnavailable,
)
from novetest.localization.results import (
    REASON_MISSING_DERIVED_FACTS,
    REASON_NO_RUN_EVIDENCE,
    REASON_RUN_NOT_ANALYZABLE,
)
from novetest.models import RunReference
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_RUN_ID = "01LATESTLOCLATESTLOCLATEST0"


def _make_finding(
    *,
    formula: str = "ochiai",
    top_n: int = 10,
    derived_at: int = 7_000,
) -> LocalizationFinding:
    ref = RunReference(run_id=_RUN_ID, created_at=1_700_000_000_000)
    loc = CodeLocation(
        kind="symbol",
        file="src/calc.py",
        symbol="buggy",
        line_range=(4, 5),
        primary_line=5,
        evidence_lines=(5,),
    )
    citation = EvidenceCitation(
        kind="test_result",
        run_reference=ref,
        selector={"test_id": "tests/test_calc.py::test_buggy", "outcome": "failed"},
    )
    entry = LocalizationEntry(
        rank=1,
        tied_with=(),
        code_location=loc,
        score_raw=1.0,
        score_normalized=1.0,
        formula=formula,
        alternate_scores={f: 0.9 for f in FORMULAS if f != formula},
        related_failed_tests=("tests/test_calc.py::test_buggy",),
        evidence_citations=(citation,),
    )
    alt_scores_available = tuple(f for f in sorted(FORMULAS) if f != formula)
    return LocalizationFinding(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mode="sbfl_per_test",
        confidence="high",
        formula=formula,
        alternate_scores_available=alt_scores_available,
        top_n=top_n,
        entries=(entry,),
        derived_at=derived_at,
        metadata={},
    )


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_active_mode", OutputMode.JSON)


@pytest.fixture
def stub_store(monkeypatch: pytest.MonkeyPatch) -> object:
    sentinel = object()
    monkeypatch.setattr(app_module, "_require_store", lambda _cmd: sentinel)
    return sentinel


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    return json.loads(out)


# ---------------------------------------------------------------------------
# Case 1: Happy path — fact-set, identical projection to localization <run_id>
# ---------------------------------------------------------------------------


def test_localization_latest_emits_fact_set_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """``derive_latest_localization`` returns a finding → ``ok: true``,
    exit 0, ``data.localization_outcome.kind == "fact-set"``, schema_version
    absent from the block."""

    seen_stores: list[Any] = []

    def fake_derive(
        store: Any, *, formula: str = "ochiai", top_n: int = 10
    ) -> LocalizationFinding:
        seen_stores.append(store)
        return _make_finding()

    monkeypatch.setattr(app_module, "derive_latest_localization", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest()
    assert exc_info.value.code == 0
    # Handler forwards exactly the resolved store sentinel.
    assert seen_stores == [stub_store]

    payload = _captured_envelope(capsys)
    assert payload["command"] == "localization.latest"
    assert payload["ok"] is True
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "fact-set"
    assert "schema_version" not in outcome
    assert outcome["formula"] == "ochiai"
    assert isinstance(outcome["entries"], list)


# ---------------------------------------------------------------------------
# Case 2: Empty store → no_run_evidence, run_reference null, detail present
# ---------------------------------------------------------------------------


def test_localization_latest_empty_store_surfaces_no_run_evidence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """An empty store: ``derive_latest_localization`` returns
    ``LocalizationUnavailable(reason="no_run_evidence")`` with
    ``run_reference=None``. The CLI surfaces ``kind: "unavailable"``,
    ``ok: true``, exit 0; ``run_reference`` is ``null`` on the wire."""

    monkeypatch.setattr(
        app_module,
        "derive_latest_localization",
        lambda _store, *, formula, top_n: LocalizationUnavailable(
            run_reference=None,
            reason=REASON_NO_RUN_EVIDENCE,
            detail="store has no run history",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest()
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_RUN_EVIDENCE
    assert outcome["run_reference"] is None
    assert outcome["detail"] is not None


# ---------------------------------------------------------------------------
# Case 3: All-tombstoned → run_not_analyzable
# ---------------------------------------------------------------------------


def test_localization_latest_all_tombstoned_surfaces_run_not_analyzable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """When all runs in the store are tombstoned / non-analyzable:
    ``derive_latest_localization`` returns ``run_not_analyzable``."""

    monkeypatch.setattr(
        app_module,
        "derive_latest_localization",
        lambda _store, *, formula, top_n: LocalizationUnavailable(
            run_reference=None,
            reason=REASON_RUN_NOT_ANALYZABLE,
            detail="all runs are tombstoned",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest()
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_RUN_NOT_ANALYZABLE


# ---------------------------------------------------------------------------
# Case 4: --formula tarantula --top-n 5 → both kwargs forwarded to engine
# ---------------------------------------------------------------------------


def test_localization_latest_flags_forwarded_to_engine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """Both ``--formula`` and ``--top-n`` are forwarded AS keyword arguments
    to ``derive_latest_localization``."""

    seen_kwargs: list[dict[str, Any]] = []

    def fake_derive(
        _store: Any, *, formula: str, top_n: int
    ) -> LocalizationFinding:
        seen_kwargs.append({"formula": formula, "top_n": top_n})
        return _make_finding(formula=formula, top_n=top_n)

    monkeypatch.setattr(app_module, "derive_latest_localization", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest(formula="tarantula", top_n=5)
    assert exc_info.value.code == 0

    assert len(seen_kwargs) == 1
    assert seen_kwargs[0]["formula"] == "tarantula"
    assert seen_kwargs[0]["top_n"] == 5

    payload = _captured_envelope(capsys)
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "fact-set"
    assert outcome["formula"] == "tarantula"
    assert outcome["top_n"] == 5


# ---------------------------------------------------------------------------
# Case 5: Uninitialized workspace → uninitialized envelope, exit 2
# ---------------------------------------------------------------------------


def test_localization_latest_uninitialized_workspace_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    """No Project Store → ``_require_store`` fires the uninitialized envelope
    and exits 2 BEFORE the engine is called."""

    def fake_require_store(_cmd: str) -> Any:
        import sys

        emit_envelope(
            Envelope(
                command="localization.latest",
                ok=False,
                errors=(EnvelopeError(code="uninitialized", message="no store"),),
            ),
            app_module._active_mode,
        )
        sys.exit(2)

    monkeypatch.setattr(app_module, "_require_store", fake_require_store)

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError(
            "derive_latest_localization called when no Project Store"
        )

    monkeypatch.setattr(app_module, "derive_latest_localization", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest()
    assert exc_info.value.code == 2
    payload = _captured_envelope(capsys)
    assert payload["errors"][0]["code"] == "uninitialized"
