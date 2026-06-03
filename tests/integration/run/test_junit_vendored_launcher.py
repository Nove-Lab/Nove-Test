"""Integration test: vendored JUnit Console Launcher resolves and runs.

This is the **R4 mitigation test** named in the Phase 2.5 JUnit adapter
task brief §8: the load-bearing pin that ``importlib.resources`` can
resolve the vendored jar AND that ``java -jar <jar> --version``
succeeds in the test environment. R4 is the medium-severity risk per
``decisions/2026-06-03-junit-console-launcher-vendor.md`` — PyApp binary
blob extraction has not been exercised in prior cycles (only Python
source files have).

What this test pins (vs what Release team's smoke pins later):

- This test runs under regular ``uv run pytest`` against the source
  tree on disk. It validates the ``importlib.resources`` resolution
  contract + the SHA-256 pin round-trip + (if a JVM is available) the
  ``java -jar <jar> --version`` smoke. It does NOT validate PyApp
  binary blob extraction across the three target platforms (Linux
  x86_64, Linux aarch64, macOS universal2) — that is the Release team's
  smoke at handoff time, per the decision §1 R4 mitigation contract.

- The ``java -jar`` smoke is skip-gated via ``shutil.which("java")`` so
  the test runs even on hosts without a JDK installed (per the
  polyglot-host-parity contract:
  ``decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md``). The
  ``importlib.resources`` + SHA-256 portion runs unconditionally — it
  needs only the stdlib.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import shutil
import subprocess

import pytest

from novetest.run.adapters._vendor import (
    LAUNCHER_JAR_FILENAME,
    LAUNCHER_JAR_SHA256,
    LAUNCHER_VERSION,
)


_VENDOR_PACKAGE = "novetest.run.adapters._vendor"


def test_importlib_resources_resolves_vendored_jar() -> None:
    """The vendored jar is reachable via ``importlib.resources.files`` and the
    SHA-256 of its on-disk bytes matches the pinned constant.

    Critically, this is the resolution path the adapter uses at runtime
    (NOT a ``Path(__file__).parent`` fallback) — exercising it from a
    test gives us a real signal about whether the file would be
    extractable inside a PyApp binary. The
    ``importlib.resources.as_file`` context manager is the API that
    transparently extracts a zipapp / PyApp resource to a temporary
    file system path; the adapter relies on the same idiom.
    """

    vendor = importlib.resources.files(_VENDOR_PACKAGE)
    jar_resource = vendor.joinpath(LAUNCHER_JAR_FILENAME)
    with importlib.resources.as_file(jar_resource) as jar_path:
        assert jar_path.is_file(), f"vendored jar missing at {jar_path}"
        # The Console Launcher 1.11.4 jar is ~2.8 MB. The brief §8.1
        # specifies a "> 1 MB sanity check" as a smoke against the
        # accidental commit of an empty / truncated jar. We keep the
        # threshold there even though the actual size is larger.
        size = jar_path.stat().st_size
        assert size > 1_000_000, (
            f"vendored jar at {jar_path} is suspiciously small: {size} bytes"
        )

        digest = hashlib.sha256(jar_path.read_bytes()).hexdigest()
        assert digest == LAUNCHER_JAR_SHA256, (
            f"SHA-256 of vendored jar at {jar_path} ({digest!r}) does not "
            f"match the pin LAUNCHER_JAR_SHA256 ({LAUNCHER_JAR_SHA256!r}). "
            "Either the jar was corrupted on disk, or the jar was bumped "
            "without updating the pin in "
            f"src/{_VENDOR_PACKAGE.replace('.', '/')}/__init__.py."
        )


def test_java_can_execute_vendored_jar() -> None:
    """``java -jar <vendored_jar> --version`` exits 0 with ``JUnit Platform``
    in the output.

    Skip-gated on ``java`` PATH presence so the test runs even on a
    JDK-less host. When the host IS equipped (per
    ``scripts/dev-host-setup.md §5``), this test validates the
    end-to-end "JVM can load and execute the vendored jar" smoke —
    which transitively validates the Console Launcher 1.11.4 / JDK 17+
    bytecode compatibility floor pinned in
    ``decisions/2026-05-25-supported-engine-matrix.md``.
    """

    java_path = shutil.which("java")
    if java_path is None:
        pytest.skip(
            "no `java` on PATH; install JDK 17+ per scripts/dev-host-setup.md §5"
        )

    vendor = importlib.resources.files(_VENDOR_PACKAGE)
    jar_resource = vendor.joinpath(LAUNCHER_JAR_FILENAME)
    with importlib.resources.as_file(jar_resource) as jar_path:
        result = subprocess.run(
            [java_path, "-jar", str(jar_path), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    assert result.returncode == 0, (
        f"`java -jar {jar_path} --version` exited {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "JUnit Platform" in combined, (
        f"`java -jar {jar_path} --version` ran but output did not include "
        f"`JUnit Platform`; full output={combined!r}. "
        "If this fails, the vendored jar may have been replaced with an "
        "unexpected upstream artifact — re-verify the SHA-256 pin against "
        "Maven Central."
    )
    # Also smoke-check that the surfaced version matches the pinned
    # constant. The Console Launcher --version output starts with the
    # JUnit Platform header followed by the version (e.g.
    # "JUnit Platform Console Launcher 1.11.4"). Looking for the bare
    # version substring is the cheapest robust check.
    assert LAUNCHER_VERSION in combined, (
        f"Console Launcher --version output does not mention pinned version "
        f"{LAUNCHER_VERSION!r}; output={combined!r}"
    )
