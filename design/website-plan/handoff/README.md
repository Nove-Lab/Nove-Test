# novetest Marketing Website — Build Package

**This bundle is everything an external team needs to design and build the novetest marketing
website.** It stands alone: you do **not** need access to any source code, internal tools, or
prior discussions. Everything required is restated here.

- **Product name:** `novetest` (always lowercase). novetest is **free and open source (Apache-2.0).**
- **Website domain:** `ailovestesting.com`
- **This package version:** v3, 2026-06-01 — **ready to ship.**

## What's in this bundle

| File | Contents |
|---|---|
| `README.md` (this file) | Product overview, the product family, target audience, the website's goal, constraints, items to confirm. |
| `site-requirements.md` | The build spec: positioning & messaging, the hero, required page sections (with draft copy), the status-badge system, functional + non-functional requirements. |
| `assets-and-links.md` | Confirmed links, the assets we owe you (with owners), and brand/legal constraints. |

Read this file first, then `site-requirements.md`, then `assets-and-links.md`.

---

## 1. What novetest is

**novetest is a free, open-source, AI-first test orchestration command-line tool. It turns each
test run into stored, comparable, reproducible evidence — and into a clear, cited recommendation
for the next coding step.**

It does **not** replace the test runners developers already use (pytest, JUnit, jest, go test,
cargo test, dotnet test). It **wraps** them and adds memory, comparison, fault-localization, and
recommendation on top — all running **locally** on the user's machine.

### The problem it solves
AI coding agents now write and change code faster than anyone can verify it by hand. The
bottleneck has shifted from *writing* code to *trusting* it. A plain test runner answers "did it
pass?" and throws everything else away. The deeper analysis (what regressed, where the fault is,
whether a failure is flaky) usually lives far away in a CI pipeline or a cloud platform — too slow
and too distant for an AI agent's fast inner loop. novetest closes that gap: testing becomes a
**cumulative, machine-readable loop that runs locally**, in cadence with the agent's iterations.

### How it works
Six engines around one loop: `Execute → Store → Structure → Compare → Locate → Validate → Recommend`.
**Run** executes via the native engine you already use; **Memory** stores every run as durable,
citable evidence; **Coverage** structures what each test exercised; **Regression** compares runs;
**Localization** ranks the most suspicious code locations; **Replay** tells a stable failure from a
flaky one. On top sits one **recommendation layer** that assembles the facts into a short,
prioritized, **evidence-cited** next step.

### What makes it distinctive (the order matters)
1. **Deterministic and trustworthy — no LLM inside.** Fixed rule-based and statistical algorithms;
   the same inputs always give the same output; every recommendation cites its evidence. The #1
   message.
2. **Local and private.** Runs in a per-project folder on the user's machine; no cloud, no account,
   no upload.
3. **Free and open source (Apache-2.0).** novetest is free to use and its source is public on GitHub.
4. **Cloud-grade analysis, brought local.** Regression detection and fault localization — normally
   CI/cloud — run in the local inner loop, fast.
5. **Built for the AI coding loop.** The agent is the primary user; structured (JSON) output; the
   human supervises with the same facts.

### What novetest is NOT
Not a new test framework · not a cloud service/SaaS · **not an AI/LLM product** (no model inside;
it *serves* agents) · not a CI pipeline or background watcher/daemon · not a test-engine installer.

### Supported ecosystems
Python (pytest), JavaScript/TypeScript (jest), Java (JUnit 5), Go (go test), Rust (cargo test),
.NET (dotnet test). Platforms: Linux & macOS today (Windows is planned).

---

## 1b. The Novetest family (product line)

novetest is the **free, open-source foundation** of a planned product family. The website presents
all three, each with a status badge. **Only novetest is free / open source** — make **no pricing or
free claims** about the others (their pricing is not decided).

| Product | Badge | What it is |
|---|---|---|
| **novetest** | **Live / Building** | The free, open-source (Apache-2.0) CLI with the six engines. The foundation, available now. |
| **Novetest Console** | **Planned** | A dashboard for the **human user** — a visual home to explore novetest's runs, history, regressions, fault localizations, and recommendations, beyond the terminal. |
| **Novetest Team** | **Planned** | A product for **teams** building on novetest — shared test-suite management and TDD collaboration across team members. |

Console and Team are **peer products** to novetest (the same level), not engines inside it.

---

## 2. Who the website is for

A **pair** on the same project: the **AI coding agent — the primary / hero user** (calls novetest
in its loop, consumes the structured output), and the **human developer — the supervisor** (reviews
and acts on the same recommendations). Both see the **same facts**. The audience is technical —
write with developer credibility, not hype.

---

## 3. The website's goal

A single landing page that (1) communicates the positioning **trust-first** (deterministic,
reproducible, local), (2) emphasizes novetest is **free and open source (Apache-2.0)**, (3) makes
the value tangible fast (install → run → result), (4) shows the **complete vision** — every module
and family product, each badged by maturity — and (5) converts the visitor to **install**.

---

## 4. Constraints (stated by us)

- **Brand name:** always `novetest`, lowercase. **Brand architecture:** *Novetest* (capitalized) =
  the product family; *novetest* (lowercase) = the core open-source CLI; family products = *Novetest
  Console*, *Novetest Team*.
- **Free & open source:** emphasize prominently that novetest is free and open source under the
  **Apache-2.0** license.
- **Brand feel:** an homage to **iLovePDF** (`ilovepdf.com`) in clarity, but **more modern and geeky
  / developer-flavored.** Detailed visual identity (logo, colors, type) is **not yet decided**.
- **Voice & tone:** developer-credible, precise, confident, anti-hype. Never imply novetest is
  itself an AI/LLM — it is the deterministic layer the AI relies on.
- **Honesty rule (binding):** the product is mid-build. **Every capability claim carries its status
  badge** (Live / Building / Planned) and matches the maturity table in `site-requirements.md`.
  Never present Building/Planned as available today.
- **Privacy consistency:** the product's promise is "nothing leaves your machine," so the site
  itself should avoid heavy third-party tracking. Prefer privacy-respecting / cookieless analytics,
  or none.
- **Platforms:** Linux & macOS today; Windows is Planned.

---

## 5. Items to confirm with us (optional; none block the build)

- **Site scope:** v1 is a single landing page; confirm if you also want a docs/quickstart page now.
- **Docs/quickstart URL**, **secondary CTA (waitlist) y/n**, **analytics choice**, **launch
  deadline**.
- **Visual identity:** logo, color palette, typography are pending from us.
