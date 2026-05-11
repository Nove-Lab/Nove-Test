from __future__ import annotations

import re

from novetest.orchestration.onboarding.identity import CLIIdentity, report_cli_identity


_ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def test_identity_returns_dataclass() -> None:
    identity = report_cli_identity()
    assert isinstance(identity, CLIIdentity)
    assert identity.command_name == "novetest"
    assert identity.installed_version != ""
    assert identity.install_location != ""
    assert identity.python_version.count(".") == 2
    assert "-" in identity.platform


def test_identity_verified_at_is_iso_utc() -> None:
    identity = report_cli_identity()
    assert _ISO_UTC.match(identity.verified_at)


def test_identity_to_dict_uses_camel_case_keys() -> None:
    payload = report_cli_identity().to_dict()
    assert set(payload) == {
        "installedVersion",
        "commandName",
        "installLocation",
        "pythonVersion",
        "platform",
        "verifiedAt",
    }
