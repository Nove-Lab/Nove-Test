---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-06-10
slug: license-apache-2.0-with-cla
related:
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - design/implementation-plan/foundations.md
  - design/implementation-plan/delivery-phasing.md
---

# Decision: Nove Test ships under Apache License 2.0 with a Contributor License Agreement

CEO-approved on 2026-06-10.

## Decision

Nove Test core (the test orchestration engine in this repository) ships
under the **Apache License, Version 2.0**, with a **Contributor License
Agreement requirement** for all external contributions.

Concretely:

1. `LICENSE` at repo root contains the unmodified Apache License 2.0
   text with a `Copyright 2026 Nove Lab` header.
2. `CLA.md` at repo root contains an adaptation of the Apache Software
   Foundation Individual Contributor License Agreement (ICLA), with
   Nove Lab as Licensor and `admin.nove@gmail.com` as the submission
   contact.
3. `CCLA.md` at repo root contains an adaptation of the Apache
   Software Foundation Corporate Contributor License Agreement (CCLA),
   for organization-affiliated contributors.
4. `CONTRIBUTING.md` documents the CLA Assistant bot workflow and
   points to the two CLA documents.
5. `pyproject.toml` declares `license = { file = "LICENSE" }` (replaces
   the no-force `text = "Proprietary"` placeholder).
6. `README.md` carries a "License at a glance" section pointing to
   `admin.nove@gmail.com` for commercial license inquiries.
7. Copyright holder is **"Nove Lab"** — a placeholder until a legal
   entity is formed. The string is updated in-place via a follow-up
   commit when the entity is registered; the underlying license choice
   does NOT change.

## Rationale

**Strategic intent**: maximize today's adoption surface while preserving
tomorrow's relicensing optionality.

Nove Test is an AI-agent-first CLI tool. Its primary distribution channel
is AI tool builders (Cursor, Claude Code, Cline, GitHub Copilot, etc.)
that either invoke it as a subprocess or embed it as a runtime. License
friction at this distribution layer translates directly to lost
adoption, and the project at v0.1.0 has zero users to amortize that loss
against. Restrictive licenses (BSL, AGPL, PolyForm Shield, ELv2) all
introduce procurement friction that makes AI tool integrators default
to "let's build our own test runner" rather than negotiate. The
strategic moat for an AI-agent CLI is not the code — it is the JSON
envelope schema becoming the de facto standard convention. Becoming the
standard requires permissive licensing.

**Why Apache 2.0 specifically (not MIT)**:

- Explicit patent grant — relevant for SBFL algorithms and any future
  AI-side IP.
- Patent termination clause if a licensee sues for patent infringement
  — defensive shield without ongoing enforcement cost.
- 11-page legal document with all the corner cases addressed; MIT is a
  paragraph and leaves more open to interpretation in enterprise
  procurement.
- SPDX-listed (`Apache-2.0`), recognized by every package registry,
  every GitHub license picker, every BigCo legal review checklist.
- 20+ years of battle-testing across thousands of projects.

**Why a Contributor License Agreement on top**:

By default, Apache 2.0 §5 ("Inbound = Outbound") means contributions
flow into the project under Apache 2.0 with no extra rights granted to
Nove Lab beyond what Apache 2.0 itself confers. This is fine for
ongoing maintenance but **does not give Nove Lab the unilateral right
to relicense future versions under different terms**.

The CLA closes that gap. Contributors retain copyright on their work
but grant Nove Lab a perpetual, worldwide, non-exclusive, royalty-free,
**sublicensable** license. With this grant in place, Nove Lab retains
the unilateral right to:

- Issue future versions under a different license (e.g., AGPL, BSL, or
  a commercial license) without contributor consent.
- Sell commercial dual licenses to specific organizations.
- Sublicense the codebase for downstream products (Nove Console, Nove
  Team) under proprietary terms.

The CLA is **not a copyright assignment**. Contributors keep their
copyright and can use their own code anywhere else they please. The
CLA only adds a Nove-Lab-side license grant on top.

**Why the Apache ICLA / CCLA templates** (not custom drafting): the
ASF ICLA has been the de facto industry standard for 20+ years
(Cassandra, Spark, Kafka, Airflow, OpenOffice, hundreds more). The
ASF CCLA is the same for organization-affiliated contributors. Custom
drafting introduces legal review burden + contributor mistrust ("why
is YOUR CLA different from everyone else's?") with no upside. Verbatim
adoption with Licensor substitution is the standard professional
move.

## What this decision rules in

- Any individual or organization may use Nove Test in production,
  internally, in commercial products, in derivative works, in managed
  services — subject only to the Apache 2.0 attribution clause (§4(a))
  and the patent-defense termination clause (§3).
- Commercial use including embedding into commercial products (e.g.,
  Cursor IDE bundling Nove Test as its test runner), building
  derivative SaaS offerings (e.g., a hypothetical "Acme Test
  Orchestration" running our engine), and consulting / training /
  support businesses are all permitted under Apache 2.0.
- PRs from individuals require Apache ICLA signature — one-time,
  automated via the CLA Assistant bot when external PRs begin to
  arrive.
- PRs from organization-affiliated contributors require Apache CCLA
  signature — one-time per organization, automated identically.
- Nove Lab retains the unilateral right to relicense future versions
  of the codebase (including code contributed by external parties
  under the CLA) under any terms, at any time, without contributor
  consent.

## What this decision rules out

- Custom CLA drafting: the Apache ICLA/CCLA texts are used verbatim
  with only the Licensor name + contact email substituted.
- Refusing PRs from contributors who decline the CLA: such PRs may be
  discussed for content but cannot be merged.
- Restricting commercial use through license terms: not possible under
  Apache 2.0. If commercial-use restriction becomes strategically
  necessary in the future, the path is a v0.X.0 release under a more
  restrictive license, exercising the CLA-preserved relicensing right;
  v0.1.0 and any other Apache-2.0-published versions remain Apache 2.0
  forever (forkable at that point).
- Copyright assignment to Nove Lab: contributors retain their
  copyright. This is the standard ASF / CNCF / Google pattern; it
  reduces contributor friction without weakening Nove Lab's practical
  rights.

## Strategic moves preserved (NOT decided here, but enabled)

- **Open core monetization**: future hosted products (Nove Console,
  Nove Team) are built as separate offerings on top of the
  Apache-2.0 engine, monetized independently. The engine being free
  is what makes those products' value visible.
- **Future relicensing if competitive threat materializes**: with CLA
  signatures collected from all contributors, Nove Lab can issue a
  v0.X.0 under a restrictive license (AGPL, BSL, FSL, or
  proprietary) without seeking individual contributor consent.
- **Trademark layer**: "Nove Test" and "novetest" can be registered
  as trademarks once a legal entity is formed. This protects the
  brand and prevents lookalike products even when the code is
  freely usable. Defer to legal-entity formation.

## Dependency-license compatibility

Confirmed no conflict at the time of this decision:

| Dependency | License | Conflict with Apache 2.0? |
|---|---|---|
| `cyclopts` >=3.0 (runtime) | Apache-2.0 | No (identical) |
| `numpy` >=1.26 (runtime) | BSD-3-Clause | No (permissive) |
| `pytest`, `mypy`, `coverage`, `syrupy`, `pytest-cov`, `pytest-json-report`, `pytest-asyncio` (dev) | MIT / Apache-2.0 | No (dev-only, not shipped) |
| `junit-platform-console-standalone-1.11.4.jar` (vendored sidecar) | EPL-2.0 | No — sidecar binary distributed unmodified per decision `2026-06-03-junit-console-launcher-vendor.md` |
| PyApp (install-time wrapper) | Apache-2.0 OR MIT | No |
| python-build-standalone CPython (PyApp first-run download) | PSF + permissive sub-components | No |

The vendored JUnit jar requires no change: per the 2026-06-03 decision,
that file ships unmodified with its own NOTICES sidecar inside the
wheel. Nove Lab does not modify the jar; the EPL-2.0 source-disclosure
obligations do not engage.

The repo-root `NOTICES.md` introduced in this cycle aggregates
attribution for `cyclopts` and `numpy` (pip-dep expansion deferred from
prior cycles' Future-cycle queue #2) alongside a pointer to the
existing `src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt`
for the JUnit attribution.

## Affected files / teams

This decision triggers a single packed Release-team cycle that lands:

1. `LICENSE` (Apache 2.0)
2. `CLA.md` (Apache ICLA adaptation)
3. `CCLA.md` (Apache CCLA adaptation)
4. `CONTRIBUTING.md` (CLA workflow)
5. `NOTICES.md` (repo-root third-party attribution)
6. `pyproject.toml` (license metadata)
7. `README.md` (License section + commercial contact)
8. `scripts/install.sh` (REPO default fix — alpha-full Gap 1)
9. `v0.1.0` git tag push -> `release-test.yml` -> draft GitHub Release

Brief at `agent-comms/tasks/release-team-2026-06-10-v0.1.0-license-and-tag-publication.md`.

PM (this commit) also updates `design/implementation-plan/foundations.md`
section 7 to cite this decision.

## Non-binding follow-ups (NOT this cycle)

Three operational items are NOT part of this decision and may be
scheduled separately by the CEO:

- **CLA Assistant bot OAuth setup** at https://cla-assistant.io —
  requires CEO-side GitHub OAuth authorization. Not required for the
  v0.1.0 cut (no external PRs expected immediately); CEO completes
  when first external PR arrives.
- **Legal entity formation** — once Nove Lab is registered as an LLC /
  Inc. / 주식회사 / similar, the Licensor string in `LICENSE`, `CLA.md`,
  `CCLA.md` is updated via a clean in-place edit. Non-binding
  amendment, no new decision document needed.
- **Trademark registration** — registering "Nove Test" / "novetest" as
  a trademark is recommended once a legal entity exists. Estimated
  $3-5k USD, 6-12 months. Filing under an individual is possible but
  less protective; defer to legal entity formation.

Also non-binding and informational only:

- **Dead-man's switch commitment** — the option of adding a non-
  binding README statement that Nove Test will auto-fall-back to
  Apache 2.0 if Nove Lab ceases active development for 12 consecutive
  months was discussed during the decision conversation. Under Apache
  2.0 with this decision the engine is ALREADY permissively licensed,
  so the fall-back statement adds zero protection. NOT adopted.

## Effective date

2026-06-10.

## Supersedes

Resolves the implicit `pyproject.toml::license = { text = "Proprietary" }`
placeholder, which carried no legal force and was never CEO-approved.
The MVP release-ready milestone empirically captured at 2026-06-09
(`8ae90cd`, history entry `2026-06-09-mvp-release-ready-positive-sign-off.md`)
was the technical precondition for this decision; without a passing CI
matrix and a working release pipeline, the license choice would have
been premature.

## Future amendments anticipated

- Once legal entity formed -> Licensor string update across `LICENSE`,
  `CLA.md`, `CCLA.md` (single PM commit, no decision update needed).
- If a competing-product threat materializes after wide adoption ->
  v0.X.0 relicensing under more restrictive terms using the CLA-
  preserved right. Would be a NEW decision document, not an amendment
  to this one.
- If the Apache ICLA / CCLA texts are revised upstream by the Apache
  Software Foundation -> consider adopting the new revision in a clean
  amendment, optional.
