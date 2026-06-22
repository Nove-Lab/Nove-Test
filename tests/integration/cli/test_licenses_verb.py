"""End-to-end ``novetest licenses`` verb tests via real subprocesses.

Exercises the full transport: argv → output-mode resolution → verb routing
(the verb must NOT be hijacked by the default-verb alias into ``test
licenses``) → orchestration assembly → envelope → renderer. JSON asserts the
machine contract; TEXT asserts the human surface; one ``.ambr`` snapshot pins
the default text block (the ``--full`` body is 15 KB and is covered by
substring assertions, not snapshotted, per the brief).
"""

from __future__ import annotations

import pytest


def test_novetest_licenses_default_envelope_json(run_cli) -> None:
    result = run_cli(["licenses", "--output", "json"])
    assert result.returncode == 0, result.stderr

    envelope = result.envelope()
    assert envelope["schema"] == "novetest/v1"
    assert envelope["command"] == "licenses"
    assert envelope["ok"] is True

    data = envelope["data"]
    assert len(data["licenses"]) == 5
    assert "notices_text" not in data
    assert data["summary"] == "Nove Test redistributes or links to 5 third-party components."


def test_novetest_licenses_full_envelope_json(run_cli) -> None:
    result = run_cli(["licenses", "--full", "--output", "json"])
    assert result.returncode == 0, result.stderr

    data = result.envelope()["data"]
    assert data["notices_text"].startswith("# Third-Party Notices\n")
    assert len(data["notices_text"]) > 15000


def test_novetest_licenses_text_mode_summary(run_cli) -> None:
    result = run_cli(["licenses", "--output", "text"])
    assert result.returncode == 0, result.stderr

    out = result.stdout
    assert not out.lstrip().startswith("{")  # not the pre-renderer JSON dump
    assert "licenses (5 third-party components)" in out
    assert "cyclopts (>=3.0)" in out
    assert "Apache-2.0" in out
    assert "PyApp (0.22.0)" in out


def test_novetest_licenses_full_text_mode_includes_verbatim(run_cli) -> None:
    result = run_cli(["licenses", "--full", "--output", "text"])
    assert result.returncode == 0, result.stderr

    out = result.stdout
    assert "--- VERBATIM NOTICES.md ---" in out
    # Drawn from the verbatim Apache 2.0 license body inlined in NOTICES.md.
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in out


def test_novetest_licenses_default_text_snapshot(run_cli, snapshot) -> None:
    result = run_cli(["licenses", "--output", "text"])
    assert result.returncode == 0, result.stderr
    assert result.stdout == snapshot


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
