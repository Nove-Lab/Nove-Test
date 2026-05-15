"""Integration tests for `scripts/install.sh`.

Closes the test half of Phase 0 DoD bullet #4: the install script verifies
SHA-256 and aborts loudly on mismatch, covered by an integration test that
intentionally serves a tampered binary.

These tests are deliberately *not* in the default ``[tool.pytest.ini_options]
.testpaths`` (which is ``tests/unit`` + ``tests/integration``); CI invokes them
as a separate step on Linux + macOS only. Windows is skipped — the install
script targets POSIX sh and Windows parity ships later via ``install.ps1``.

The tests run install.sh against a localhost ``http.server`` serving fixture
binaries. They never touch the real GitHub release or the user's
``~/.local/bin``; everything stays under ``tmp_path``.
"""

from __future__ import annotations

import hashlib
import http.server
import platform
import socket
import socketserver
import subprocess
import sys
import threading
from pathlib import Path
from typing import Iterator

import pytest

# Skip the whole module on Windows. /bin/sh isn't there, and Phase 0 scope
# explicitly excludes Windows from the install-script path (foundations §7).
pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="install.sh is POSIX sh; Windows parity ships post-MVP via install.ps1",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install.sh"
ASSET_VERSION = "dev"  # arbitrary path segment; mirrors release-test.yml e2e job


def _detect_target() -> str:
    """Compute the binary asset name install.sh will request on this host.

    Mirrors the case logic in ``scripts/install.sh::detect_target``. If the
    host platform is outside Phase 0 scope, the test is skipped — the install
    script would refuse to run anyway and there is nothing to assert.
    """
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Linux":
        os_id = "linux"
    elif system == "Darwin":
        os_id = "macos"
    else:
        pytest.skip(f"install.sh does not target {system!r}")

    if machine in ("x86_64", "amd64"):
        arch_id = "x86_64"
    elif machine in ("aarch64", "arm64"):
        arch_id = "aarch64"
    else:
        pytest.skip(f"install.sh does not target arch {machine!r}")

    if os_id == "macos" and arch_id == "aarch64":
        arch_id = "arm64"

    return f"{os_id}-{arch_id}"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler that doesn't spam stderr during tests."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return  # silence


@pytest.fixture
def http_root(tmp_path: Path) -> Path:
    """Document root for the localhost HTTP fixture server."""
    root = tmp_path / "www"
    (root / ASSET_VERSION).mkdir(parents=True)
    return root


@pytest.fixture
def http_server(http_root: Path) -> Iterator[str]:
    """Spin up a localhost HTTP server rooted at ``http_root``.

    Yields the base URL (``http://127.0.0.1:<port>``). Stops the server on
    teardown. Uses port 0 so concurrent test processes don't collide.
    """

    class _Server(socketserver.TCPServer):
        allow_reuse_address = True

        def finish_request(self, request: object, client_address: object) -> None:
            # Pin the handler's working directory to http_root so relative
            # asset paths resolve under our fixture, not the test's CWD.
            self.RequestHandlerClass(
                request,  # type: ignore[arg-type]
                client_address,  # type: ignore[arg-type]
                self,
                directory=str(http_root),  # type: ignore[call-arg]
            )

    # Bind to port 0 to let the OS allocate a free port.
    with _Server(("127.0.0.1", 0), _QuietHandler) as server:
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.shutdown()
            thread.join(timeout=2.0)


def _wait_for_port_open(host: str, port: int, timeout: float = 2.0) -> None:
    """Block briefly until the HTTP fixture starts accepting connections."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"http server at {host}:{port} did not come up in {timeout}s")


def _write_asset(
    *,
    http_root: Path,
    target: str,
    binary_bytes: bytes,
    sidecar_digest: str | None = None,
) -> None:
    """Place a fixture binary and its .sha256 sidecar under the served root.

    If ``sidecar_digest`` is None, the sidecar carries the *correct* digest of
    ``binary_bytes`` (happy path). Pass an explicit (wrong) hex digest to
    simulate a tampered mirror.
    """
    asset = f"novetest-{target}"
    bin_path = http_root / ASSET_VERSION / asset
    sha_path = http_root / ASSET_VERSION / f"{asset}.sha256"

    bin_path.write_bytes(binary_bytes)
    if sidecar_digest is None:
        sidecar_digest = hashlib.sha256(binary_bytes).hexdigest()
    # Match the `<hex>  <filename>` shape that sha256sum / shasum -a 256 emit.
    sha_path.write_text(f"{sidecar_digest}  {asset}\n")


def _run_install_script(
    *,
    base_url: str,
    prefix: Path,
) -> subprocess.CompletedProcess[str]:
    """Invoke install.sh with the test overrides; never the real network."""
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",  # minimal PATH; let `sh` find tools
        "HOME": str(prefix.parent),  # prevent default ~/.local/bin contamination
        "NOVETEST_INSTALL_BASE_URL": base_url,
        "NOVETEST_INSTALL_VERSION": ASSET_VERSION,
        "NOVETEST_INSTALL_PREFIX": str(prefix),
    }
    return subprocess.run(
        ["sh", str(INSTALL_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


# --- happy path ---------------------------------------------------------------


def test_install_succeeds_when_sha256_matches(
    tmp_path: Path,
    http_root: Path,
    http_server: str,
) -> None:
    """SHA-256 verified → binary installed at PREFIX, exit code 0."""
    target = _detect_target()
    fake_binary = b"#!/bin/sh\necho 'stub novetest 0.0.0'\n"
    _write_asset(http_root=http_root, target=target, binary_bytes=fake_binary)

    host_port = http_server.removeprefix("http://").split(":")
    _wait_for_port_open(host_port[0], int(host_port[1]))

    prefix = tmp_path / "prefix"
    result = _run_install_script(base_url=http_server, prefix=prefix)

    assert result.returncode == 0, (
        f"install.sh failed: rc={result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    installed = prefix / "novetest"
    assert installed.is_file(), f"binary not installed at {installed}"
    assert installed.read_bytes() == fake_binary
    # Executable bit set (chmod 0755 in the script).
    assert installed.stat().st_mode & 0o111, "installed binary is not executable"
    assert "SHA-256 verified" in result.stdout


def test_install_is_idempotent_on_rerun(
    tmp_path: Path,
    http_root: Path,
    http_server: str,
) -> None:
    """Re-running upgrades in place: same binary, same SHA, exit code 0 twice."""
    target = _detect_target()
    fake_binary = b"#!/bin/sh\necho 'stub novetest 0.0.0'\n"
    _write_asset(http_root=http_root, target=target, binary_bytes=fake_binary)

    host_port = http_server.removeprefix("http://").split(":")
    _wait_for_port_open(host_port[0], int(host_port[1]))

    prefix = tmp_path / "prefix"
    first = _run_install_script(base_url=http_server, prefix=prefix)
    second = _run_install_script(base_url=http_server, prefix=prefix)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (prefix / "novetest").read_bytes() == fake_binary


# --- tampered-binary path (the DoD-mandated test) -----------------------------


def test_install_aborts_loudly_when_sha256_mismatches(
    tmp_path: Path,
    http_root: Path,
    http_server: str,
) -> None:
    """Tampered binary → loud abort, non-zero exit, NOTHING written to PREFIX.

    This is the integration test mandated by Phase 0 DoD bullet #4. The fixture
    serves a binary whose bytes do NOT match the published .sha256 sidecar
    (simulating a corrupted download or a tampered mirror). install.sh must
    detect the mismatch and refuse to install.
    """
    target = _detect_target()
    real_binary = b"#!/bin/sh\necho 'real novetest'\n"
    # Sidecar advertises a digest that is valid hex but does not match
    # `real_binary`'s actual SHA-256. install.sh should compare and abort.
    wrong_digest = "0" * 64
    _write_asset(
        http_root=http_root,
        target=target,
        binary_bytes=real_binary,
        sidecar_digest=wrong_digest,
    )

    host_port = http_server.removeprefix("http://").split(":")
    _wait_for_port_open(host_port[0], int(host_port[1]))

    prefix = tmp_path / "prefix"
    result = _run_install_script(base_url=http_server, prefix=prefix)

    # Exit code: non-zero (the script uses `exit 1` for SHA mismatch).
    assert result.returncode != 0, (
        f"install.sh unexpectedly succeeded with mismatched SHA-256.\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    # "Loud" — the abort message names SHA-256 explicitly on stderr.
    assert "SHA-256 MISMATCH" in result.stderr, (
        f"abort message missing 'SHA-256 MISMATCH':\n{result.stderr}"
    )
    # The expected and actual digests are both surfaced.
    assert wrong_digest in result.stderr
    actual_digest = hashlib.sha256(real_binary).hexdigest()
    assert actual_digest in result.stderr
    # And — critically — nothing was installed under the prefix.
    installed = prefix / "novetest"
    assert not installed.exists(), (
        f"install.sh wrote {installed} despite SHA mismatch — DoD violation"
    )
