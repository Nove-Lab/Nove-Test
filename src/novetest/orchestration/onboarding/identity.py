from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from novetest import __version__


@dataclass(slots=True, frozen=True)
class CLIIdentity:
    installed_version: str
    command_name: str
    install_location: str
    python_version: str
    platform: str
    verified_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "installedVersion": self.installed_version,
            "commandName": self.command_name,
            "installLocation": self.install_location,
            "pythonVersion": self.python_version,
            "platform": self.platform,
            "verifiedAt": self.verified_at,
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def report_cli_identity() -> CLIIdentity:
    return CLIIdentity(
        installed_version=__version__,
        command_name="novetest",
        install_location=sys.executable,
        python_version=sys.version.split()[0],
        platform=f"{platform.system().lower()}-{platform.machine().lower()}",
        verified_at=_utc_now_iso(),
    )
