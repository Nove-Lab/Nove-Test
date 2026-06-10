#!/bin/sh
# install.sh — closes Phase 0 DoD bullets #3 (curl-pipe-sh end-to-end) and #4
# (SHA-256 verification + tampered-binary integration test).
#
# Canonical user invocation (per decisions/2026-05-14-install-script-hosting-url.md):
#   curl -fsSL https://ailovestesting.com/novetest/install.sh | sh
#
# This script is POSIX sh — verified on dash (Debian /bin/sh), ash (Alpine),
# and bash 3.2 (the default macOS interpreter). No bashisms. No `set -o
# pipefail`. No `[[ ... ]]`. No arrays. Long lines are intentionally short
# so the inspect-first user can read it without wrapping.
#
# Override env vars (test harness + mirror operators + pinning):
#   NOVETEST_INSTALL_REPO       default: Nove-Lab/Nove-Test
#                               GitHub `owner/repo` for the default URL layout.
#   NOVETEST_INSTALL_VERSION    default: latest
#                               "latest" or a tag like "v0.1.0".
#   NOVETEST_INSTALL_BASE_URL   default: derived from REPO+VERSION
#                               When set explicitly, the URL becomes
#                               ${BASE_URL}/${VERSION}/${asset}. Used by the
#                               integration tests that serve fixtures on
#                               localhost.
#   NOVETEST_INSTALL_PREFIX     default: ${HOME}/.local/bin
#
# Idempotent: re-running upgrades the binary in place via rename(2).
# On SHA-256 mismatch the install aborts loudly and writes nothing under
# $NOVETEST_INSTALL_PREFIX.

set -eu

# --- helpers ------------------------------------------------------------------

err() {
  printf 'error: %s\n' "$*" >&2
}

die() {
  err "$*"
  exit 1
}

info() {
  printf '%s\n' "$*"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

# --- detect OS and arch -------------------------------------------------------

detect_target() {
  _os="$(uname -s 2>/dev/null || echo unknown)"
  _arch="$(uname -m 2>/dev/null || echo unknown)"

  case "$_os" in
    Linux)  _os_id="linux" ;;
    Darwin) _os_id="macos" ;;
    *) die "unsupported OS: ${_os} (Phase 0 supports linux, macos; Windows is post-MVP via install.ps1)" ;;
  esac

  # macOS ships a single universal2 fat binary that runs on both Apple
  # Silicon and Intel — macOS picks the right Mach-O slice at exec time,
  # so install.sh has nothing to branch on for arch. Upstream artifact
  # name in release-test.yml: `novetest-macos-universal2`. Linux still
  # ships one binary per architecture.
  if [ "${_os_id}" = "macos" ]; then
    _arch_id="universal2"
  else
    case "$_arch" in
      x86_64|amd64)   _arch_id="x86_64" ;;
      aarch64|arm64)  _arch_id="aarch64" ;;
      *) die "unsupported arch: ${_arch} (Phase 0 Linux supports x86_64, aarch64/arm64; macOS ships universal2)" ;;
    esac
  fi

  printf '%s-%s' "${_os_id}" "${_arch_id}"
}

# --- compose download URLs ----------------------------------------------------

compose_urls() {
  _asset="$1"
  if [ -n "${BASE_URL_EXPLICIT}" ]; then
    binary_url="${NOVETEST_INSTALL_BASE_URL}/${VERSION}/${_asset}"
  elif [ "${VERSION}" = "latest" ]; then
    binary_url="https://github.com/${REPO}/releases/latest/download/${_asset}"
  else
    binary_url="https://github.com/${REPO}/releases/download/${VERSION}/${_asset}"
  fi
  sha_url="${binary_url}.sha256"
}

# --- sha256 -------------------------------------------------------------------

sha256_compute() {
  # Print hex digest of file $1 on stdout.
  if have sha256sum; then
    sha256sum "$1" | awk '{print $1}'
  elif have shasum; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif have openssl; then
    # `openssl dgst -sha256 file` prints "SHA256(file)= <hex>"; field $NF
    # is the hex regardless of the prefix shape.
    openssl dgst -sha256 "$1" | awk '{print $NF}'
  else
    die "no SHA-256 tool found (need one of: sha256sum, shasum, openssl)"
  fi
}

sha256_extract_expected() {
  # `sha256sum` / `shasum -a 256` write `<hex>  <filename>` (two spaces).
  # The first whitespace-delimited field is the digest; tolerate either
  # form by taking the first record's first column.
  awk '{print $1; exit}' "$1"
}

# --- download -----------------------------------------------------------------

download() {
  _url="$1"
  _out="$2"
  if have curl; then
    curl -fsSL --retry 3 -o "${_out}" "${_url}"
  elif have wget; then
    wget -q --tries=3 -O "${_out}" "${_url}"
  else
    die "no downloader found (need curl or wget)"
  fi
}

# --- PATH hint ----------------------------------------------------------------

print_path_hint_if_needed() {
  case ":${PATH}:" in
    *":${PREFIX}:"*) ;;
    *)
      info ""
      info "Note: ${PREFIX} is not on your PATH."
      info "      Add this line to your shell profile:"
      info ""
      info "        export PATH=\"${PREFIX}:\$PATH\""
      info ""
      ;;
  esac
}

# --- main ---------------------------------------------------------------------

main() {
  REPO="${NOVETEST_INSTALL_REPO:-Nove-Lab/Nove-Test}"
  VERSION="${NOVETEST_INSTALL_VERSION:-latest}"
  PREFIX="${NOVETEST_INSTALL_PREFIX:-${HOME}/.local/bin}"

  # We need to know whether the user *explicitly set* BASE_URL (vs. it being
  # unset and us defaulting), because that flips the URL layout. POSIX sh
  # supports `${var+x}` which expands to "x" iff $var is set (even to empty).
  if [ "${NOVETEST_INSTALL_BASE_URL+x}" = "x" ]; then
    BASE_URL_EXPLICIT="1"
  else
    BASE_URL_EXPLICIT=""
    NOVETEST_INSTALL_BASE_URL=""
  fi

  target="$(detect_target)"
  asset="novetest-${target}"

  compose_urls "${asset}"

  info "Installing novetest (${target}, ${VERSION}) into ${PREFIX}"
  info "  binary: ${binary_url}"
  info "  sha256: ${sha_url}"

  tmpdir="$(mktemp -d)" || die "mktemp -d failed"
  # POSIX trap; runs on normal exit and on common signals.
  trap 'rm -rf "${tmpdir}"' EXIT
  trap 'rm -rf "${tmpdir}"; exit 130' INT
  trap 'rm -rf "${tmpdir}"; exit 143' TERM

  download "${binary_url}" "${tmpdir}/${asset}"
  download "${sha_url}"    "${tmpdir}/${asset}.sha256"

  expected="$(sha256_extract_expected "${tmpdir}/${asset}.sha256")"
  if [ -z "${expected}" ]; then
    die "sha256 sidecar is empty: ${sha_url}"
  fi
  actual="$(sha256_compute "${tmpdir}/${asset}")"

  if [ "${expected}" != "${actual}" ]; then
    # LOUD abort per Phase 0 DoD bullet #4. Do NOT install.
    err ""
    err "================================================================="
    err "  SHA-256 MISMATCH — refusing to install ${asset}."
    err "-----------------------------------------------------------------"
    err "  expected:  ${expected}"
    err "  actual:    ${actual}"
    err "  source:    ${binary_url}"
    err "  sidecar:   ${sha_url}"
    err ""
    err "  This means the binary you would have installed does NOT match"
    err "  the published checksum. Possible causes: a corrupted download,"
    err "  a man-in-the-middle, or a tampered mirror. Nothing has been"
    err "  written to ${PREFIX}."
    err "================================================================="
    exit 1
  fi

  info "SHA-256 verified (${actual})."

  mkdir -p "${PREFIX}"
  install_path="${PREFIX}/novetest"
  # Stage under a sibling temp name first, then rename(2) into place. On the
  # same filesystem this is atomic — concurrent readers either see the old
  # binary or the new one, never a half-written executable.
  cp "${tmpdir}/${asset}" "${install_path}.tmp"
  chmod 0755 "${install_path}.tmp"
  mv "${install_path}.tmp" "${install_path}"

  info "Installed: ${install_path}"
  print_path_hint_if_needed
  info "Run 'novetest --version' to verify."
}

main "$@"
