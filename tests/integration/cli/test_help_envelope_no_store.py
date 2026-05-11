from __future__ import annotations


def test_help_envelope_shape_in_clean_dir(run_cli) -> None:
    result = run_cli(["--help", "--output", "json"])
    assert result.returncode == 0, result.stderr

    envelope = result.envelope()
    assert envelope["schema"] == "novetest/v1"
    assert envelope["command"] == "help"
    assert envelope["ok"] is True

    data = envelope["data"]
    assert data["schemaVersion"] == 1
    onboarding_names = {entry["name"] for entry in data["onboarding"]}
    assert {"novetest --version", "novetest --help", "novetest init"} <= onboarding_names

    operating_names = {entry["name"] for entry in data["operating"]}
    for required in (
        "novetest test",
        "novetest run",
        "novetest memory list",
        "novetest inspect",
        "novetest status",
    ):
        assert required in operating_names


def test_help_envelope_snapshot(run_cli, snapshot) -> None:
    result = run_cli(["--help", "--output", "json"])
    assert result.returncode == 0, result.stderr
    assert result.envelope() == snapshot


def test_help_short_flag(run_cli) -> None:
    result = run_cli(["-h", "--output", "json"])
    assert result.returncode == 0, result.stderr
    assert result.envelope()["command"] == "help"
