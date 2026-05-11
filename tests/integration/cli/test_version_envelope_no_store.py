from __future__ import annotations

import re

_ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def test_version_envelope_shape_in_clean_dir(run_cli) -> None:
    result = run_cli(["--version", "--output", "json"])
    assert result.returncode == 0, result.stderr

    envelope = result.envelope()
    assert envelope["schema"] == "novetest/v1"
    assert envelope["command"] == "version"
    assert envelope["ok"] is True
    assert envelope["errors"] == []
    assert envelope["warnings"] == []

    data = envelope["data"]
    assert isinstance(data, dict)
    assert set(data) == {
        "installedVersion",
        "commandName",
        "installLocation",
        "pythonVersion",
        "platform",
        "verifiedAt",
    }
    assert data["commandName"] == "novetest"
    assert _ISO_UTC.match(data["verifiedAt"])


def test_version_short_flag(run_cli) -> None:
    result = run_cli(["-v", "--output", "json"])
    assert result.returncode == 0, result.stderr
    assert result.envelope()["command"] == "version"


def test_version_ndjson_is_single_line(run_cli) -> None:
    result = run_cli(["--version", "--output", "ndjson"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("\n") == 1
    assert result.stdout.endswith("\n")


def test_version_via_env_var(run_cli) -> None:
    result = run_cli(["--version"], env_overrides={"NOVETEST_OUTPUT": "ndjson"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("\n") == 1
