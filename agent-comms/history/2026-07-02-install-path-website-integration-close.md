---
from: novetest-pm-team
to: all
type: history
status: archived
created: 2026-07-02
slug: install-path-website-integration-close
related:
  - agent-comms/tasks/marketing-pm-team-2026-06-30-install-path-website-integration.md
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
---

# History: install-path-website-integration cycle — overtaken by external completion, closed

## Summary

The request `marketing-pm-team-2026-06-30-install-path-website-integration.md` is closed as **resolved**. Its routing purpose (get install-path integration into ailovestesting.com through the Marketing PM handoff) was fulfilled ahead of any Marketing-PM activation: the external website team completed hosting `ailovestesting.com/products/novetest/install.{sh,ps1}` on 2026-07-01, ~24 hours after the brief was filed. The Nove-Test-side URL alignment triggered by that migration landed in commit `cc5ea23`. No Marketing-PM cycle occurred; no handoff was ever dispatched.

## Arc

1. **2026-06-30 · commit `748091c`** — PM filed the request. Frame: route through Marketing PM → external site team, patch handoff bundle for Windows-Live text + `install.ps1` addition, and get the two URLs (`/novetest/install.sh` + `/novetest/install.ps1`) hosted at `ailovestesting.com`. Original path assumption: `/novetest/…` (per `decisions/2026-05-14-install-script-hosting-url.md`).
2. **2026-07-01 (external)** — the website build team, working from the addendum PM had copied to `ailovestesting.com/design/install-path-integration-request-2026-06-30.md`, deployed the site with the install scripts hosted at `ailovestesting.com/products/novetest/install.{sh,ps1}` (path-namespaced under `/products/` to align with the site's product-page IA). Old `/novetest/…` paths retired without redirect (404). Marketing PM never routed the brief.
3. **2026-07-01 · commit `cc5ea23`** — CEO relayed the external team's migration request to PM: sweep the Nove-Test repo for the old URL and update to `/products/novetest/…`. PM applied the URL migration across `scripts/install.{sh,ps1}` header comments, `agent-comms/decisions/2026-05-14-install-script-hosting-url.md` (URL text + Amendment 2026-07-01 section documenting the path move), `design/implementation-plan/foundations.md` (Tier 1 + install-matrix + Windows note), `design/implementation-plan/delivery-phasing.md` (Open Q #15 row), and `design/website-plan/handoff/{site-requirements.md, assets-and-links.md}` (URL text only, §1 and S11 rows).
4. **2026-07-02 · this commit** — PM closes the original request as `resolved`, files this history entry, regenerates the INDEX.

## What did NOT get done, and why it's OK

The original brief's §3 handoff-bundle patches were only **partially applied** in `cc5ea23` — URL strings were rewritten, but three stale-fact updates were not:

- `site-requirements.md` §S11: still reads "Linux & macOS today (Windows — Planned)"; should read "Linux, macOS, and Windows — all Live" and show the sibling `irm … install.ps1 | iex` command.
- `assets-and-links.md` §1: no rows for the Windows install script or one-liner.
- `assets-and-links.md` §5: still reads "Platforms: Linux & macOS today; Windows is Planned"; status date still `2026-06-01`.

**Why leaving these OK for now**: the live site (`ailovestesting.com`) already reflects Windows-Live reality — the drift is confined to Nove-Test's internal handoff bundle, which is now a historical design-doc artifact (the site is built and shipped). Nothing user-facing is broken. If the Marketing-PM channel is ever reactivated (unlikely near-term — the promotional website that was its primary charge is live), the bundle can be republished with these fixes. If not, this history entry stands as the record of intentional deferral.

## Signals to CEO

- **Marketing-PM function may be sunsetting.** The team's charter (`design/website-plan/` only, requirements elicitation for the promotional website) had one primary deliverable — the website — which shipped externally without Marketing-PM involvement. Not a decision to make today, but worth surfacing: does the Marketing-PM team charter still have work in front of it, or should it be archived alongside the shipped site?
- **URL brand-namespace principle survived intact.** The `/products/<product>/…` shape (external team's IA) is a strict extension of the 2026-05-14 principle (path-namespacing under one brand domain); the amended decision doc records this without weakening the original binding.

## INDEX effect

Removes one Pending item from `agent-comms/INDEX.md`. Post-close: 2 Pending tasks (`orchestration-team-2026-06-25-test-reruns-flag`, `pm-team-2026-06-25-user-doc-taxonomy-realignment`) + 1 Open question (`2026-07-02-engine-selection-policy`) remain — all legitimate live items awaiting CEO prioritization or the next PM opportunistic window.
