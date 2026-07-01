---
slug: install-path-website-integration
from: novetest-pm-team
to: novetest-marketing-pm-team
created: 2026-06-30
status: pending
amended: 2026-07-01
---

# Request — Install-path integration into ailovestesting.com

**Filed:** 2026-06-30 · **From:** PM (engineering) · **To:** Marketing PM · **Routes to:** external website team via handoff package

---

## Amendment 2026-07-01 — URL path migration + hosting already done externally

Two things changed after this brief was filed:

1. **URL paths moved** — `ailovestesting.com/novetest/install.{sh,ps1}` → `ailovestesting.com/products/novetest/install.{sh,ps1}`. All URL text in §§2–3 and §6 below has been mechanically rewritten to the new path. Rationale + the amended canonical URLs are recorded in `agent-comms/decisions/2026-05-14-install-script-hosting-url.md` §"Amendment 2026-07-01".
2. **Hosting already done by the external website team** — as of 2026-07-01 the external team is already serving both scripts at the new URLs and has retired the old `/novetest/…` paths (they now 404). §2.1 hosting delivery and the sync-model choice in §2.2 are therefore **closed externally**.

**What still remains actionable for Marketing PM** (the residual value of this brief):

- §3.1 `site-requirements.md` S11 stale-fact fix — Windows-Live text + add Windows one-liner.
- §3.2 `assets-and-links.md` §1 & §5 — add Windows install rows, replace Windows-Planned text, bump status date.
- §3.3–§3.5 — the smaller docs / README / top-level plan touch-ups.
- The `install.{sh,ps1}` **comment/URL updates inside the Nove-Test repo** (this repo — `scripts/install.{sh,ps1}`, decision doc, foundations, delivery-phasing) were applied directly by PM on 2026-07-01 to unblock a marketing-team request; Marketing PM does **not** need to route those.

**Verification (§2.3) is no longer a Marketing PM deliverable** — the external team owns the acceptance test against staging.

---

---

## 0. Why this request exists

The website (`ailovestesting.com`) is in final build and the handoff bundle already **reserves space** for the install-path integration:

- `handoff/site-requirements.md` **S11 (Get started / install)** — section is specified, copy is drafted with a placeholder install URL.
- `handoff/assets-and-links.md §1` — already declares the canonical install URL as `https://ailovestesting.com/products/novetest/install.sh` (branded host, decided pre-2026-06-01).

Two things have changed since `2026-06-01` (the date stamped on the handoff package) that make the current copy **stale** and the integration not yet executable:

1. **Windows is now Live.** Windows install pipeline shipped 2026-06-18 (`scripts/install.ps1`, PyApp `.exe`, SHA-256 verification, 1st-class CI gate). Yet `site-requirements.md` S11 and `assets-and-links.md §5` both still say *"Linux & macOS today; Windows is Planned."*
2. **A second install script now exists** (`scripts/install.ps1`) that the website needs to host **in addition to** `install.sh`. `assets-and-links.md` only lists the Linux/macOS script.

This request asks the Marketing PM to amend the handoff package so the external website team has everything they need to ship the install path **as planned**.

---

## 1. Scope of this request

| In scope | Out of scope |
|---|---|
| What the install section on the landing page must show | Designing the visual treatment of S11 |
| Which URLs the website serves and how they stay synced with the canonical scripts | Hosting the **binaries** (those stay on GitHub Releases — no change) |
| Stale-fact updates triggered by Windows-Live (S11, Part C, §5) | Re-opening positioning / messaging / hero copy |
| The sync/freshness contract for the install scripts | OS auto-detection on the page (nice-to-have, not required) |

---

## 2. What the website must serve

### 2.1 Branded install URLs (canonical, user-facing)

| Path on `ailovestesting.com` | Serves (byte-identical to) | Why it's needed |
|---|---|---|
| `/products/novetest/install.sh` | `Nove-Lab/Nove-Test:scripts/install.sh` @ latest tagged release | Linux + macOS one-line install |
| `/products/novetest/install.ps1` | `Nove-Lab/Nove-Test:scripts/install.ps1` @ latest tagged release | **NEW** — Windows one-line install |

Both files are small (each <10 KB), text-only, and **safe to mirror byte-for-byte**. The scripts themselves perform SHA-256 verification of the downloaded binaries against sidecars on GitHub Releases — no integrity gate at the hosting layer is required.

**Content-Type:**
- `/products/novetest/install.sh` → `text/x-shellscript; charset=utf-8`
- `/products/novetest/install.ps1` → `text/plain; charset=utf-8` (PowerShell has no registered MIME; plain text is fine because `irm | iex` doesn't care about Content-Type)

**Cache-Control:** short TTL — recommend `max-age=300` (5 min) so a fresh release reaches users quickly.

### 2.2 Sync / freshness contract

The website's `/products/novetest/install.sh` and `/products/novetest/install.ps1` MUST be **byte-identical** to the files in the canonical repo (`Nove-Lab/Nove-Test:scripts/install.sh`, `scripts/install.ps1`) at the **latest tagged GitHub Release** of `novetest`.

Cadence: at minimum, refresh on every novetest release (currently ~monthly; trigger = a new `vX.Y.Z` tag on `Nove-Lab/Nove-Test`).

Three acceptable implementation models — **website team picks one**:

| Model | How it works | Pros | Cons |
|---|---|---|---|
| **A — Edge proxy / redirect** | `/products/novetest/install.sh` 301/302 → `raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.sh` (or pinned to a release tag) | Zero sync logic; always current | Reveals GitHub on TLS handshake / redirect chain; loses branded host for the actual fetch |
| **B — CI-pulled mirror (recommended)** | Website's deploy pipeline pulls the two files from GitHub on each build and serves them statically from `ailovestesting.com` | Branded URL all the way through; trivially CDN-cached; rebuild = refresh | Requires the website to redeploy when novetest releases (or run a scheduled refresh) |
| **C — Manual sync** | We (novetest team) push the two files on every release | No website-side automation | Highest operator load; easy to forget |

**Our recommendation: B.** Either tie the sync to a webhook on `Nove-Lab/Nove-Test` releases, or schedule a daily cron. The novetest side will mark this request closed once the website serves the correct content on both paths.

### 2.3 Verification (acceptance test the website team can run)

On a clean Linux machine without `novetest` installed:

```bash
curl -fsSL https://ailovestesting.com/products/novetest/install.sh | sh
~/.local/bin/novetest --version
# expect: installedVersion is the latest release (currently 0.1.2)
```

On a clean Windows PowerShell:

```powershell
irm https://ailovestesting.com/products/novetest/install.ps1 | iex
& "$HOME\.local\bin\novetest.exe" --version
# expect: installedVersion is the latest release (currently 0.1.2)
```

Both must complete cleanly (exit 0) within roughly 5–15 seconds on a typical runner (PyApp first-run cold start).

---

## 3. Updates to the handoff package (please apply)

### 3.1 `design/website-plan/handoff/site-requirements.md`

| Location | Current text | Replace with |
|---|---|---|
| **S11 — Get started / install** | *"Linux & macOS today (Windows — Planned)"* | *"Linux, macOS, and Windows — all Live."* |
| **S11 install command (the single copyable line)** | `curl -fsSL https://ailovestesting.com/products/novetest/install.sh \| sh` (already correct) | Keep — **add a sibling PowerShell command** for Windows: `irm https://ailovestesting.com/products/novetest/install.ps1 \| iex` |
| **S11 quickstart** | `install → novetest init → novetest test` (already correct) | Keep |
| **Part C — Current maturity mapping** | *"Planned: Windows support."* | **Remove this line.** Windows is now Live. |
| **Part C — Engines line** | Current text accurate | Keep (engine-coverage badges separately tracked) |

If S11's tile layout supports one tab per OS (For Linux/macOS / For Windows), please reflect that — otherwise show the two one-liners stacked, with the curl-pipe-sh command first (the most common visitor environment) and the PowerShell line directly under it with a small "Windows" label.

### 3.2 `design/website-plan/handoff/assets-and-links.md`

| Section | Change |
|---|---|
| **§1 — Confirmed links** | Add a row: `Install script — Windows (raw) \| https://ailovestesting.com/products/novetest/install.ps1` |
| **§1 — Confirmed links** | Add a row: `One-line install (Windows) \| irm https://ailovestesting.com/products/novetest/install.ps1 \| iex` |
| **§5 — Brand, tone & legal constraints** | Change `Platforms: Linux & macOS today; Windows is Planned.` → `Platforms: Linux, macOS, and Windows — all Live as of 2026-06-18.` |
| **Header status date** | Update `Status as of 2026-06-01` → `Status as of 2026-06-30` |

### 3.3 `design/website-plan/handoff/docs/installation.md`

This page is already accurate (it documents the real GitHub Raw URLs and the Windows command). **Two small adjustments** for consistency with the new landing-page install:

- §1 (Linux + macOS) — additionally show the branded one-liner as the **primary**, with the GitHub Raw command immediately under it as the "direct source" alternative for inspect-first users. Same for Windows.
- A one-line note: *"`ailovestesting.com/products/novetest/install.sh` is a byte-identical mirror of the script in the repo; either URL works."*

### 3.4 `design/website-plan/handoff/README.md`

After landing the changes above, refresh:

- The "Status: ready to ship" banner — re-confirm or note that the install-path delta is the last addendum.
- Add a short pointer: *"Install path: hosted at `ailovestesting.com/products/novetest/install.sh` and `/install.ps1`; sync contract in site-requirements.md §S11 / assets-and-links.md §1."*

### 3.5 Top-level `design/website-plan/README.md`

Update the table of `handoff/` contents and the "still pending" section if anything material shifted. Update `**Status: ready to ship.**` with the date of this amendment.

---

## 4. Coordination with the external website team

The Marketing PM owns the handoff bundle and the route to the external website team. Once §3 amendments are applied, please:

1. Flag the install-path delta in the team's normal channel (one short note: *"S11 updated — Windows now in scope, second install URL `/products/novetest/install.ps1` added; please pick a sync model per §2.2"*).
2. Confirm the team's choice of sync model (A / B / C) and capture it in `assets-and-links.md` (or a new file under `handoff/` if it warrants its own page — e.g. `handoff/install-hosting-contract.md` — your call).
3. Once the website serves the two paths in staging and the verification commands in §2.3 succeed, mark this request closed.

---

## 5. Deliverables checklist (for Marketing PM)

- [ ] `site-requirements.md` S11 + Part C updated (§3.1)
- [ ] `assets-and-links.md` §1 + §5 + status date updated (§3.2)
- [ ] `docs/installation.md` adjusted for branded-URL primary (§3.3)
- [ ] `handoff/README.md` updated (§3.4)
- [ ] Top-level `design/website-plan/README.md` updated (§3.5)
- [ ] External website team informed; sync-model decision captured (§4)
- [ ] Acceptance test in §2.3 passes against staging — request closed

---

## 6. Reference — what the install scripts actually do

For the website team's reference (in case they want to validate before hosting):

- Both scripts (`install.sh`, `install.ps1`) are sudo-free, idempotent (re-running upgrades in place via atomic rename), and abort loudly on SHA-256 mismatch rather than write a partial binary.
- They write to `~/.local/bin/novetest` (Linux/macOS) or `%USERPROFILE%\.local\bin\novetest.exe` (Windows).
- They download from GitHub Releases (`github.com/Nove-Lab/Nove-Test/releases/...`) — that endpoint stays canonical for binaries; we are **only** asking the website to mirror the two **install scripts**, not the binaries.
- Default behavior: install latest release. Pinned version via `NOVETEST_INSTALL_VERSION=vX.Y.Z`. (Documented in `handoff/docs/installation.md`.)

Full content of both scripts is in the canonical repo at `scripts/install.sh` and `scripts/install.ps1`.

---

## 7. Out of scope (do not block on these)

- Binary hosting / SHA-256 mirroring at `ailovestesting.com` — not requested.
- OS-detection on the landing page (auto-select Linux vs Windows command) — nice-to-have, not required for v1.
- Multi-arch dropdown UI in S11 — not requested.
- Translating the install section into other languages — i18n still v1-deferred.
