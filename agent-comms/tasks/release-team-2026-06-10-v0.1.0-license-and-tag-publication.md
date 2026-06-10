---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-06-10
slug: release-team-2026-06-10-v0.1.0-license-and-tag-publication
related:
  - agent-comms/decisions/2026-06-10-license-apache-2.0-with-cla.md
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md
  - design/implementation-plan/foundations.md
  - design/implementation-plan/delivery-phasing.md
---

# Release team task: license adoption (Apache 2.0 + CLA) + v0.1.0 tag publication

## Mission

Land the inaugural license surface AND publish the first user-visible
release tag (`v0.1.0`) in a single packed Release-team slice. CEO
approved both decisions on 2026-06-10.

- **License**: Apache License 2.0 + Apache ICLA/CCLA-based CLA, Licensor
  "Nove Lab" (placeholder), commercial license contact
  `admin.nove@gmail.com` — full rationale in
  `agent-comms/decisions/2026-06-10-license-apache-2.0-with-cla.md`.
- **alpha-full Gap 1 fix**: `scripts/install.sh::REPO` default from
  `nove/novetest` to `Nove-Lab/Nove-Test` so the canonical install
  command works without env var override.
- **v0.1.0 release**: push the tag triggering `release-test.yml` ->
  3-cell PyApp build + install-script-e2e + draft GitHub Release
  auto-creation per `softprops/action-gh-release@v3`.

This is the milestone-defining transition from "release-ready" (achieved
2026-06-09, `8ae90cd`) to "released".

## Pre-flight reading

1. `agent-comms/decisions/2026-06-10-license-apache-2.0-with-cla.md` — the binding decision
2. `agent-comms/decisions/2026-05-14-install-script-hosting-url.md` — install.sh canonical URL plan
3. `agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md` — JUnit jar NOTICES treatment
4. `agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md` — empirical MVP release-ready evidence
5. `design/implementation-plan/foundations.md` section 7 (Distribution)
6. `.github/workflows/release-test.yml` — the pipeline you will be triggering
7. `scripts/install.sh` — REPO default fix surface
8. `src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt` — existing JUnit NOTICES (stays as-is; new repo-root NOTICES.md is additive)

## Files to create / modify

### 1. `LICENSE` (NEW at repo root)

Exact unmodified Apache License 2.0 text. Canonical source:
https://www.apache.org/licenses/LICENSE-2.0.txt

Copy the full document INCLUDING the standard appendix titled "APPENDIX:
How to apply the Apache License to your work." That appendix contains a
boilerplate paragraph at the bottom for the copyright holder to fill in.

Replace the boilerplate paragraph at the END of the file with exactly:

```
Copyright 2026 Nove Lab

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

The Apache 2.0 text body itself (11.4 KB, sections 1-9 + Appendix) is
NOT modified — only the placeholder copyright block at the bottom
receives the "Nove Lab" + "2026" substitution.

### 2. `CLA.md` (NEW at repo root) — Individual Contributor License Agreement

Base: Apache Software Foundation ICLA. Canonical source:
https://www.apache.org/licenses/icla.pdf (also published as plain-text
mirror at https://www.apache.org/licenses/cla-individual.txt for easier
PDF-to-Markdown conversion).

Adapt verbatim with these substitutions:

- "The Apache Software Foundation" -> "Nove Lab"
- "ASF" or "the Foundation" -> "Nove Lab"
- Project name field -> "Nove Test"
- Contact email for submission -> `admin.nove@gmail.com`
- Strip ASF-specific clauses about ASF Bylaws compliance (the
  "subject to" pointer to ASF Bylaws becomes "subject to applicable
  Nove Lab governance documents, if any")

Preserve verbatim the substantive legal clauses:

- Section 1 — Definitions
- Section 2 — Grant of Copyright License (perpetual, worldwide,
  non-exclusive, royalty-free, irrevocable, **sublicensable**)
- Section 3 — Grant of Patent License
- Section 4 — Warranty
- Section 5 — Third-party content disclosure
- Section 6 — Non-warranty disclaimer
- Section 7 — Obligation to notify Nove Lab of material facts

Convert from PDF text to Markdown. Wrap legal language verbatim — do
NOT paraphrase. Test the resulting Markdown renders cleanly on GitHub.

### 3. `CCLA.md` (NEW at repo root) — Corporate Contributor License Agreement

Base: Apache Software Foundation CCLA. Canonical source:
https://www.apache.org/licenses/cla-corporate.txt

Same substitution pattern as `CLA.md`. Preserve the organization-
signatory fields per the ASF CCLA template (Corporation Name, Title,
Mailing Address, Country, Telephone, Email, designated signatories
list with affiliated employee scoping).

### 4. `CONTRIBUTING.md` (NEW at repo root)

Sections (suggested, adjust voice/order as you see fit):

```markdown
# Contributing to Nove Test

Thanks for your interest. Adoption is the bottleneck for Nove Test
right now — pull requests, issue reports, and documentation
improvements are all very welcome.

## License of your contribution

Nove Test is released under the Apache License 2.0 (see `LICENSE`).
Contributions are accepted under a Contributor License Agreement:

- Individual contributors: [`CLA.md`](./CLA.md)
- Organization-affiliated contributors: [`CCLA.md`](./CCLA.md)

The CLA is **not a copyright assignment** — you keep your copyright.
The CLA grants Nove Lab a perpetual, royalty-free, sublicensable
license that lets us relicense future versions if strategically
necessary (e.g., issuing a v0.X.0 under different terms). This is the
standard pattern used by Apache, Kubernetes (CNCF), Google, and
Microsoft open-source projects.

## How to contribute

1. Fork the repository.
2. Create a feature branch from `main`.
3. Make your change. Run `uv run pytest -q tests/unit tests/integration`
   and `uv run mypy --strict src/novetest` locally to verify.
4. Open a pull request against `main`.
5. On your first PR, the CLA Assistant bot will comment with a link to
   sign the CLA. Sign once and all future PRs are covered.
6. A maintainer reviews. We aim for first response within a week.

## Reporting bugs

Open a GitHub issue with:
- Minimal reproduction steps
- Expected vs actual output
- `novetest --version --output json` output
- Operating system and Python version (if relevant)

## Commercial license inquiries

For commercial terms, custom indemnification, support contracts, or
dual-licensing of derivative products: `admin.nove@gmail.com`
```

Keep CONTRIBUTING.md short. The CLA workflow is the only legally-load-
bearing section; everything else is convenience guidance.

### 5. `NOTICES.md` (NEW at repo root)

Comprehensive third-party attribution. Sections:

```markdown
# Third-Party Notices

Nove Test redistributes or links to third-party software covered by
the licenses below. Apache License 2.0 section 4(d) requires
preservation of these notices in all derivative works.

## Runtime dependencies (shipped in the published wheel)

### cyclopts (>=3.0)

- Project: https://github.com/BrianPugh/cyclopts
- License: Apache License 2.0
- Copyright (c) Brian Pugh and cyclopts contributors

### numpy (>=1.26)

- Project: https://github.com/numpy/numpy
- License: BSD 3-Clause License
- Copyright (c) 2005-present, NumPy Developers

The full text of each license is reproduced in the installed
package metadata (pip-managed under `*.dist-info/`). Distribution
of those metadata files satisfies the respective attribution
clauses.

## Vendored binary (sidecar in the published wheel)

### JUnit Platform Console Standalone (1.11.4)

- File: `src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar`
- Project: https://github.com/junit-team/junit5
- License: Eclipse Public License 2.0
- SHA-256 pin: `b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc`
- Distributed unmodified per decision `agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md`.
- Per-file NOTICES (with EPL 2.0 section 3.3 unmodified-distribution
  statement) live alongside the jar at
  `src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt`.

## Install-time bootstrap (downloaded by PyApp on first run)

### PyApp (0.22.0)

- Project: https://github.com/ofek/pyapp
- License: Apache License 2.0 OR MIT
- Copyright (c) Ofek Lev

### python-build-standalone CPython

- Project: https://github.com/indygreg/python-build-standalone
- License: Python Software Foundation License plus permissive licenses
  for sub-components (OpenSSL, libffi, ncurses, etc.)

These artifacts are not shipped inside the Nove Test wheel — PyApp
downloads them on first invocation of the installed binary. They are
listed here for completeness of attribution.
```

### 6. `pyproject.toml` (MODIFY)

Current (line 7):

```toml
license = { text = "Proprietary" }
```

Replace with:

```toml
license = { file = "LICENSE" }
```

Verify `uv build` still succeeds with this change. Hatchling supports
`license = { file = "..." }` form. PEP 639's `license-files = [...]`
form is forward-compat but not strictly required at this stage — skip
unless Hatchling complains.

### 7. `README.md` (MODIFY — add License section)

Current README is 3 lines (just project name + tagline). Add a License
section after the existing content:

```markdown
## License

Nove Test is released under the **Apache License 2.0** (see [LICENSE](./LICENSE)).

Free for any use:
- Internal use, CI integration, production deployment, by individuals
  and organizations of any size
- Embedding in your own products (commercial or non-commercial)
- Forking, modifying, redistributing (with notices preserved)
- Building commercial products, services, and SaaS offerings on top of
  Nove Test
- Academic and research use, including publishing modifications

The Apache 2.0 patent grant terminates if you initiate patent
litigation against Nove Test or its contributors (Apache 2.0 section 3).

External contributions are accepted under a Contributor License
Agreement — see [CLA.md](./CLA.md) for individuals, [CCLA.md](./CCLA.md)
for organizations, and [CONTRIBUTING.md](./CONTRIBUTING.md) for the
workflow.

For commercial licensing inquiries (custom terms, indemnification,
support contracts): `admin.nove@gmail.com`
```

### 8. `scripts/install.sh` (MODIFY — alpha-full Gap 1)

Two edits:

**Line 14 (comment block)**:

Current:
```sh
#   NOVETEST_INSTALL_REPO       default: nove/novetest
```

Replace with:
```sh
#   NOVETEST_INSTALL_REPO       default: Nove-Lab/Nove-Test
```

**Line 151 (main function)**:

Current:
```sh
  REPO="${NOVETEST_INSTALL_REPO:-nove/novetest}"
```

Replace with:
```sh
  REPO="${NOVETEST_INSTALL_REPO:-Nove-Lab/Nove-Test}"
```

This 2-line change makes the canonical curl-pipe-sh user invocation
work without env var override. The install script will then compose
the right GitHub Releases URL (`https://github.com/Nove-Lab/Nove-Test/releases/latest/download/...`)
by default.

### 9. `design/implementation-plan/foundations.md` section 7 (PM-OWNED — already handled)

PM edits foundations.md section 7 in the same commit that ships this
brief. Release team does NOT touch this file — it is in PM's owned
files per `.claude/agents/novetest-pm-team.md`. Listed here only for
audit-trail completeness.

## Out of scope (explicitly NOT this slice)

- CLA Assistant bot OAuth setup at https://cla-assistant.io — CEO-side
  GitHub OAuth authorization; not required for v0.1.0 since no external
  PRs are expected immediately.
- Trademark registration — defer to legal entity formation.
- `ailovestesting.com` DNS routing (Gap 2 of alpha-full) — CEO ops
  task; can be done after v0.1.0 release.
- Any `src/novetest/**` engine code modifications — none required.
- Any `tests/**` modifications — none required.
- Any adapter changes — section 2.5 equip-and-exercise does NOT apply
  (no adapter touched). Generic dev host suffices for verification.
- Updating `decisions/2026-05-14-install-script-hosting-url.md` — that
  decision's "before MVP launch" rollout step (CEO wires DNS) remains
  open until CEO completes Gap 2.
- Wholesale repo-root reorganization — keep changes additive (no
  renames of existing files).
- The existing `src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt`
  STAYS unchanged; the new repo-root `NOTICES.md` is additive and
  references it.

## v0.1.0 tag push procedure

After all files in sections 1-8 are committed to the worktree branch
AND Main Branch FF-merges to `main`:

1. Verify `ci.yml` is green on the merged HEAD:
   ```sh
   gh run list --workflow ci.yml --branch main --limit 3
   gh run view <run-id> --json jobs --jq '.jobs[] | {name, conclusion}'
   ```
   Cite the run number in your handoff.

2. Verify `gh release list --limit 5` shows no pre-existing `v0.1.0`
   draft/release that would conflict. If one exists from local
   experimentation, surface in a question — do NOT delete without
   CEO approval.

3. Create the tag and push:
   ```sh
   git tag -a v0.1.0 -m "Nove Test v0.1.0 — Phase 0 milestone, Apache 2.0 + CLA inaugural release"
   git push origin v0.1.0
   ```

4. `release-test.yml` will auto-trigger on the tag push:
   - 3 PyApp builds (linux-x86_64, linux-aarch64, macos-universal2) + `.sha256` sidecars
   - install-script-e2e smoke (localhost HTTP server fixture)
   - `release` job (only runs on tag push, not on workflow_dispatch):
     creates draft GitHub Release with all 6 artifacts via `softprops/action-gh-release@v3`

5. Verify the draft release exists:
   ```sh
   gh release view v0.1.0
   ```
   Confirm `isDraft: true` and 6 attached assets. Cite in your handoff.

6. **Do NOT promote the draft to public release.** That is a separate
   CEO action via GitHub UI (or `gh release edit v0.1.0 --draft=false`
   if CEO requests CLI promotion). The handoff explicitly notes this
   boundary.

## Empirical curl-pipe-sh smoke (NEW verification surface)

After the draft GitHub Release is created AND assets are attached,
run an empirical end-to-end test of the canonical install path using
the just-published v0.1.0 artifacts:

```sh
# Clean container or dev host
curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/v0.1.0/scripts/install.sh \
  | NOVETEST_INSTALL_VERSION=v0.1.0 sh
```

Expected:
- Install script downloads the binary from the v0.1.0 release
- SHA-256 verified
- `novetest --version --output json` returns valid `novetest/v1` envelope
- Re-running upgrades in place idempotently

This is THE proof that the alpha-full Gap 1 fix (REPO default) actually
works with real GitHub Releases artifacts, not just the localhost
smoke. Cite the output verbatim in your handoff.

**Asset propagation timing note**: GitHub Releases CDN propagation can
take 30-90 seconds after the `release` job completes. If the smoke
fails immediately, wait 2 minutes and retry once before surfacing as
a question.

## Definition of done

11 binding bullets:

1. [ ] `LICENSE` at repo root: unmodified Apache 2.0 text + Nove Lab 2026 copyright header per section 1 above
2. [ ] `CLA.md` at repo root: Apache ICLA adaptation per section 2 (Nove Lab Licensor + admin.nove@gmail.com contact + verbatim sections 1-7)
3. [ ] `CCLA.md` at repo root: Apache CCLA adaptation per section 3
4. [ ] `CONTRIBUTING.md` at repo root: CLA workflow per section 4
5. [ ] `NOTICES.md` at repo root: cyclopts + numpy + JUnit + PyApp + python-build-standalone attribution per section 5
6. [ ] `pyproject.toml`: `license = { file = "LICENSE" }` per section 6; `uv build` succeeds
7. [ ] `README.md`: License section per section 7 with admin.nove@gmail.com contact
8. [ ] `scripts/install.sh`: `REPO` default + comment updated per section 8
9. [ ] `uv run mypy --strict src/novetest`: no regression (source-file count unchanged, no new `src/` files)
10. [ ] `uv run pytest -q tests/unit tests/integration`: baseline maintained (1218 passed + 26 skipped + 1 pre-existing dotnet-host-equip failure per 2026-06-09 baseline; new exact numbers cited in handoff)
11. [ ] `ci.yml` post-merge run on `main` HEAD: 10/10 GREEN — cite run number in handoff

Plus the release-publication-specific bullets:

12. [ ] `v0.1.0` git tag pushed; `release-test.yml` run GREEN — cite run number
13. [ ] Draft GitHub Release `v0.1.0` exists with 3 binaries + 3 `.sha256` sidecars (6 assets total); cite `gh release view v0.1.0` output
14. [ ] Empirical curl-pipe-sh smoke from the v0.1.0 raw.githubusercontent.com URL succeeds; cite verbatim `novetest --version --output json` output
15. [ ] WORKLOG entry per format (section 1-8 modifications + install.sh: this slice DOES touch `scripts/` which the hook treats as eligible-not-required, but a WORKLOG entry is still useful documentation)
16. [ ] Handoff at `agent-comms/handoffs/release-team-2026-06-10-v0.1.0-license-and-tag-publication.md` with DoD bullets-believed-closed list
17. [ ] `python3 tools/regen_comms_index.py`

## Verification criterion (per meta-decision 2026-06-08)

CI matrix verdict per `agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md`
applies as **SHOULD tier** for this slice (no adapter modified;
license/distribution work):

- Post-merge `ci.yml` run on `main` must show 10/10 GREEN
- `release-test.yml` run on the v0.1.0 tag must show all jobs GREEN
- Both run numbers cited in handoff (DoD #11, #12)

Section 2.5 equip-and-exercise file-glob heuristic does NOT trigger
(no `adapters/*_adapter.py` modified, no `tests/integration/run/test_*_<engine>_*.py`
modified).

## Failure modes to anticipate (PM-pinned for Release team)

1. **`hatchling` may not accept `license = { file = "LICENSE" }` on
   older versions** — if `uv build` fails post-edit, check Hatchling
   version (`uv pip show hatchling`) and consider falling back to
   `license = "Apache-2.0"` (SPDX-string form, also valid). Surface in
   a question if neither form works.

2. **`v0.1.0` tag already exists** — if `gh release list` shows a
   pre-existing v0.1.0 (unlikely but possible from local
   experimentation), surface this in a question. Do NOT delete the
   existing tag without CEO approval.

3. **Draft release creation collision** — if `release-test.yml::release`
   tries to create a release that already exists,
   `softprops/action-gh-release@v3` should handle gracefully but
   verify the asset list in your handoff. If a partial state results,
   surface in a question.

4. **CDN propagation lag (DoD #14)** — see "Empirical curl-pipe-sh
   smoke" section above. Wait 2 minutes, retry once, only then
   surface as a question.

5. **CLA file legal review concerns** — the Apache ICLA/CCLA texts are
   battle-tested by 200+ ASF projects. If you have a specific clause
   concern during transcription (e.g., a phrase that seems odd in
   context), raise as a question for PM/CEO routing rather than
   silently modifying the standard text. Custom CLA drafting is
   explicitly out of scope per the decision document.

6. **NOTICES.md content discoveries** — if you discover additional
   bundled dependencies during the `pyproject.toml` + wheel audit, ADD
   them to NOTICES.md (don't drop them). Better complete than partial.

7. **README.md gets too long** — current README is 3 lines. The
   License section above is ~25 lines. That's fine — it stays small.
   Resist the temptation to add Quick Start / Install / Examples
   sections in this slice (separate work, defer to a docs cycle).

## Handoff "DoD bullets believed closed" list (template)

In your handoff include a section like:

```markdown
## DoD bullets believed closed for Phase 0 — PM to verify and tick

This slice closes (or re-empirically validates) the following bullets
in `design/implementation-plan/delivery-phasing.md`:

- Phase 0 section "Definition-of-done" bullet #1 (ci matrix) — re-validated at v0.1.0 tag's `ci.yml` run `<NUM>`
- Phase 0 section "Definition-of-done" bullet #4 (signed binary) — re-validated at v0.1.0 tag's `release-test.yml` run `<NUM>`
- Phase 0 section "Definition-of-done" bullet #5 (curl-pipe-sh end-to-end) — re-validated via empirical smoke per DoD #14 above
- Phase 0 section "Definition-of-done" bullet #6 (SHA-256 verify) — re-validated via the same empirical smoke

NEW closures (NOT in current `delivery-phasing.md` DoD — PM may add):

- License surface (LICENSE + CLA + CCLA + NOTICES + CONTRIBUTING + README)
- install.sh canonical URL Gap 1 closed (REPO default = Nove-Lab/Nove-Test)
- v0.1.0 milestone: inaugural public release published (as DRAFT, awaiting CEO promotion)
```

## Cycle close direction

After Manual Test verifies the handoff AND PM cycle-closes:

- CEO promotes draft GitHub Release `v0.1.0` to public via GitHub UI
  (or CLI: `gh release edit v0.1.0 --draft=false`)
- CEO separately handles `ailovestesting.com` domain routing (Gap 2 of
  alpha-full, out of scope here)
- PM may distill into a history entry capturing the inaugural release
  milestone

## Reporting back (in handoff)

- Worktree path / commit SHA
- Each new file's location + first 3 lines (or full diff for the small
  install.sh edits)
- `uv run mypy --strict` + `uv run pytest` results (full counts)
- `ci.yml` run number + URL for the post-merge HEAD
- `release-test.yml` run number + URL for the v0.1.0 tag
- `gh release view v0.1.0` output confirming draft + 6 attached assets
- Empirical curl-pipe-sh smoke command + verbatim `novetest --version --output json` output
- WORKLOG entry text
- Any release-pipeline surprises (per charter "Reporting back")
