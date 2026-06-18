# install.ps1 — Windows companion to scripts/install.sh.
#
# Canonical user invocation (per decisions/2026-05-14-install-script-hosting-url.md):
#   irm https://ailovestesting.com/novetest/install.ps1 | iex
# Interim per Amendment 2026-06-10 (until DNS routing is wired):
#   irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex
#
# This script is PowerShell 5.1 compatible — verified against Windows 10/11's
# default Windows PowerShell. No PowerShell 7-only syntax: no '??' null-
# coalescing, no '?.' safe-navigation, no '?:' ternary, no 'using namespace'.
#
# Override env vars (parallel to install.sh):
#   NOVETEST_INSTALL_REPO       default: Nove-Lab/Nove-Test
#                               GitHub `owner/repo` for the default URL layout.
#   NOVETEST_INSTALL_VERSION    default: latest
#                               "latest" or a tag like "v0.1.2".
#   NOVETEST_INSTALL_BASE_URL   default: derived from REPO+VERSION
#                               When set, the URL becomes
#                               ${BASE_URL}/${VERSION}/${asset}. Used by the
#                               integration tests that serve fixtures on
#                               localhost.
#   NOVETEST_INSTALL_PREFIX     default: $env:USERPROFILE\.local\bin
#                               Symmetric with install.sh's ~/.local/bin —
#                               AI-agent install hints land in the same shape
#                               on every OS.
#
# Idempotent: re-running upgrades the binary in place via Move-Item -Force.
# On SHA-256 mismatch the install aborts loudly and writes nothing under
# $NOVETEST_INSTALL_PREFIX.

$ErrorActionPreference = "Stop"

# --- helpers -----------------------------------------------------------------

function Write-Info {
    param([string]$Message = "")
    Write-Host $Message
}

function Resolve-EnvOrDefault {
    param(
        [string]$EnvName,
        [string]$Default
    )
    $value = [Environment]::GetEnvironmentVariable($EnvName, "Process")
    if ([string]::IsNullOrEmpty($value)) {
        return $Default
    }
    return $value
}

# --- detect target -----------------------------------------------------------

function Get-Target {
    # $env:PROCESSOR_ARCHITECTURE is set on every Windows install and survives
    # in 32-bit PowerShell hosts via PROCESSOR_ARCHITEW6432. Reading both lets
    # this script work even if launched from a 32-bit shell on a 64-bit OS.
    $arch  = $env:PROCESSOR_ARCHITECTURE
    $arch6 = $env:PROCESSOR_ARCHITEW6432
    if ($arch -eq "AMD64" -or $arch6 -eq "AMD64") {
        return "windows-x86_64"
    }
    if ($arch -eq "ARM64" -or $arch6 -eq "ARM64") {
        throw "unsupported Windows architecture: windows-arm64 (python-build-standalone gap; see foundations.md §54). This cycle ships windows-x86_64 only."
    }
    throw "unsupported Windows architecture: $arch (this cycle ships windows-x86_64 only)"
}

# --- compose download URLs ---------------------------------------------------

function Get-DownloadUrls {
    param(
        [string]$Asset,
        [string]$Repo,
        [string]$Version,
        [string]$BaseUrl
    )
    if (-not [string]::IsNullOrEmpty($BaseUrl)) {
        $binaryUrl = "$BaseUrl/$Version/$Asset"
    } elseif ($Version -eq "latest") {
        $binaryUrl = "https://github.com/$Repo/releases/latest/download/$Asset"
    } else {
        $binaryUrl = "https://github.com/$Repo/releases/download/$Version/$Asset"
    }
    return @{
        Binary = $binaryUrl
        Sha    = "$binaryUrl.sha256"
    }
}

# --- sha256 ------------------------------------------------------------------

function Get-Sha256Hex {
    # Return lower-case hex digest of $Path on stdout.
    param([string]$Path)
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLower()
}

function Get-ExpectedSha256 {
    # `sha256sum` / `shasum -a 256` write `<hex>  <filename>` (two spaces).
    # Tolerate either form by reading the FIRST line, splitting on whitespace,
    # taking the first token. Get-Content -TotalCount 1 reads only line 1.
    param([string]$Path)
    $line = (Get-Content -Path $Path -TotalCount 1).Trim()
    if ([string]::IsNullOrEmpty($line)) {
        return ""
    }
    return ($line -split '\s+')[0].ToLower()
}

# --- download ----------------------------------------------------------------

function Save-RemoteFile {
    param(
        [string]$Url,
        [string]$OutPath
    )
    # Invoke-WebRequest is PowerShell 5.1 built-in; -UseBasicParsing skips the
    # IE COM dependency, which is required in headless contexts and on Server
    # Core. We rely on TLS 1.2+ being default on Windows 10 1809+ (the
    # supported floor); older hosts would need [Net.ServicePointManager]
    # ::SecurityProtocol manipulation — out of scope for v1.
    Invoke-WebRequest -Uri $Url -OutFile $OutPath -UseBasicParsing
}

# --- PATH hint ---------------------------------------------------------------

function Show-PathHintIfNeeded {
    param([string]$Prefix)
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ([string]::IsNullOrEmpty($userPath)) {
        $userPath = ""
    }
    $segments = $userPath -split ';'
    $alreadyOnPath = $false
    foreach ($segment in $segments) {
        if ($segment -ieq $Prefix) {
            $alreadyOnPath = $true
            break
        }
    }
    if ($alreadyOnPath) {
        return
    }
    Write-Info ""
    Write-Info "Note: $Prefix is not on your user PATH."
    Write-Info "      To add it permanently, run this once in PowerShell:"
    Write-Info ""
    Write-Info "        [Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','User') + ';$Prefix', 'User')"
    Write-Info ""
    Write-Info "      Then open a fresh PowerShell session before running 'novetest'."
}

# --- main --------------------------------------------------------------------

function Invoke-Install {
    $repo    = Resolve-EnvOrDefault -EnvName "NOVETEST_INSTALL_REPO"    -Default "Nove-Lab/Nove-Test"
    $version = Resolve-EnvOrDefault -EnvName "NOVETEST_INSTALL_VERSION" -Default "latest"
    $prefix  = Resolve-EnvOrDefault -EnvName "NOVETEST_INSTALL_PREFIX"  -Default (Join-Path $env:USERPROFILE ".local\bin")
    # install.sh distinguishes "BASE_URL unset" from "BASE_URL set to empty"
    # via POSIX `${var+x}`. PowerShell `[Environment]::GetEnvironmentVariable`
    # returns $null for unset and "" for empty, both of which fall through to
    # the default GitHub URL composition. Documented divergence; acceptable
    # because the empty-but-set case is not part of any user contract.
    $baseUrl = [Environment]::GetEnvironmentVariable("NOVETEST_INSTALL_BASE_URL", "Process")
    if ($null -eq $baseUrl) {
        $baseUrl = ""
    }

    $target = Get-Target
    $asset  = "novetest-$target.exe"
    $urls   = Get-DownloadUrls -Asset $asset -Repo $repo -Version $version -BaseUrl $baseUrl

    Write-Info "Installing novetest ($target, $version) into $prefix"
    Write-Info "  binary: $($urls.Binary)"
    Write-Info "  sha256: $($urls.Sha)"

    # Stage download under TEMP. The final Move-Item moves from TEMP to PREFIX;
    # if those are on different volumes (rare — both are normally on the
    # system drive), Move-Item falls back to copy+delete (still works, just
    # not atomic). For most installs they are on the same volume and the
    # rename is atomic.
    $stagingRoot = Join-Path $env:TEMP ("novetest-install-" + [Guid]::NewGuid().ToString("N"))
    [void](New-Item -ItemType Directory -Path $stagingRoot -Force)
    try {
        $binaryPath = Join-Path $stagingRoot $asset
        $shaPath    = "$binaryPath.sha256"

        Save-RemoteFile -Url $urls.Binary -OutPath $binaryPath
        Save-RemoteFile -Url $urls.Sha    -OutPath $shaPath

        $expected = Get-ExpectedSha256 -Path $shaPath
        if ([string]::IsNullOrEmpty($expected)) {
            throw "sha256 sidecar is empty: $($urls.Sha)"
        }
        $actual = Get-Sha256Hex -Path $binaryPath

        if ($expected -ne $actual) {
            # LOUD abort per Phase 0 DoD bullet #4 / install.sh §"sha256 mismatch".
            # Write the banner to stderr (Write-Host bypasses it, so use the
            # error stream via Write-Error) so a redirected stdout pipe (e.g.
            # `irm | iex 2>install.log`) still surfaces the abort visibly.
            $banner = @"

=================================================================
  SHA-256 MISMATCH - refusing to install $asset.
-----------------------------------------------------------------
  expected:  $expected
  actual:    $actual
  source:    $($urls.Binary)
  sidecar:   $($urls.Sha)

  This means the binary you would have installed does NOT match
  the published checksum. Possible causes: a corrupted download,
  a man-in-the-middle, or a tampered mirror. Nothing has been
  written to $prefix.
=================================================================
"@
            [Console]::Error.WriteLine($banner)
            exit 1
        }

        Write-Info "SHA-256 verified ($actual)."

        [void](New-Item -ItemType Directory -Path $prefix -Force)
        $installPath = Join-Path $prefix "novetest.exe"
        $stagePath   = "$installPath.tmp"
        # Copy from the GUID staging dir into the install prefix as `.tmp`,
        # then Move-Item -Force atomically replaces the live binary. This
        # mirrors install.sh's `cp ... .tmp; mv -f .tmp final` rename(2)
        # pattern. On Windows, Move-Item -Force uses MoveFileEx with
        # MOVEFILE_REPLACE_EXISTING — same-volume rename is atomic; cross-
        # volume falls back to copy+delete. Staging the .tmp under $prefix
        # (NOT under $env:TEMP) guarantees same-volume for the rename
        # regardless of where TEMP lives.
        Copy-Item -Path $binaryPath -Destination $stagePath -Force
        Move-Item -Path $stagePath -Destination $installPath -Force

        Write-Info "Installed: $installPath"
        Show-PathHintIfNeeded -Prefix $prefix
        Write-Info "Run 'novetest --version' to verify."
    } finally {
        Remove-Item -Path $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Invoke-Install
