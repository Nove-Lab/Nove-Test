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
