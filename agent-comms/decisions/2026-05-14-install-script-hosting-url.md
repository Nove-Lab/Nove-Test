---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-14
slug: install-script-hosting-url
---

# Decision: install script hosting URL + brand namespace principle

CEO-approved on 2026-05-14. Resolves Open Question #15 in
`design/implementation-plan/delivery-phasing.md`.

## Decision

The canonical one-line install URL for the novetest core product is:

```
curl -fsSL https://ailovestesting.com/novetest/install.sh | sh
```

And the binding **brand namespace principle** for the whole product family:

- **Static assets** (install scripts, docs, landing pages) → **path-namespaced
  under the single brand domain** `ailovestesting.com`, one path segment per
  product: `ailovestesting.com/<product>/...`.
- **Future interactive web apps** (e.g. a paid console / dashboard) → **their
  own subdomain** (`console.ailovestesting.com`, `app.ailovestesting.com`, ...).
  Not decided here; flagged so the namespace stays clean when that day comes.

## Rationale

- The project is a **product family**, not a single tool: `novetest` core today,
  `novetest-team` / `novetest-console` and other (some paid) products later.
  The URL structure must scale to N products, not be optimized for one.
- Path-namespacing under one brand domain: scales at **zero marginal cost** per
  product (no new domain or subdomain purchase/setup), keeps a single brand
  umbrella, single DNS zone / SSL cert / management point.
- Keeps install / docs / landing URLs **parallel and predictable**:
  `ailovestesting.com/novetest` (landing) · `/novetest/install.sh` (install) ·
  `/novetest/docs` (docs).
- Proven pattern — `uv` ships exactly this shape (`astral.sh/uv/install.sh`):
  company/brand domain + product-name path.
- `.sh` extension kept deliberately for **transparency**: `curl | sh` users are
  expected to inspect the script first; the extension makes intent obvious.
- `get.` subdomain dropped — once the product name lives in the path, a `get.`
  prefix is redundant and nesting (`get.novetest.ailovestesting.com`) is too
  long. Bare brand domain + path is cleaner.

## Rollout (non-blocking)

- **Now:** Release Team continues to use the raw GitHub URL
  (`https://raw.githubusercontent.com/...`) for `release-test` validation —
  already specified in `tasks/release-team-2026-05-14-phase0-ci-and-distribution.md`.
  No task change needed.
- **Before MVP launch:** CEO wires DNS + hosting so
  `https://ailovestesting.com/novetest/install.sh` rewrites/redirects to the
  repo's `scripts/install.sh`. A subdomain is **not** required — this is a path
  route on the brand domain, zero additional purchase. PM issues a follow-up
  task to Release at that point.
- **Refinement (later, non-blocking):** pin the redirect target to a released
  tag of `scripts/install.sh` rather than the `main` branch, so the public
  install path is immutable per release.

## Affected teams / files

- **Release Team** — owns `scripts/install.sh` (the in-repo file keeps its
  `scripts/install.sh` path; only the *public-facing URL* is decided here),
  `.github/workflows/**`, and install documentation.
- **PM** — follow-up doc edit: update `delivery-phasing.md` Open Question #15
  row (mark resolved, link this decision) and `foundations.md` §7 (Distribution)
  wording. Hand the diff to CEO before commit per convention.
- **All teams** — the namespace principle above is binding for any future
  product addition; no re-litigation needed per product.

## Effective date

2026-05-14.

## Supersedes

None. First decision on distribution URLs. Resolves Open Question #15.


---

## Amendment 2026-06-10 — Interim primary install URL for v0.1.1 launch

**Context**: The 2026-06-10 v0.1.1 launch cycle (first public-facing
Nove Test release) proceeds before the original rollout step "CEO wires
DNS + hosting so https://ailovestesting.com/novetest/install.sh
rewrites/redirects to the repo's scripts/install.sh" has been completed.
The `ailovestesting.com` domain is registered but homepage hosting +
path routing are deferred to a later cycle when the marketing/homepage
team activates.

**Interim policy**: README's primary install surface uses the
**GitHub raw URL** as a 1:1 functional equivalent:

```bash
curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh | sh
```

This is NOT a policy reversal. The canonical brand URL
`https://ailovestesting.com/novetest/install.sh` remains the binding
target per the original Decision §"Decision" + §"Brand namespace
principle". `scripts/install.sh`'s in-file header keeps citing the
canonical URL as the "canonical user invocation" — only the README's
externally-visible primary URL is temporarily the raw GitHub form.

**Why this is safe**:

1. The raw GitHub URL is permanent as long as the repository at
   `Nove-Lab/Nove-Test` exists on its `main` branch.
2. `scripts/install.sh`'s URL composition logic (`NOVETEST_INSTALL_BASE_URL`
   env var + version-resolution machinery) works transparently against
   either URL.
3. The transition from raw URL to canonical URL is a single-line
   README edit; no `install.sh` change, no tag re-cut, no breaking
   migration.

**Migration plan when DNS is wired** (later CEO-triggered cycle):

1. CEO sets up Cloudflare Page Rules (Free tier, 3 rules included):
   - URL pattern: `ailovestesting.com/novetest/install.sh`
   - Setting: Forwarding URL (301 or 302)
   - Destination: `https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh`
2. Verify with `curl -fsSL https://ailovestesting.com/novetest/install.sh | head` from a clean host.
3. PM updates README primary install URL via single-line edit.
4. (Optional) Pin Page Rule destination to a specific tagged version
   per the original Decision §"Rollout / Refinement (later, non-blocking)":
   "pin the redirect target to a released tag of `scripts/install.sh`
   rather than the `main` branch, so the public install path is
   immutable per release."

**Status of original §"Rollout / Before MVP launch" step**: STILL
PENDING (not retired). The interim raw GitHub URL is a stop-gap, not
a replacement. The canonical brand URL remains the target end state.

The raw GitHub URL remains supported indefinitely as a fallback /
alternative install path even after the canonical URL is wired —
similar to how many projects ship multiple equivalent install URLs
for redundancy and inspect-first transparency.
