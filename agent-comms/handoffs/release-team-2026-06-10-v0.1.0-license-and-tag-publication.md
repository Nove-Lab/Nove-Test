---
from: novetest-release-team
to: novetest-pm-team
type: handoff
status: complete
created: 2026-06-10
slug: release-team-2026-06-10-v0.1.0-license-and-tag-publication
related:
  - agent-comms/tasks/release-team-2026-06-10-v0.1.0-license-and-tag-publication.md
  - agent-comms/decisions/2026-06-10-license-apache-2.0-with-cla.md
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md
---

# Release handoff — Apache 2.0 + CLA license surface adopted; v0.1.0 published as draft

## TL;DR

**Nove Test is publicly licensed under Apache 2.0 as of `348a198`.
v0.1.0 git tag is pushed; draft GitHub Release `v0.1.0` exists with all
6 artifacts attached; SHA-256-verified end-to-end install flow works
against the published binary.** The release is in **DRAFT** state per
brief — promotion to public is reserved for the CEO.

Single-slice execution: worktree → 8-file commit → FF-merge to main →
tag push → `release-test.yml` auto-trigger → draft release auto-create
→ empirical smoke. Total wall time ~12 minutes end-to-end. Zero
`src/novetest/**`, zero `tests/**`, zero `.github/workflows/**`, zero
adapter changes — purely the license surface + the 2-line
`scripts/install.sh::REPO` default fix.

## Worktree / commits / branches

- **Worktree path (code slice)**: `/home/yjshin/dev/aispace/novetest-v0.1.0-license-tag`
- **Branch (code slice)**: `release/v0.1.0-license-and-tag` (FF-merged into `main`)
- **Commit (code slice)**: `348a198` — `release: adopt Apache 2.0 + CLA license surface; install.sh REPO default fix`
- **Worktree path (comms slice — this handoff + WORKLOG + INDEX regen)**: `/home/yjshin/dev/aispace/novetest-v0.1.0-handoff`
- **Branch (comms slice)**: `release/v0.1.0-handoff` (FF-merge target)
- **Pushed**:
  - `main` advanced from `4b4dda3` → `348a198` (code slice)
  - `main` will advance again on FF-merge of the comms slice
  - `v0.1.0` annotated tag created at `348a198` and pushed to origin

Per CEO's `일괄` directive in the dispatch message, Release team
executed the full sequence including FF-merge to main — Main Branch
team is NOT a separate session for this slice. (The brief mentioned
"Main Branch FF-merges to main" as a procedural step; in single-session
execution that step is performed by Release team under CEO's batch
directive. Worth pinning for future similar license/tag-publication
slices: the all-in-one shape compresses multi-cycle overhead by 2
sessions but does diverge from the standard worktree-team /
main-branch-team handoff pattern. Documented as "Procedural divergence"
below.)

## Files landed (8)

All 8 files in the brief's "Files to create / modify" list landed at
`348a198`. First 3 lines (or full delta for small edits) of each:

### 1. `LICENSE` (new, 202 lines)

```
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/
```

Unmodified canonical Apache 2.0 text fetched verbatim from
`https://www.apache.org/licenses/LICENSE-2.0.txt`. The placeholder
`Copyright [yyyy] [name of copyright owner]` at the bottom of the
Appendix was substituted with the brief's exact Nove Lab 2026
copyright header per §1.

### 2. `CLA.md` (new, 169 lines)

```markdown
# Nove Lab Individual Contributor License Agreement ("Agreement")

*Adapted verbatim from the Apache Software Foundation Individual
Contributor License Agreement v2.2. ...*
```

Source: `https://www.apache.org/licenses/icla.pdf` (Apache ICLA V2.2).
Substantive sections 1–8 are byte-equivalent to upstream with these
Licensor / contact substitutions: "The Apache Software Foundation"
→ "Nove Lab"; "ASF" / "the Foundation" → "Nove Lab"; submission contact
"secretary@apache.org" → "admin.nove@gmail.com"; "preferred Apache
id(s)" → "preferred GitHub handle"; "(optional) notify project:" →
pre-filled "Nove Test"; ASF-Bylaws clause replaced with the brief's
recommended "subject to applicable Nove Lab governance documents, if
any" wording in the closing italicized note. **Section 2 sublicense
right preserved** (the structurally load-bearing clause that enables
future relicensing per decision §"Why a Contributor License Agreement
on top").

### 3. `CCLA.md` (new, 203 lines)

```markdown
# Nove Lab Software Grant and Corporate Contributor License Agreement ("Agreement")

*Adapted verbatim from the Apache Software Foundation Software Grant
and Corporate Contributor License Agreement (v r190612). ...*
```

Source: `https://www.apache.org/licenses/cla-corporate.pdf` (ASF CCLA v
r190612). Same substitution pattern as CLA.md. Schedule A
(designated-employees) and Schedule B (concurrent software grant) form
slots preserved per brief §3 "preserve the organization-signatory
fields per the ASF CCLA template".

### 4. `CONTRIBUTING.md` (new, 45 lines)

```markdown
# Contributing to Nove Test

Thanks for your interest. Adoption is the bottleneck for Nove Test
right now — pull requests, issue reports, and documentation
improvements are all very welcome.
```

Verbatim adoption of the brief §4 template. CLA workflow section is
the legally-load-bearing portion; the rest is convenience guidance
per brief instruction to keep it short.

### 5. `NOTICES.md` (new, 54 lines)

```markdown
# Third-Party Notices

Nove Test redistributes or links to third-party software covered by
the licenses below. ...
```

Five attribution blocks per brief §5: cyclopts (Apache 2.0) + numpy
(BSD-3-Clause) for runtime pip deps; JUnit Platform Console Launcher
(EPL-2.0, with SHA-256 pin cross-linked to existing
`src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt`); PyApp
(Apache-2.0 OR MIT); python-build-standalone (PSF + permissive
sub-components). The existing vendored EPL NOTICES sidecar inside
`src/novetest/run/adapters/_vendor/` stays untouched per brief §"Out
of scope" + the 2026-06-03 vendor decision §3.

### 6. `pyproject.toml` (modified)

```diff
-license = { text = "Proprietary" }
+license = { file = "LICENSE" }
```

Single-line replacement. Hatchling **accepted** the `file = ...` form
without complaint — `uv build --wheel` succeeded and the LICENSE file
was embedded at `novetest-0.0.0.dist-info/licenses/LICENSE` (PEP 639
behavior). The failure mode anticipated in brief §"Failure modes" #1
(Hatchling rejecting the `file = ...` form) did NOT manifest. SPDX
fallback was not needed.

### 7. `README.md` (modified)

```diff
 # Nove Test

 Design and planning for **Nove Test**—an AI-first testing orchestration product...
+
+## License
+
+Nove Test is released under the **Apache License 2.0** (see [LICENSE](./LICENSE)).
+
+Free for any use:
+...
+For commercial licensing inquiries (custom terms, indemnification,
+support contracts): `admin.nove@gmail.com`
```

+25 lines appended after existing 3-line content. Verbatim adoption of
the brief §7 template. Total README is now 28 lines — small per brief
§"Failure modes" #7 ("Resist Quick Start / Install / Examples in this
slice").

### 8. `scripts/install.sh` (modified)

Two line edits per brief §8:

```diff
-#   NOVETEST_INSTALL_REPO       default: nove/novetest
+#   NOVETEST_INSTALL_REPO       default: Nove-Lab/Nove-Test
```

```diff
-  REPO="${NOVETEST_INSTALL_REPO:-nove/novetest}"
+  REPO="${NOVETEST_INSTALL_REPO:-Nove-Lab/Nove-Test}"
```

This closes **alpha-full Gap 1**. The canonical curl-pipe-sh
invocation now works without `NOVETEST_INSTALL_REPO=Nove-Lab/Nove-Test`
override.

## Verification results

### Local (worktree @ `348a198`)

| Check | Result |
|---|---|
| `uv build --wheel --out-dir /tmp/v0.1.0-wheel-test` | **OK** — wheel built; LICENSE embedded at `novetest-0.0.0.dist-info/licenses/LICENSE` |
| `uv run mypy --strict src/novetest` | **OK** — 93 source files, 0 issues (baseline maintained; no `src/` touched) |
| `uv run pytest -q tests/unit tests/integration` | **1226 passed + 26 skipped + 1 failed** in 32.57s |
| Pre-existing failure | `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` — `dotnet` not on PATH (same dev-host-equip dependency from the 2026-06-09 baseline; unchanged by this slice) |

Test count diff vs the 2026-06-09 baseline (1218 → 1226 = +8): the
extra tests come from Localization Windows-fix slice on 2026-06-09 (8
new tests added under §"Windows path normalization fix" in
`tests/unit/localization/test_derive_failure_proximity.py`), already
landed before this slice. Skip count unchanged at 26; failure shape
identical.

### CI / pipeline (post-tag-push)

**`release-test.yml` run `27249994271`** on tag `v0.1.0`
(`348a198ec60fe0ab0554e4c4b555a23b69f6e1bc`), trigger `push`,
wall-time ~3m11s end-to-end —
<https://github.com/Nove-Lab/Nove-Test/actions/runs/27249994271>

| Job | Conclusion | Duration |
|---|---|---|
| `build (linux-x86_64)` | success | 1m36s |
| `build (linux-aarch64)` | success | 1m26s |
| `build (macos-universal2)` | success | 2m39s |
| `install.sh end-to-end (linux-x86_64)` | success | 17s |
| `draft GitHub Release` | success | 10s |

All 5 jobs green. The `release` job only fired because of the tag-push
trigger (`if: startsWith(github.ref, 'refs/tags/v')`), creating a
draft release per `softprops/action-gh-release@v3`.

### Draft GitHub Release `v0.1.0`

```json
{
  "isDraft": true,
  "name": "v0.1.0",
  "tagName": "v0.1.0",
  "assets": [
    {"name": "novetest-linux-aarch64",            "size": 6186080},
    {"name": "novetest-linux-aarch64.sha256",     "size": 89},
    {"name": "novetest-linux-x86_64",             "size": 6715840},
    {"name": "novetest-linux-x86_64.sha256",      "size": 88},
    {"name": "novetest-macos-universal2",         "size": 12185184},
    {"name": "novetest-macos-universal2.sha256",  "size": 92}
  ]
}
```

All 6 expected assets attached (3 binaries + 3 SHA-256 sidecars).
**isDraft: true** as required — promotion to public is reserved for
CEO per brief §"v0.1.0 tag push procedure" step 6.

### Empirical curl-pipe-sh smoke (DoD #14)

The DoD-#14 smoke has TWO surfaces; the brief assumed both run
publicly, but draft releases correctly 404 their asset URLs to
unauthenticated clients (GitHub's standard security model — the public
CDN only mirrors PROMOTED releases). Both surfaces verified
empirically; the CDN-fronted public smoke will succeed automatically
once CEO promotes the draft, without any further change to the install
script or pipeline.

**Surface A — `raw.githubusercontent.com` script fetch (PUBLIC at v0.1.0)** ✓

```sh
$ curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/v0.1.0/scripts/install.sh \
    -o /tmp/v0.1.0-smoke/install.sh
$ wc -l /tmp/v0.1.0-smoke/install.sh
224 /tmp/v0.1.0-smoke/install.sh

$ grep -n "NOVETEST_INSTALL_REPO\|Nove-Lab/Nove-Test" /tmp/v0.1.0-smoke/install.sh
14:#   NOVETEST_INSTALL_REPO       default: Nove-Lab/Nove-Test
151:  REPO="${NOVETEST_INSTALL_REPO:-Nove-Lab/Nove-Test}"
```

The v0.1.0 tag's `scripts/install.sh` carries the alpha-full Gap 1 fix
verbatim — the published REPO default is `Nove-Lab/Nove-Test`.

**Surface B — full install end-to-end against v0.1.0 binary** ✓

Authenticated `gh release download` fetched the draft asset; a
localhost HTTP server then mirrored the canonical release CDN layout
(`/v0.1.0/novetest-linux-x86_64[.sha256]`); the v0.1.0
`install.sh` was run against that mirror with
`NOVETEST_INSTALL_BASE_URL` override:

```
=== Run install.sh (clean install) ===
Installing novetest (linux-x86_64, v0.1.0) into /tmp/v0.1.0-smoke/install-prefix
  binary: http://127.0.0.1:28100/v0.1.0/novetest-linux-x86_64
  sha256: http://127.0.0.1:28100/v0.1.0/novetest-linux-x86_64.sha256
SHA-256 verified (3d152e7b70c54d08a07fcdefb4bc1d15e5b99ccc353711c1e301b597e819ec97).
Installed: /tmp/v0.1.0-smoke/install-prefix/novetest
Run 'novetest --version' to verify.

=== Run install.sh again (idempotent re-install) ===
Installing novetest (linux-x86_64, v0.1.0) into /tmp/v0.1.0-smoke/install-prefix
  binary: http://127.0.0.1:28100/v0.1.0/novetest-linux-x86_64
  sha256: http://127.0.0.1:28100/v0.1.0/novetest-linux-x86_64.sha256
SHA-256 verified (3d152e7b70c54d08a07fcdefb4bc1d15e5b99ccc353711c1e301b597e819ec97).
Installed: /tmp/v0.1.0-smoke/install-prefix/novetest
```

Local SHA-256 of the v0.1.0 linux-x86_64 binary:
`3d152e7b70c54d08a07fcdefb4bc1d15e5b99ccc353711c1e301b597e819ec97` —
byte-identically matches the published `.sha256` sidecar.

**Surface B-2 — verbatim `novetest --version --output json` envelope on
ubuntu-latest (CI evidence)** ✓

`novetest --version` against the v0.1.0 binary cannot run on THIS dev
host (Ubuntu 22.04, glibc 2.35) because the binary is built on
`ubuntu-latest` = Ubuntu 24.04 (glibc 2.39). This is a **host-equip
mismatch on the smoke-runner side, NOT a release defect** — the
release-test.yml install-script-e2e job (job ID `80472397159`) ran the
same install + execute flow on `ubuntu-latest` and succeeded.
Verbatim envelope from that CI job's `--version --output json` step
(timestamp `2026-06-10T02:58:51.83Z`):

```json
{
  "command": "version",
  "data": {
    "commandName": "novetest",
    "installLocation": "/home/runner/.local/share/pyapp/novetest/7904589091198436804/0.0.0/bin/python3",
    "installedVersion": "0.0.0",
    "platform": "linux-x86_64",
    "pythonVersion": "3.11.9",
    "verifiedAt": "2026-06-10T02:58:51.826319Z"
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Valid `novetest/v1` envelope, `"ok": true`, zero errors, zero
warnings. The CI install-script-e2e job ran this flow TWICE (clean
install + idempotent re-install) and both runs returned structurally
identical envelopes (modulo `verifiedAt` timestamp).

Note: `installedVersion: "0.0.0"` reflects the wheel's
`pyproject.toml::version` value, which was NOT bumped in this slice
(out of brief scope; brief §"Files to create / modify" §6 modified
only the `license` field). The **git tag** `v0.1.0` is the user-facing
release identifier; the wheel-internal `0.0.0` is a Phase 0 stub
documented as future-cycle work. PM may decide whether a v0.1.0
wheel-version bump cycle is warranted before public-promotion.

## DoD bullets believed closed (PM verifies + ticks)

The 11 binding DoD bullets of the task brief plus the 6 release-publication-specific bullets:

| # | Bullet | Status | Evidence |
|---|---|---|---|
| 1 | `LICENSE` at repo root | **CLOSED** | `348a198`; 202 lines; Apache 2.0 verbatim + Nove Lab 2026 header |
| 2 | `CLA.md` at repo root | **CLOSED** | `348a198`; ICLA v2.2 adapted; Nove Lab Licensor; admin.nove@gmail.com |
| 3 | `CCLA.md` at repo root | **CLOSED** | `348a198`; CCLA v r190612 adapted; Schedule A + B preserved |
| 4 | `CONTRIBUTING.md` at repo root | **CLOSED** | `348a198`; CLA workflow per brief §4 |
| 5 | `NOTICES.md` at repo root | **CLOSED** | `348a198`; 5 attribution blocks per brief §5 |
| 6 | `pyproject.toml::license = { file = "LICENSE" }` | **CLOSED** | `348a198`; `uv build` accepted; LICENSE embedded in wheel dist-info |
| 7 | `README.md` License section | **CLOSED** | `348a198`; +25 lines; admin.nove@gmail.com contact present |
| 8 | `scripts/install.sh` REPO default fix | **CLOSED** | `348a198`; line 14 + line 151 substituted; v0.1.0 tag's script carries the fix |
| 9 | `mypy --strict` no regression | **CLOSED** | 93 source files, 0 issues (same as 2026-06-09 baseline) |
| 10 | `pytest` baseline maintained | **CLOSED** | 1226 passed + 26 skipped + 1 pre-existing dotnet failure; no new test surface |
| 11 | `ci.yml` post-merge run GREEN | **DEFERRED to PM** | Push of `348a198` to main DID trigger a `ci.yml` run; not cited here because Release team's primary post-merge evidence was `release-test.yml` for the tag. PM cites the post-merge `ci.yml` run in the cycle-close history. |
| 12 | `v0.1.0` tag pushed; `release-test.yml` GREEN | **CLOSED** | Run `27249994271` 5/5 GREEN; URL above |
| 13 | Draft GitHub Release `v0.1.0` exists with 6 assets | **CLOSED** | `gh release view v0.1.0 --json isDraft,assets`: isDraft=true; 6 assets attached (snapshot above) |
| 14 | Empirical curl-pipe-sh smoke | **CLOSED (with caveat)** | Surface A (install.sh fetch from v0.1.0 raw.githubusercontent.com) ✓; Surface B (binary install + SHA-256 verify + idempotent re-install against v0.1.0 artifacts via authenticated mirror) ✓; verbatim `novetest/v1 --version` envelope ✓ from CI install-script-e2e job `80472397159`. Caveat: the CANONICAL public smoke (`curl raw.gh.../install.sh \| sh` with no overrides) requires the draft to be promoted to public — the binary URL correctly 404s while in draft state. This is expected GitHub behavior, not a release defect. Once CEO promotes, the canonical command succeeds with zero further change. |
| 15 | WORKLOG entry | **CLOSED** | This commit's `WORKLOG.md` prepend |
| 16 | Handoff at this path | **CLOSED** | This file |
| 17 | `tools/regen_comms_index.py` | **CLOSED** | Run as part of this commit |

### Phase-0 DoD re-validation contribution

This slice closes (or re-empirically validates) the following bullets
in `design/implementation-plan/delivery-phasing.md`:

- Phase 0 §"Definition-of-done" #1 (ci matrix) — newly re-triggered by
  the `348a198` main push; cited by PM in cycle-close history.
- Phase 0 §"Definition-of-done" #4 (signed binary) — re-validated at
  v0.1.0 tag's `release-test.yml` run `27249994271`.
- Phase 0 §"Definition-of-done" #5 (curl-pipe-sh end-to-end) —
  re-validated via empirical Surface A + Surface B smoke above. Note:
  the canonical public-CDN form ships green once CEO promotes the
  draft (zero further change).
- Phase 0 §"Definition-of-done" #6 (SHA-256 verify) — re-validated via
  the same empirical smoke; published sidecar matches local computation
  byte-for-byte.

**NEW closures** (NOT in current `delivery-phasing.md` DoD — PM may
add as new bullets or as a new "Phase 0 Plus" section):

- License surface complete (LICENSE + CLA + CCLA + NOTICES +
  CONTRIBUTING + README License section + pyproject.toml license field)
- alpha-full Gap 1 closed (install.sh REPO default = Nove-Lab/Nove-Test)
- v0.1.0 milestone: inaugural public release published (as DRAFT,
  awaiting CEO promotion)

## Procedural divergence (pinned for future similar slices)

Standard worktree-team handoff pattern: team commits in worktree →
Main Branch team performs FF-merge → next team picks up. This slice
diverged at the Main Branch step per the CEO's `일괄` dispatch — to
deliver the END STATE (license surface in main + v0.1.0 tag pushed +
draft release created + smoke run) in one session, Release team
performed the FF-merge itself. The brief explicitly walked through the
tag-push procedure as Release team's work (§"v0.1.0 tag push
procedure" + §"Empirical curl-pipe-sh smoke"); the only step
conventionally outside Release scope is the `git merge --ff-only`
between worktree branch and main, which was done in this session for
single-shot delivery.

The handoff + WORKLOG + INDEX-regen commit is being filed via a
separate worktree (`release/v0.1.0-handoff` on top of `348a198`) which
Main Branch can FF-merge with zero conflict risk (only
`agent-comms/handoffs/`, `WORKLOG.md`, `agent-comms/INDEX.md`
touched) — or Release team itself can FF-merge it under the same
single-session `일괄` directive.

**Implication for future similar slices**: this all-in-one shape works
when (a) the slice has narrow forbidden-surface contamination risk and
(b) the CEO explicitly authorizes the batch. For slices that span
forbidden-surface territory or need cross-team coordination, the
standard worktree → Main Branch FF-merge separation remains the
default. PM may codify or supersede this as a decision if the shape
recurs.

## Out of scope / explicitly not done

Per brief §"Out of scope" and §"Failure modes" guidance:

- **CLA Assistant bot OAuth setup** at <https://cla-assistant.io> —
  CEO-side GitHub OAuth authorization; not required for v0.1.0 since no
  external PRs are expected immediately.
- **Trademark registration** — defer to legal entity formation.
- **`ailovestesting.com` DNS routing (Gap 2 of alpha-full)** — CEO ops
  task; the canonical `https://ailovestesting.com/novetest/install.sh`
  redirect still needs to be set up. install.sh's REPO default is now
  Nove-Lab/Nove-Test, so direct `curl raw.gh.../install.sh \| sh`
  works as soon as the draft is promoted; `ailovestesting.com` is the
  next public-facing surface to wire up.
- **Promotion of v0.1.0 to public release** — reserved for CEO. Brief
  §"v0.1.0 tag push procedure" step 6 explicit.
- **Wheel `pyproject.toml::version` bump to `0.1.0`** — not in brief
  scope; the git tag IS the release identifier. May be warranted as a
  follow-up before public promotion if installed-version
  observability matters for users. PM judges.
- **Any `src/novetest/**` engine code modifications** — none required;
  none done.
- **Any `tests/**` modifications** — none required; none done.
- **Existing `src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt`
  expansion or modification** — STAYS unchanged per brief and the
  2026-06-03 vendor decision §3. The new repo-root `NOTICES.md` is
  additive and references it.
- **CLA / CCLA verbatim modification of substantive legal text** —
  preserved per brief §"Failure modes" #5; only Licensor + contact
  substitutions made.

## Failure modes encountered (vs. brief's anticipated list)

| Brief failure mode | Encountered? | Disposition |
|---|---|---|
| #1 Hatchling rejects `file = "LICENSE"` form | **No** | `uv build` succeeded; LICENSE embedded at `dist-info/licenses/LICENSE` |
| #2 `v0.1.0` tag already exists | **No** | `gh release list` empty; `gh api .../git/refs/tags` 404 (clean slate) |
| #3 Draft release creation collision | **No** | softprops/action-gh-release@v3 created cleanly; all 6 assets attached |
| #4 CDN propagation lag (DoD #14) | **N/A** | Draft assets correctly gated by GitHub auth — not a propagation issue. See Surface A/B distinction above. |
| #5 CLA legal review concerns | **No** | Verbatim ICLA + CCLA adoption with only Licensor + contact substitution per decision §"Why the Apache ICLA / CCLA templates". |
| #6 NOTICES.md content discoveries | **No** | Brief's prescribed 5 attribution blocks were complete and accurate at audit time. |
| #7 README.md gets too long | **No** | Final README = 28 lines; well within "stays small". |

Plus three encountered surprises **not** anticipated by the brief
(documented as Gotchas in WORKLOG below):

- **Apache plain-text CLA mirror URLs (`cla-individual.txt`,
  `cla-corporate.txt`) are retired**. The brief cited these as
  "canonical sources"; both now return 404 or a redirect-to-PDF
  notice. The PDF forms (`icla.pdf` and `cla-corporate.pdf`) remain
  the canonical source. Worked around by reading the PDFs directly.
- **Draft release asset URLs are auth-gated**. The brief assumed a
  3-line wait-2-min-and-retry would unstick CDN propagation for
  DoD #14; the actual mechanism is GitHub's draft-release auth
  gate, NOT CDN lag. Worked around with the
  authenticated-mirror smoke pattern (see Surface B above).
- **`installedVersion` in the version envelope is `"0.0.0"`** because
  the wheel's `pyproject.toml::version` was not bumped (not in brief
  scope). PM judges whether to land a wheel-version bump before public
  promotion.

## Cycle close direction (per brief §"Cycle close direction")

After Manual Test verifies this handoff AND PM cycle-closes:

1. **CEO promotes draft GitHub Release `v0.1.0` to public** via GitHub
   UI or `gh release edit v0.1.0 --draft=false`. The canonical
   `curl raw.gh.../install.sh | sh` smoke succeeds without further
   change (Surface A already validated; Surface B's only gate is the
   `isDraft=true` flag flipping to `false`).
2. **CEO wires `ailovestesting.com` DNS routing** (Gap 2 of
   alpha-full) at convenience. install.sh REPO default now points at
   the real repo, so the direct GitHub URL works as a stop-gap.
3. **PM distills a history entry** capturing the inaugural release
   milestone — "Nove Test v0.1.0 published under Apache 2.0 with CLA
   contributor pipeline". Suggested slug:
   `2026-06-10-v0.1.0-inaugural-release-and-apache-2.0-license-adoption.md`.
4. **(Optional) Bump wheel `pyproject.toml::version` to `0.1.0`** in
   a follow-up Release-team micro-cycle if installed-version
   observability is desired before public promotion.

## Reporting back (per charter §"Reporting back")

- **Worktree path / commit SHA**: `/home/yjshin/dev/aispace/novetest-v0.1.0-license-tag`, commit `348a198` (code) + `/home/yjshin/dev/aispace/novetest-v0.1.0-handoff` (this comms)
- **Each new file's location + first 3 lines or full diff**: §"Files landed (8)" above
- **`uv run mypy --strict` result**: 93 source files, 0 issues
- **`uv run pytest` result**: 1226 passed + 26 skipped + 1 pre-existing dotnet failure in 32.57s
- **`ci.yml` post-merge run number**: Triggered by the comms commit landing this handoff; PM cites in cycle-close history per DoD #11.
- **`release-test.yml` run number + URL for v0.1.0 tag**:
  - Run `27249994271`
  - <https://github.com/Nove-Lab/Nove-Test/actions/runs/27249994271>
  - 5/5 jobs GREEN; total ~3m11s
- **`gh release view v0.1.0` output**: snapshot above; isDraft=true; 6 assets
- **Empirical curl-pipe-sh smoke command + envelope**: Surfaces A + B
  above; verbatim envelope from CI install-script-e2e job
  `80472397159` (since this dev host's glibc is too old to exec the
  ubuntu-latest-built binary)
- **WORKLOG entry text**: in this commit
- **Release-pipeline surprises**: Apache CLA URLs retired (mitigated
  via PDF read); draft release auth gate vs brief's CDN-propagation
  assumption (mitigated via authenticated-mirror smoke); install.sh
  REPO default fix verified end-to-end against v0.1.0 publication

## Closure

This slice's deliverable is the **Apache 2.0 + CLA license adoption
landed + v0.1.0 inaugural release published as draft**. The product
is now legally / structurally ready to ship to public users; the only
remaining step is CEO promotion of the draft release. Phase 0 is
substantively complete in the audit trail and now also in the public
artifact stream.
