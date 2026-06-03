"""Vendored third-party assets shipped inside the Nove Test distribution.

The first vendored asset is the JUnit Platform Console Launcher
(Standalone) jar, per
``agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md``
(closes Open Question #5). Subsequent adapter slices that need vendored
helpers (e.g. a hypothetical JaCoCo CLI or Coverlet diagnostic helper)
follow this directory + ``THIRD_PARTY_NOTICES.txt`` + ``pyproject.toml``
include pattern.

**Runtime resolution.** Always go through
``importlib.resources.files(__name__).joinpath(<filename>)`` followed by
``importlib.resources.as_file(...)`` to obtain a filesystem `Path` that
survives PyApp single-binary extraction (R4 mitigation). DO NOT use
``Path(__file__).parent / "_vendor" / ...`` — that breaks under a
zipapp / PyApp deployment where the package source is not on a normal
filesystem.

**SHA-256 pin.** ``LAUNCHER_JAR_SHA256`` is captured from Maven Central
at slice-write time and re-verified against
``hashlib.sha256(<bytes>)`` in the R4 mitigation integration test
(`tests/integration/run/test_junit_vendored_launcher.py`). Future jar
bumps MUST update both this constant and the
``THIRD_PARTY_NOTICES.txt`` sibling in the same commit.

The downloaded ``.sha256`` sidecar at
``https://repo1.maven.org/maven2/org/junit/platform/
junit-platform-console-standalone/1.11.4/
junit-platform-console-standalone-1.11.4.jar.sha256`` returned the same
hex value at 2026-06-03 13:30 UTC; the local
``sha256sum junit-platform-console-standalone-1.11.4.jar`` matched
byte-identical. Both transcripts are reproduced in the slice handoff.
"""

from __future__ import annotations

from typing import Final

# Filename inside this directory. Pinned because the import-time
# ``importlib.resources`` resolution is by-name; bumping the version
# requires updating this constant AND `THIRD_PARTY_NOTICES.txt` AND the
# SHA-256 below — all three in the same commit.
LAUNCHER_JAR_FILENAME: Final[str] = "junit-platform-console-standalone-1.11.4.jar"

# Public version string. Used in `NativeResult.metadata` to surface the
# Console Launcher version on the persisted Run Record.
LAUNCHER_VERSION: Final[str] = "1.11.4"

# SHA-256 of the jar bytes — captured 2026-06-03 from Maven Central's
# ``.sha256`` sidecar at the URL embedded in `THIRD_PARTY_NOTICES.txt`.
# The R4 mitigation integration test re-verifies this at every test run
# so on-disk corruption (or an accidental jar bump that forgets to
# update the pin) surfaces immediately.
LAUNCHER_JAR_SHA256: Final[str] = (
    "b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc"
)


__all__ = [
    "LAUNCHER_JAR_FILENAME",
    "LAUNCHER_JAR_SHA256",
    "LAUNCHER_VERSION",
]
