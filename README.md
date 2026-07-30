<div align="center">

# Nove Test

**Continuous testing intelligence layers for AI coding agents.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![CI](https://github.com/Nove-Lab/Nove-Test/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Nove-Lab/Nove-Test/actions/workflows/ci.yml)
[![Release pipeline](https://github.com/Nove-Lab/Nove-Test/actions/workflows/release-test.yml/badge.svg)](https://github.com/Nove-Lab/Nove-Test/actions/workflows/release-test.yml)
[![Python](https://img.shields.io/badge/python-3.11_|_3.12_|_3.13-blue.svg)](https://www.python.org)
[![Version](https://img.shields.io/badge/version-v0.3.0-success.svg)](https://github.com/Nove-Lab/Nove-Test/releases)

Stop naive testing — simply running tests and getting pass/fail results.

Add testing intelligence layers on top of your native test engines: structured guidance through coverage-guided testing, regression testing, and fault localization.

Nove Test ships with native test runner wrappers, test result memory, a coverage analyzer, a regression engine, fault localization, and test replay — all under one CLI, all under one JSON contract.

[**Install**](#install) · [**Quick start**](#quick-start) · [**Why**](#why-nove-test) · [**For AI agents**](#for-ai-coding-agents) · [**Docs**](./docs/) · [**License**](#license)

</div>

---

## Install

One line, Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh | sh
```

One line, Windows (PowerShell 5.1+):

```powershell
irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex
```

Both scripts detect your OS/arch, download a signed binary from the latest GitHub Release, verify SHA-256, and install to `~/.local/bin/novetest` (Linux/macOS) or `%USERPROFILE%\.local\bin\novetest.exe` (Windows). Re-running upgrades in place.

Inspect-first (recommended):

```bash
# Linux / macOS
curl -fsSL -o install.sh https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh
less install.sh   # read it
sh install.sh
```

```powershell
# Windows
irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 -OutFile install.ps1
Get-Content install.ps1   # read it
.\install.ps1
```

Or download a binary directly:

```bash
curl -fsSL -o novetest \
  https://github.com/Nove-Lab/Nove-Test/releases/latest/download/novetest-linux-x86_64
curl -fsSL -o novetest.sha256 \
  https://github.com/Nove-Lab/Nove-Test/releases/latest/download/novetest-linux-x86_64.sha256
sha256sum -c novetest.sha256
chmod +x novetest && mv novetest ~/.local/bin/
```

For Python tooling users:

```bash
uv tool install novetest    # via uv (Astral)
pipx install novetest       # via pipx
```

## Quick start

```bash
cd your-project          # any project — Python, JS, Go, Java, .NET, Rust
novetest init            # creates .novetest/, detects the test engine
novetest test            # runs your tests, stores the result, prints JSON
novetest status          # list stored runs
novetest inspect <id>    # full Run Record (passes, failures, coverage, metadata)
novetest compare A B     # what changed between runs A and B
novetest localization run --formula ochiai   # rank likely buggy files (SBFL)
```

Every command emits a `novetest/v1` JSON envelope on stdout:

```json
{
  "version": "novetest/v1",
  "verb": "test",
  "exit_code": 0,
  "data": {
    "run_id": "2026-06-10T07:23:14Z-a1b2c3",
    "summary": { "total": 42, "passed": 41, "failed": 1, "skipped": 0 },
    "results": [
      {
        "test_id": "tests/test_auth.py::test_login_succeeds_with_valid_credentials",
        "outcome": "passed",
        "duration_ms": 12
      }
    ]
  },
  "warnings": [],
  "errors": []
}
```

The JSON shape is **stable across all six engines** (pytest, jest, JUnit, go test, dotnet, cargo). Your scripts and AI agents see the same envelope regardless of what's underneath.

## Why Nove Test?

| You are | Nove Test gives you |
|---|---|
| **An AI coding agent** | Stable `novetest/v1` envelopes — parse JSON, not stderr. Run Records as ground truth — compare your edits against a known baseline. SBFL fault localization — get a ranked list of probable culprit files. |
| **A solo developer** | One binary, six engines, zero per-engine config. Persistent run history without setting up a database. |
| **A team CI integrator** | Stable JSON contract across pytest / jest / JUnit / go test / dotnet / cargo. Deterministic regression detection. |
| **A test-engine author** | Documented, minimal adapter contract. Bring your own engine, get storage and cross-run analysis for free. |

## Features

- ✅ **Adapters for six native test engines** — pytest · jest · JUnit (Maven, Gradle) · go test · dotnet (xUnit / NUnit / MSTest) · cargo
- ✅ **Parsers for five coverage formats** — coverage.py · istanbul (LCOV) · jacoco · cobertura · with cross-drive normalization on Windows
- ✅ **Persistent run records** — every execution stored as immutable JSON under `.novetest/`
- ✅ **Cross-run regression** — deterministic deltas between any two runs
- ✅ **Fault localization** — SBFL (Ochiai, DStar, Op2, Tarantula) across three degradation modes
- ✅ **Replay** — re-execute a prior run under reconstructed conditions
- ✅ **AI-friendly by default** — `--output json` is the default contract; `NOVETEST_OUTPUT=json` env override
- ✅ **Single binary** — PyApp-wrapped, no Python toolchain required on the user's machine

## For AI coding agents

If you're an AI agent invoking Nove Test on a user's project, here's the contract you can rely on:

- **One verb, one envelope, one exit code.** Every CLI verb emits `{ version: "novetest/v1", verb, exit_code, data, warnings, errors }`. Parse JSON; ignore stderr.
- **The `version` field is the schema contract.** When it ticks to `novetest/v2`, the schema may break — until then it won't.
- **Run IDs are stable references.** Use them in subsequent calls (`inspect <id>`, `compare <A> <B>`, `localization run --baseline <id>`).
- **Determinism is a first-class goal.** A given input project + engine + version produces the same `summary` block. Differences across runs are user-visible flake, not framework noise.
- **`warnings[]` is your degradation signal.** Adapter quirks, partial coverage, missing tooling — all surface here as structured `{ code, message, ... }` entries. Match on `code` for programmatic handling.

See [`docs/`](./docs/) for the full envelope reference and integration patterns.

## Status

**v0.3.0 — production-ready for Linux, macOS, and Windows.**

Stable today:
- All six native test engines and CLI verbs
- The `novetest/v1` JSON envelope schema
- The on-disk Run Record format under `.novetest/`
- Linux (x86_64, aarch64), macOS (universal2), and Windows (x86_64) distribution

Roadmap:
- **Rich TTY renderer** — tables, colors, and single-line summaries for human use
- **Nove Test Console** — a dashboard for humans to inspect what AI coding agents are doing through Nove Test
- **Nove Test Team** — team-scale collaborative test-driven development built on the Nove Test engine

## Documentation

User documentation ships in two parallel sets — same flow, same verbs, tuned to two audiences:

- **[For humans](./docs/human/)** — install, quick start, per-language notes, deeper verbs, troubleshooting. Examples are scannable terminal text with glyph summaries (`✓ ✗ — ⚠ ! ? · ↳`).
- **[For AI agents](./docs/agent/)** — same flow, same verbs, but every example is a full `novetest/v1` JSON envelope with deterministic routing on `recommendations[].category`.

Start at [`docs/`](./docs/) for the audience picker.

## License

Nove Test is released under the **Apache License 2.0** — see [LICENSE](./LICENSE).

Free for any use:
- Internal use, CI integration, production deployment, by individuals and organizations of any size
- Forking, modifying, redistributing (with notices preserved)
- Academic and research use, including publishing modifications

The Apache 2.0 patent grant terminates if you initiate patent litigation against Nove Test or its contributors (Apache 2.0 §3).

**Enterprise licensing inquiries** (custom terms, indemnification, support contracts): `admin.nove@gmail.com`

## Contributing

Pull requests, bug reports, documentation improvements, and adapter contributions for new test engines are all welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to get started.

---

<div align="center">

### Stop instant testing.
### Build continuous testing intelligence with Nove Test.

</div>
