"""Unit tests for the ``--engine`` CLI surface + the D7 init error envelopes.

CLI transport only — the workflow seams (``initialize_project_workspace``,
``run_target_in_store``, ``test_target_in_store``, ``_require_store`` /
``resolve_workspace``) are monkeypatched; workflow composition is unit-tested
in ``tests/unit/orchestration/``. Pins per decision
``2026-07-03-engine-selection-policy.md``:

- ``--engine`` validation against the six-engine matrix (``invalid-flag``,
  exit 2, mirroring ``--formula``) on ``init`` / ``run`` / ``test``;
- name → ``(ecosystem, engine_name)`` pair mapping forwarded to workflows;
- ``init`` D7 failure envelopes: ``no-engine-detected`` (exit 4, with the
  ``data.candidates`` discovery report + ``data.scan_refused``) and
  ``engine-ambiguous`` (exit 2, ``data.candidates`` with ``path: "."``);
- the migration-time ``engine-ambiguous`` surfaced through the shared
  ``_require_store`` seam on any verb.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from novetest.cli import app as app_module
from novetest.cli.output import OutputMode
from novetest.orchestration.workflows.discovery import DiscoveredCandidate
from novetest.orchestration.workflows.init import (
    InitEngineAmbiguous,
    InitializationResult,
    InitNoEngineDetected,
)
from novetest.run import EngineCandidate


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_active_mode", OutputMode.JSON)


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    payload: dict[str, Any] = json.loads(out)
    return payload


# ---------------------------------------------------------------------------
# _validate_engine_flag — name → pair mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "pair"),
    [
        ("pytest", ("python", "pytest")),
        ("jest", ("javascript-typescript", "jest")),
        ("junit", ("java", "junit")),
        ("go-test", ("go", "go-test")),
        ("cargo-test", ("rust", "cargo-test")),
        ("xunit", ("dotnet", "xunit")),
    ],
)
def test_all_six_engine_names_map_to_their_pairs(
    name: str, pair: tuple[str, str]
) -> None:
    assert app_module._validate_engine_flag("init", name) == pair


def test_absent_flag_passes_through_as_none() -> None:
    assert app_module._validate_engine_flag("init", None) is None


@pytest.mark.parametrize("command_fn", ["init", "run_cmd", "test_cmd"])
def test_invalid_engine_rejected_with_invalid_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    command_fn: str,
) -> None:
    """Bad ``--engine`` is a transport error on every verb that takes it —
    the workflow layer never sees it."""

    async def must_not_run(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("workflow invoked despite invalid --engine")

    monkeypatch.setattr(app_module, "_require_store", lambda _cmd: object())
    monkeypatch.setattr(app_module, "initialize_project_workspace", must_not_run)
    monkeypatch.setattr(app_module, "run_target_in_store", must_not_run)
    monkeypatch.setattr(app_module, "test_target_in_store", must_not_run)

    handler = getattr(app_module, command_fn)
    with pytest.raises(SystemExit) as exc_info:
        handler(engine="mocha")
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "invalid-flag"
    assert "--engine" in payload["errors"][0]["message"]
    assert "mocha" in payload["errors"][0]["message"]


# ---------------------------------------------------------------------------
# Pair forwarding to the workflows
# ---------------------------------------------------------------------------


def test_run_cmd_forwards_engine_pair(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    forwarded: list[Any] = []

    async def fake_run(target: str, store: Any, **kwargs: Any) -> Any:
        forwarded.append(kwargs["engine"])
        raise SystemExit(0)  # short-circuit; envelope shape is not under test

    monkeypatch.setattr(app_module, "_require_store", lambda _cmd: object())
    monkeypatch.setattr(app_module, "run_target_in_store", fake_run)

    with pytest.raises(SystemExit):
        app_module.run_cmd(engine="go-test")
    assert forwarded == [("go", "go-test")]
    capsys.readouterr()  # drain


def test_test_cmd_forwards_engine_pair(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    forwarded: list[Any] = []

    async def fake_test(target: str, store: Any, **kwargs: Any) -> Any:
        forwarded.append(kwargs["engine"])
        raise SystemExit(0)

    monkeypatch.setattr(app_module, "_require_store", lambda _cmd: object())
    monkeypatch.setattr(app_module, "test_target_in_store", fake_test)

    with pytest.raises(SystemExit):
        app_module.test_cmd(engine="cargo-test")
    assert forwarded == [("rust", "cargo-test")]
    capsys.readouterr()  # drain


def test_init_forwards_engine_pair_and_surfaces_pin(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    forwarded: list[Any] = []
    store = SimpleNamespace(
        path=Path("/ws/.novetest"),
        store_state="ready",
        initialized_at=1_700_000_000_000,
        pinned_engine=SimpleNamespace(
            to_dict=lambda: {"ecosystem": "python", "engine_name": "pytest"}
        ),
    )
    readiness = SimpleNamespace(
        state="ready",
        engine_context=SimpleNamespace(
            engine_name="pytest", ecosystem="python", engine_version="9.0.0"
        ),
        evidence=("pyproject.toml",),
        issues=(),
    )

    async def fake_init(workspace: Path, *, engine: Any = None) -> Any:
        forwarded.append(engine)
        return InitializationResult(
            store=store,  # type: ignore[arg-type]
            engine_readiness=readiness,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(app_module, "initialize_project_workspace", fake_init)

    with pytest.raises(SystemExit) as exc_info:
        app_module.init(engine="pytest")
    assert exc_info.value.code == 0
    assert forwarded == [("python", "pytest")]

    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    assert payload["data"]["pinned_engine"] == {
        "ecosystem": "python",
        "engine_name": "pytest",
    }


# ---------------------------------------------------------------------------
# D7 init failure envelopes
# ---------------------------------------------------------------------------


def test_init_no_engine_detected_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    outcome = InitNoEngineDetected(
        candidates=(
            DiscoveredCandidate(
                path="backend", ecosystem="python", engine_name="pytest"
            ),
            DiscoveredCandidate(
                path="services/api", ecosystem="go", engine_name="go-test"
            ),
        ),
        scan_refused=False,
    )

    async def fake_init(workspace: Path, *, engine: Any = None) -> Any:
        return outcome

    monkeypatch.setattr(app_module, "initialize_project_workspace", fake_init)

    with pytest.raises(SystemExit) as exc_info:
        app_module.init()
    assert exc_info.value.code == 4

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "no-engine-detected"
    assert payload["data"]["scan_refused"] is False
    assert payload["data"]["candidates"] == [
        {"path": "backend", "ecosystem": "python", "engine_name": "pytest"},
        {"path": "services/api", "ecosystem": "go", "engine_name": "go-test"},
    ]
    # The agent is instructed to cd into a candidate and init there itself.
    assert "cd into" in payload["errors"][0]["message"]


def test_init_scan_refused_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    async def fake_init(workspace: Path, *, engine: Any = None) -> Any:
        return InitNoEngineDetected(candidates=(), scan_refused=True)

    monkeypatch.setattr(app_module, "initialize_project_workspace", fake_init)

    with pytest.raises(SystemExit) as exc_info:
        app_module.init()
    assert exc_info.value.code == 4

    payload = _captured_envelope(capsys)
    assert payload["errors"][0]["code"] == "no-engine-detected"
    assert payload["data"] == {"candidates": [], "scan_refused": True}
    assert "refused" in payload["errors"][0]["message"]


def test_init_engine_ambiguous_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    outcome = InitEngineAmbiguous(
        candidates=(
            EngineCandidate(
                ecosystem="python", engine_name="pytest", evidence=("pyproject.toml",)
            ),
            EngineCandidate(
                ecosystem="go", engine_name="go-test", evidence=("go.mod",)
            ),
        )
    )

    async def fake_init(workspace: Path, *, engine: Any = None) -> Any:
        return outcome

    monkeypatch.setattr(app_module, "initialize_project_workspace", fake_init)

    with pytest.raises(SystemExit) as exc_info:
        app_module.init()
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["errors"][0]["code"] == "engine-ambiguous"
    assert payload["data"]["candidates"] == [
        {"path": ".", "ecosystem": "python", "engine_name": "pytest"},
        {"path": ".", "ecosystem": "go", "engine_name": "go-test"},
    ]
    assert "novetest init --engine" in payload["errors"][0]["message"]


# ---------------------------------------------------------------------------
# D6 migration ambiguity NO LONGER routes through the shared _require_store
# seam (S19 seam split; Gate-1 D1=A / D2=A, 2026-07-20)
# ---------------------------------------------------------------------------


def test_require_store_passes_legacy_unpinned_store_through_for_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S19 (D1=A): the shared ``_require_store`` seam no longer maps
    ``engine-ambiguous`` — ``resolve_workspace`` returns a legacy pin-less
    store as-is and every read verb receives it untouched (proceeds
    engine-less). The ambiguous-refusal moved to the EXECUTION path
    (``run`` / ``test`` via ``resolve_execution_engine`` →
    ``_map_execution_exception``), pinned in
    ``test_execution_exception_mapping.py``. This pins that the read seam
    passes the store straight through with no exit."""

    sentinel = object()

    async def fake_resolve(_cwd: Path) -> Any:
        # A legacy pin-less store is now returned as-is (post-S19 the seam
        # never raises EngineAmbiguousError on a read).
        return sentinel

    monkeypatch.setattr(app_module, "resolve_workspace", fake_resolve)

    assert app_module._require_store("status") is sentinel
