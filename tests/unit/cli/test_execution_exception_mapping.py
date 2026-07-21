"""W2/S17 execution exception-mapping dedup (ORC-02 + ORC-21).

``run_cmd`` and ``test_cmd`` used to carry a verbatim-duplicated three-block
``except`` tree (EngineAmbiguous / EngineNotReady / AdapterInvocation) with
identical envelope construction, error codes, and exit codes. S17 collapses
both copies into the single ``cli/app.py::_map_execution_exception`` helper and
adds a structural fallback (ORC-21) so a NEW ``RunEngineError`` subclass cannot
fall through to the generic exit-1 ``cli-error`` handler and lose its verb name
/ structured exit.

Two guarantees are pinned here:

- **Behavior preservation (ORC-02).** For each of the previously-mapped
  exceptions the shared helper's ``(Envelope, exit)`` is byte-identical — on
  BOTH ``run`` and ``test`` — to the pre-S17 inlined block, with ONE
  intentional carve-out: ``adapter-invalid-target``'s exit code was
  reclassified 4 → 2 (usage error) per the 2026-07-09 decision, so it is
  pinned separately (``test_invalid_target_reclassified_to_usage_exit``) and
  excluded from the byte-identical oracle set (``_PRE_S17_IDS``). The oracle is
  a verbatim replica of that old inline construction (``_old_inline_mapping``),
  holding the shared projection helpers constant, which is exactly the right
  scope for a behavior-preserving refactor proof (helper-internal correctness
  is covered by the ORC-03/ORC-23 pins in
  ``test_exit_error_code_contract.py``). Load-bearing wire tokens (command,
  error code, exit) also get literal assertions independent of the oracle.
- **ORC-21 structural fallback.** A fabricated new ``RunEngineError`` subclass
  (and the real, today-unreachable ``EngineNotSupportedError``) maps to a
  structured ``engine-not-supported`` envelope at exit 4 (``EXIT_ENGINE_MISSING``)
  carrying the verb name — NOT the generic exit-1 ``cli-error`` fall-through.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from novetest.cli import _shared
from novetest.cli import app as app_module
from novetest.cli.app import (
    _engine_candidates_payload,
    _engine_not_ready_code,
    _map_execution_exception,
    _readiness_payload,
)
from novetest.cli.handlers import run as run_handler
from novetest.cli.handlers import test as test_handler
from novetest.cli.output import (
    EXIT_ENGINE_MISSING,
    EXIT_GENERIC,
    EXIT_USAGE,
    Envelope,
    EnvelopeError,
    OutputMode,
)
from novetest.orchestration.anchor_resolution import (
    EngineAmbiguousError,
    WorkspaceEngineUndetectedError,
)
from novetest.orchestration.workflows.run import RunOutcome
from novetest.orchestration.workflows.test import TestOutcome
from novetest.run import (
    AdapterInvocationError,
    EngineCandidate,
    EngineNotReadyError,
    EngineNotSupportedError,
    EngineReadinessResult,
    NativeEngineContext,
    RunEngineError,
)


# ---------------------------------------------------------------------------
# Exception fixtures
# ---------------------------------------------------------------------------


def _readiness(state: str, *, with_context: bool) -> EngineReadinessResult:
    return EngineReadinessResult(
        state=state,
        engine_context=(
            NativeEngineContext(ecosystem="python", engine_name="pytest")
            if with_context
            else None
        ),
        evidence=("marker: pyproject.toml",),
        issues=("stubbed readiness issue",),
    )


def _ambiguous() -> EngineAmbiguousError:
    return EngineAmbiguousError(
        (
            EngineCandidate(ecosystem="python", engine_name="pytest"),
            EngineCandidate(ecosystem="javascript", engine_name="jest"),
        )
    )


class _FabricatedRunEngineError(RunEngineError):
    """A brand-new RunEngineError subclass with no dedicated ``except`` branch.

    Stands in for a hypothetical future member of the family so the ORC-21
    structural fallback is exercised without waiting for a real one to exist.
    """


# Every exception the helper maps, keyed by a readable id. The three
# EngineAmbiguous / EngineNotReady / AdapterInvocation families were mapped by
# the pre-S17 inline blocks; ``fallback-*`` are the ORC-21 additions.
_MAPPED_EXCEPTIONS: dict[str, RunEngineError | EngineAmbiguousError] = {
    "ambiguous": _ambiguous(),
    "not-ready-missing": EngineNotReadyError(
        _readiness("engine-missing", with_context=False)
    ),
    "not-ready-misconfigured": EngineNotReadyError(
        _readiness("engine-misconfigured", with_context=True)
    ),
    "markerless-undetected": WorkspaceEngineUndetectedError(
        _readiness("engine-missing", with_context=False)
    ),
    "adapter-with-hint": AdapterInvocationError(
        "cargo-nextest is not installed",
        kind="missing-engine",
        install_hint="cargo install cargo-nextest",
    ),
    "adapter-no-hint": AdapterInvocationError(
        "target expression would be consumed as a flag",
        kind="invalid-target",
    ),
}

# The families that map byte-identically to the pre-S17 inline block — the
# behavior-preservation set. ``adapter-no-hint`` (kind ``invalid-target``) is
# DELIBERATELY absent: its exit code was reclassified 4 → 2 by the 2026-07-09
# decision, so it no longer equals the old inline block and is pinned on its
# own (``test_invalid_target_reclassified_to_usage_exit``). Every OTHER adapter
# kind still maps byte-identically, so ``adapter-with-hint`` stays here.
_PRE_S17_IDS = [
    "ambiguous",
    "not-ready-missing",
    "not-ready-misconfigured",
    "markerless-undetected",
    "adapter-with-hint",
]


# ---------------------------------------------------------------------------
# Behavior-preservation oracle: a verbatim replica of the pre-S17 inline block
# ---------------------------------------------------------------------------


def _old_inline_mapping(command: str, exc: Exception) -> tuple[Envelope, int]:
    """Verbatim copy of the pre-S17 inlined three-block ``except`` tree.

    Identical on ``run_cmd`` and ``test_cmd`` modulo ``command=`` (that copy-
    paste symmetry is precisely what ORC-02 dedups). ``_map_execution_exception``
    must equal this for every exception in ``_PRE_S17_IDS``. It INTENTIONALLY
    diverges for ``kind == "invalid-target"``: this oracle preserves the old
    exit-4 mapping (as pre-S17 emitted), while the live helper now returns exit 2
    per the 2026-07-09 reclassification — so ``adapter-no-hint`` is excluded from
    the byte-identical set and pinned separately.
    """
    if isinstance(exc, EngineAmbiguousError):
        return (
            Envelope(
                command=command,
                ok=False,
                data={"candidates": _engine_candidates_payload(exc.candidates)},
                errors=(EnvelopeError(code="engine-ambiguous", message=str(exc)),),
            ),
            EXIT_USAGE,
        )
    if isinstance(exc, EngineNotReadyError):
        return (
            Envelope(
                command=command,
                ok=False,
                data={"engine_readiness": _readiness_payload(exc.readiness)},
                errors=(
                    EnvelopeError(
                        code=_engine_not_ready_code(exc),
                        message=str(exc),
                    ),
                ),
            ),
            EXIT_ENGINE_MISSING,
        )
    if isinstance(exc, AdapterInvocationError):
        return (
            Envelope(
                command=command,
                ok=False,
                errors=(
                    EnvelopeError(
                        code=f"adapter-{exc.kind}",
                        message=str(exc),
                        details=(
                            {"install_hint": exc.install_hint}
                            if exc.install_hint is not None
                            else {}
                        ),
                    ),
                ),
            ),
            EXIT_ENGINE_MISSING,
        )
    raise AssertionError(f"{exc!r} was not mapped by the pre-S17 inline block")


# ---------------------------------------------------------------------------
# ORC-02 — the shared helper reproduces the pre-S17 shape byte-identically
# ---------------------------------------------------------------------------


class TestBehaviorPreservation:
    @pytest.mark.parametrize("command", ["run", "test"])
    @pytest.mark.parametrize("exc_id", _PRE_S17_IDS)
    def test_helper_matches_old_inline_block(
        self, command: str, exc_id: str
    ) -> None:
        exc = _MAPPED_EXCEPTIONS[exc_id]
        assert _map_execution_exception(command, exc) == _old_inline_mapping(
            command, exc
        )

    @pytest.mark.parametrize("exc_id", _PRE_S17_IDS)
    def test_run_and_test_differ_only_in_command_field(self, exc_id: str) -> None:
        """The two verbs emit the SAME shape modulo ``command`` — the exact
        symmetry ORC-02 collapses to one source."""
        exc = _MAPPED_EXCEPTIONS[exc_id]
        run_env, run_exit = _map_execution_exception("run", exc)
        test_env, test_exit = _map_execution_exception("test", exc)
        assert run_exit == test_exit
        assert run_env.command == "run"
        assert test_env.command == "test"
        # Rebasing the test envelope onto command="run" makes them identical.
        from dataclasses import replace

        assert replace(test_env, command="run") == run_env

    def test_ambiguous_wire_tokens(self) -> None:
        env, exit_code = _map_execution_exception("run", _MAPPED_EXCEPTIONS["ambiguous"])
        assert exit_code == EXIT_USAGE
        assert env.errors[0].code == "engine-ambiguous"
        assert env.data["candidates"] == [
            {"path": ".", "ecosystem": "python", "engine_name": "pytest"},
            {"path": ".", "ecosystem": "javascript", "engine_name": "jest"},
        ]

    @pytest.mark.parametrize(
        ("exc_id", "expected_code"),
        [
            ("not-ready-missing", "engine-missing"),
            ("not-ready-misconfigured", "engine-misconfigured"),
            ("markerless-undetected", "no-engine-detected"),
        ],
    )
    def test_not_ready_wire_tokens(self, exc_id: str, expected_code: str) -> None:
        env, exit_code = _map_execution_exception("test", _MAPPED_EXCEPTIONS[exc_id])
        assert exit_code == EXIT_ENGINE_MISSING
        assert env.errors[0].code == expected_code
        assert not env.errors[0].code.startswith("engine-engine-")
        assert "engine_readiness" in env.data

    def test_adapter_wire_tokens_and_hint_conditional(self) -> None:
        with_hint, hint_exit = _map_execution_exception(
            "run", _MAPPED_EXCEPTIONS["adapter-with-hint"]
        )
        assert hint_exit == EXIT_ENGINE_MISSING
        assert with_hint.errors[0].code == "adapter-missing-engine"
        assert with_hint.errors[0].details == {
            "install_hint": "cargo install cargo-nextest"
        }

        no_hint, no_hint_exit = _map_execution_exception(
            "run", _MAPPED_EXCEPTIONS["adapter-no-hint"]
        )
        assert no_hint.errors[0].code == "adapter-invalid-target"
        assert no_hint.errors[0].details == {}
        # invalid-target reclassified 4 → 2 (usage error); code string unchanged.
        assert no_hint_exit == EXIT_USAGE

    @pytest.mark.parametrize("command", ["run", "test"])
    def test_invalid_target_reclassified_to_usage_exit(self, command: str) -> None:
        """``adapter-invalid-target`` is the ONE adapter kind that intentionally
        diverges from the pre-S17 exit-4 mapping: a dash-/flag-/metachar-shaped
        target is a *caller* usage error → exit 2 (``EXIT_USAGE``), not the
        engine-missing class. The wire error-code STRING and envelope shape are
        UNCHANGED; only the exit code flips 4 → 2. Pinned on BOTH verbs.
        (``decisions/2026-07-09-adapter-invalid-target-exit-code-reclassification.md``)
        """
        env, exit_code = _map_execution_exception(
            command, _MAPPED_EXCEPTIONS["adapter-no-hint"]
        )
        assert (env.errors[0].code, exit_code) == (
            "adapter-invalid-target",
            EXIT_USAGE,
        )
        # Discriminating guard: EVERY OTHER AdapterInvocationError kind still
        # maps to exit 4, so a future regression that broadens the exit-2
        # carve-out (or flips it into a blanket adapter change) fails loudly.
        for other_kind in ("missing-engine", "unparseable-output", "timed-out"):
            _, other_exit = _map_execution_exception(
                command, AdapterInvocationError("boom", kind=other_kind)
            )
            assert other_exit == EXIT_ENGINE_MISSING, other_kind


# ---------------------------------------------------------------------------
# ORC-21 — structural fallback for the RunEngineError family
# ---------------------------------------------------------------------------


class TestOrc21Fallback:
    @pytest.mark.parametrize("command", ["run", "test"])
    def test_fabricated_subclass_maps_to_structured_engine_not_supported(
        self, command: str
    ) -> None:
        exc = _FabricatedRunEngineError("adapter for 'zig-test' not implemented yet")
        env, exit_code = _map_execution_exception(command, exc)
        assert exit_code == EXIT_ENGINE_MISSING
        assert exit_code != EXIT_GENERIC  # NOT the generic exit-1 fall-through
        assert env.command == command  # verb name preserved, not "cli"
        assert env.ok is False
        assert env.errors[0].code == "engine-not-supported"
        assert env.errors[0].message == "adapter for 'zig-test' not implemented yet"

    @pytest.mark.parametrize("command", ["run", "test"])
    def test_real_engine_not_supported_hits_the_fallback(self, command: str) -> None:
        """The real (today-unreachable) subclass also routes to the fallback —
        documents the ORC-21 correction target if a 7th engine ever lands in
        the supported matrix without an adapter branch."""
        env, exit_code = _map_execution_exception(
            command, EngineNotSupportedError("(js, deno) has no adapter")
        )
        assert (env.command, env.errors[0].code, exit_code) == (
            command,
            "engine-not-supported",
            EXIT_ENGINE_MISSING,
        )


# ---------------------------------------------------------------------------
# End-to-end through the real run_cmd / test_cmd handlers
# ---------------------------------------------------------------------------


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_shared, "_active_mode", OutputMode.JSON)


@pytest.fixture
def stub_store(monkeypatch: pytest.MonkeyPatch) -> object:
    sentinel = object()
    monkeypatch.setattr(run_handler, "_require_store", lambda _cmd: sentinel)
    monkeypatch.setattr(test_handler, "_require_store", lambda _cmd: sentinel)
    return sentinel


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    payload: dict[str, Any] = json.loads(out)
    return payload


def _patch_run_raise(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    async def fake_workflow(target: str, store: Any, **kwargs: Any) -> RunOutcome:
        raise exc

    monkeypatch.setattr(run_handler, "run_target_in_store", fake_workflow)


def _patch_test_raise(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    async def fake_workflow(target: str, store: Any, **kwargs: Any) -> TestOutcome:
        raise exc

    monkeypatch.setattr(test_handler, "test_target_in_store", fake_workflow)


class TestVerbsRouteThroughTheHelper:
    @pytest.mark.parametrize(
        ("exc_id", "expected_exit"),
        [
            ("ambiguous", EXIT_USAGE),
            ("not-ready-missing", EXIT_ENGINE_MISSING),
            ("markerless-undetected", EXIT_ENGINE_MISSING),
            ("adapter-with-hint", EXIT_ENGINE_MISSING),
            # invalid-target reclassified 4 → 2 (2026-07-09); proven end-to-end
            # through the real run_cmd handler, not just the helper.
            ("adapter-no-hint", EXIT_USAGE),
        ],
    )
    def test_run_verb_emits_helper_result(
        self,
        exc_id: str,
        expected_exit: int,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        exc = _MAPPED_EXCEPTIONS[exc_id]
        expected_env, _ = _map_execution_exception("run", exc)
        _patch_run_raise(monkeypatch, exc)
        with pytest.raises(SystemExit) as exc_info:
            app_module.run_cmd("")
        assert exc_info.value.code == expected_exit
        payload = _captured_envelope(capsys)
        assert payload == expected_env.to_dict()

    @pytest.mark.parametrize(
        ("exc_id", "expected_exit"),
        [
            ("ambiguous", EXIT_USAGE),
            ("not-ready-misconfigured", EXIT_ENGINE_MISSING),
            ("markerless-undetected", EXIT_ENGINE_MISSING),
            ("adapter-with-hint", EXIT_ENGINE_MISSING),
            # invalid-target reclassified 4 → 2 (2026-07-09); proven end-to-end
            # through the real test_cmd handler on BOTH verbs.
            ("adapter-no-hint", EXIT_USAGE),
        ],
    )
    def test_test_verb_emits_helper_result(
        self,
        exc_id: str,
        expected_exit: int,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        exc = _MAPPED_EXCEPTIONS[exc_id]
        expected_env, _ = _map_execution_exception("test", exc)
        _patch_test_raise(monkeypatch, exc)
        with pytest.raises(SystemExit) as exc_info:
            app_module.test_cmd("")
        assert exc_info.value.code == expected_exit
        payload = _captured_envelope(capsys)
        assert payload == expected_env.to_dict()

    def test_both_verbs_route_through_the_one_helper(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        """Monkeypatching the ONE helper redirects BOTH verbs — proof neither
        verb keeps a private copy of the mapping."""
        sentinel = (
            Envelope(
                command="sentinel-route",
                ok=False,
                errors=(EnvelopeError(code="sentinel", message="routed"),),
            ),
            99,
        )
        monkeypatch.setattr(
            _shared, "_map_execution_exception", lambda _cmd, _exc: sentinel
        )
        _patch_run_raise(monkeypatch, RunEngineError("boom"))
        _patch_test_raise(monkeypatch, RunEngineError("boom"))

        with pytest.raises(SystemExit) as run_exc:
            app_module.run_cmd("")
        assert run_exc.value.code == 99
        assert _captured_envelope(capsys)["command"] == "sentinel-route"

        with pytest.raises(SystemExit) as test_exc:
            app_module.test_cmd("")
        assert test_exc.value.code == 99
        assert _captured_envelope(capsys)["command"] == "sentinel-route"

    @pytest.mark.parametrize("verb", ["run", "test"])
    def test_fallback_subclass_does_not_fall_through_to_cli_error(
        self,
        verb: str,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        force_json_mode: None,
        stub_store: object,
    ) -> None:
        """A new RunEngineError subclass raised from the workflow reaches the
        structured ORC-21 fallback (exit 4, ``engine-not-supported``, verb
        name kept) instead of the generic exit-1 ``cli-error`` handler."""
        exc = _FabricatedRunEngineError("adapter for 'zig-test' not implemented yet")
        if verb == "run":
            _patch_run_raise(monkeypatch, exc)
            handler = app_module.run_cmd
        else:
            _patch_test_raise(monkeypatch, exc)
            handler = app_module.test_cmd

        with pytest.raises(SystemExit) as exc_info:
            handler("")
        assert exc_info.value.code == EXIT_ENGINE_MISSING
        payload = _captured_envelope(capsys)
        assert payload["command"] == verb
        assert payload["command"] != "cli"
        assert payload["errors"][0]["code"] == "engine-not-supported"
        assert payload["errors"][0]["code"] != "cli-error"
