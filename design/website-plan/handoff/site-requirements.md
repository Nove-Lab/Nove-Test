# novetest Website — Build Spec

Self-contained build specification for the novetest marketing landing page. Read `README.md`
(product overview, the product family, audience, goal, constraints) first. Companion:
`assets-and-links.md`.

**v1 shape:** a single rich landing page on `ailovestesting.com` with sticky anchor navigation.
All copy below is a **starting draft** — refine it; keep the meaning and the ordering.

---

## Part A — Positioning & messaging

### A1. Brand line (the category)
> **"Continuous local testing intelligence for AI-generated code."**

Position novetest as a **category** — an on-device intelligence layer that keeps AI-generated code
verified as it evolves — **not** a wrapper around test engines, and **not** a grab-bag of utilities.

### A2. The message hierarchy (state in this order, everywhere)
1. **Trust — deterministic & reproducible (first, always).** No LLM in the analysis path; the same
   inputs always give the same output; every recommendation cites its evidence. Leads, including in
   the hero.
2. **Local & private.** Runs in a per-project folder on the user's machine; no cloud, no account,
   no upload; works offline; no per-use token cost.
3. **Cloud-grade intelligence, brought local.** Regression detection and fault localization —
   normally CI/cloud — run in the local inner loop, fast. Headline: **"Cloud-grade test analysis.
   No cloud."**
4. **Built for the AI coding loop.** The agent is the hero user; structured JSON output and stable
   exit codes; the human supervises with the same facts.

### A3. The category narrative — define "continuous" on the page
"Continuous testing" is normally a cloud/CI discipline. novetest deliberately relocates it to the
local machine. Make this explicit so no one mistakes it for a CI pipeline or a file-watch daemon:

> *"Continuous testing used to live in your CI pipeline. novetest brings it down to your machine —
> into the AI coding loop, where every change needs checking now, not 20 minutes later in CI. It
> runs in cadence with your agent's loop, not a background daemon you configure."*

### A4. Product shape — two abstractions (use these to frame the functional summary)
- **Polyglot: multi-language testing, one tool.** Wraps whatever native engine each project already
  uses — one tool across ecosystems, not a new framework.
- **A living system of engines, continuously interacting.** Not a single feature but a set of
  testing-supportive engines that continuously interact — each run's facts feed the next.

### A5. The trust angle (the most ownable story)
> *"Your AI writes the code. A deterministic engine you can actually trust checks it — locally, the
> same way every time."*

### A6. Voice & tone
Developer-credible, precise, confident, anti-hype, modern + geeky. Real terminal/JSON output is
welcome. Frame novetest as the **deterministic facts-and-analysis layer the agent relies on** — the
agent brings the reasoning, novetest brings facts it can trust. Read "intelligence" the way you read
"business intelligence" (analysis software), **not** as another AI agent — the deterministic /
no-LLM / serves-the-agent copy already conveys this, so **no explicit "we're not an agent"
disclaimer is needed.** Never imply novetest is itself an AI/LLM.

---

## Part B — The hero

- **Eyebrow / badge (small, above or beside the headline):** **"Free & open source"**.
- **Headline (decided):**
  **"Accelerate your coding agents with continuous, reproducible, local test intelligence."**
- **Subhead (carries determinism + no-cloud + trust):**
  *"No LLM, no cloud — the same result every run, all on your machine. Test intelligence your
  agents, and you, can trust."*
- **Definition beat (directly under the hero):** the A3 paragraph.
- **Primary CTA:** **Install** (targets the Get-started section).

---

## Part C — Status-badge system (required)

The site shows the **complete product — current and future** — and every module/capability/engine
and family product carries one status badge.

| Badge | Meaning |
|---|---|
| **Live** | Available today. |
| **Building** | Actively in development; not yet shippable. |
| **Planned** | On the roadmap; not started. |

Requirements: distinguish badges **without relying on color alone**; render from a **single editable
source** so updating maturity is a one-line change.

### Current maturity mapping (novetest's own capabilities, as of 2026-06-01)
- **Live:** install & onboarding; Run; Memory; Coverage; Regression; Localization.
- **Building:** Replay; the recommendation layer; engine support beyond pytest.
- **Planned:** Windows support.
- **Engines:** pytest = **Live**; jest, JUnit 5, go test, cargo test, dotnet test = **Building**.

(Planned family products — Novetest Console, Novetest Team — are shown in Part D, S12.)

---

## Part D — Required page sections

Order below is the recommended flow. The *presence and content* of each section is the requirement;
layout is your call. Copy is draft.

### S1 — Hero
See Part B. Must include: the **"Free & open source"** eyebrow, the headline, the trust subhead, the
"continuous" definition beat, the primary Install CTA, and optionally the inline install command.

### S2 — Trust strip (determinism-first, + open source)
Reinforce the #1 message immediately. Claims: **"No LLM in the loop"**, **"Deterministic &
reproducible: same inputs → same outputs"**, **"Every recommendation cites its evidence,"** and
**"Free & open source."** Draft: *"novetest is the part of your AI stack you can trust. No model in
the analysis path. The same run gives the same answer, every time. Every recommendation links back
to the exact runs and facts behind it. And it's free and open source — nothing hidden."*

### S3 — Capabilities at a glance (functional summary)
Three tiles:
1. **Multi-language testing, one tool.** *"Wraps the native engine your project already uses —
   pytest, jest, JUnit, go test, cargo test, dotnet test. No new framework to learn."*
2. **A set of testing engines that continuously work together.** *"Run, Memory, Coverage,
   Regression, Localization, and Replay aren't separate tools — they form one system where each
   run's facts feed the next, so you can compare runs, replay them, and let the loop get sharper as
   you go."*
3. **The right read on every result — and the next move.** *"novetest doesn't just report
   pass/fail. It interprets what your results mean — what regressed, where the fault is, what's
   flaky — and recommends the next action, prioritized and evidence-cited, so your coding agent
   moves faster with less guessing."*
*Honesty note:* tile 3's end-to-end recommendation is **Building**; the interpretation facts beneath
it are **Live**. May be visually merged with S6.

### S4 — The problem
AI generates/changes code faster than it can be trusted; the inner loop needs verification **now**,
not 20 minutes later in CI; plain runners throw everything away after pass/fail.

### S5 — How it works (the local loop)
Show the cycle **Execute → Store → Structure → Compare → Locate → Validate → Recommend** as a fast
local cycle, plus a **sample integrated output** (facts + a cited recommendation). The interactive
terminal demo (Part E, F5) fits here. *Honesty note:* label the end-to-end recommendation as
**Building**; the underlying facts are **Live**. Use real, copyable text (not an image).

### S6 — Module map (detailed, badged) — centerpiece
Show novetest's engines + recommendation layer, each with a one-line description and a badge:
- **Run — Live** — "Runs your tests through the native engine you already use; emits one standardized result."
- **Memory — Live** — "Stores every run as durable, citable evidence to inspect, compare, and replay."
- **Coverage — Live** — "Structures what each test exercised; computes coverage and coverage deltas."
- **Regression — Live** — "Compares runs to surface new failures, fixed failures, and output diffs."
- **Localization — Live** — "Ranks the most suspicious code locations for a failure (statistical fault localization)."
- **Replay — Building** — "Re-runs a stored run to tell a stable failure from a flaky one."
- **Recommendation — Building** — "Assembles all the facts into a short, prioritized, evidence-cited next step."

### S7 — Why local / why deterministic (and free)
Privacy (nothing leaves the machine), reproducibility, no account, no per-use token cost, offline,
auditable evidence citations — **and free & open source.** Draft: *"Everything runs in a folder next
to your code. No account, no upload, no token meter, works offline. Because there's no model in the
loop, the same run always gives the same answer — and you can trace every recommendation back to the
evidence. It's free and open source, too."*

### S8 — Cloud-grade analysis without the cloud
Regression detection and fault localization, normally CI/cloud-grade, now local and fast. Framing:
**"Cloud-grade test analysis. No cloud."**

### S9 — For agents & their supervisors
Structured JSON output by default; stable exit codes an agent can branch on; the agent = primary /
human = supervisor pair seeing the same facts. Make the relationship clear, positively: **the agent
brings the reasoning; novetest brings facts it can trust** — deterministic, with no model of its own.
Draft: *"Built for the agent first: every command emits a structured JSON envelope and a stable exit
code it can act on — no prose-scraping. Your agent brings the reasoning; novetest brings facts it can
trust — the same answer every time. The human supervises with the exact same facts."*

### S10 — Supported ecosystems
The six engines, each badged — pytest **(Live)**; jest, JUnit 5, go test, cargo test, dotnet test
**(Building)** — plus the boundary: **"we wrap your engine, never replace it — and we don't install
it for you."**

### S11 — Get started / install
The one-line install command, **"free to install, free to use — and open source (Apache-2.0),"**
**"no Python / Node / JVM prerequisite,"** **Linux & macOS today (Windows — Planned)**, an optional
2–3 step quickstart (`install → novetest init → novetest test`), and an optional "inspect the source
on GitHub" link. Install command (copyable):
`curl -fsSL https://ailovestesting.com/novetest/install.sh | sh`
(See `assets-and-links.md` for confirmed URLs.)

### S12 — The Novetest family (what's coming)
novetest is the **free, open-source foundation** of a planned product family. Show all three with
badges. **Only novetest is free / open source** — make **no** pricing or free claims about the
others.
- **novetest — Live / Building** — the free, open-source (Apache-2.0) CLI with the six engines; the
  foundation, available now.
- **Novetest Console — Planned** — a dashboard for the **human user**: a visual home to explore
  novetest's runs, history, regressions, fault localizations, and recommendations, beyond the
  terminal.
- **Novetest Team — Planned** — for **teams** building on novetest: shared test-suite management and
  TDD collaboration across team members.
(novetest's own near-term roadmap — Windows support, broader engine coverage — can be shown via the
S6/S10 badges.)

### S13 — Footer
`novetest` wordmark, `ailovestesting.com`, a **"free & open source"** note with the **Apache-2.0
license** and a link to the **GitHub repository**, plus install and docs (if available). Keep minimal.

---

## Part E — Functional requirements

- **F1 — Copy-to-clipboard** on the install command and any sample CLI commands.
- **F2 — Smooth-scroll anchor navigation** from the sticky nav and the hero CTA.
- **F3 — Status-badge rendering** from one editable source (per Part C); trivially updatable.
- **F4 — (Optional) secondary CTA** — a waitlist / early-access capture for the in-progress
  recommendation layer. Include only if we opt in (to confirm).
- **F5 — Interactive terminal demo (required for v1).** A **scripted, interactive terminal widget**:
  the visitor steps/clicks through a curated sequence (`install → novetest init → novetest test`) and
  watches realistic, pre-baked output appear — so they see, in seconds, how simple it is to install,
  run a test, and get back useful results. Notes:
  - It is **scripted, not live** — **no backend**, runs nothing real. It plays a fixed, deterministic
    sequence (which also reinforces "same result every time") and cannot break or be abused.
  - **We provide the exact command + output sequence;** you build the widget. Fits within S5.
  - A genuinely live, server-executed playground is **out of scope for v1** (it would need a
    server-side sandbox and conflicts with the "local / no-cloud" message); possible future
    enhancement.

---

## Part F — Non-functional requirements

- **SEO.** Descriptive `<title>`/meta description, Open Graph + Twitter card tags, semantic heading
  hierarchy, canonical URL, sitemap. Suggested keyword intents: *AI testing, local test
  intelligence, fault localization, regression detection for AI code, continuous local testing,
  multi-language testing, open source testing, AI coding agent testing.* Consider
  `SoftwareApplication` structured data.
- **Accessibility.** Target **WCAG 2.1 AA**: semantic landmarks/headings, keyboard navigability, alt
  text, sufficient contrast, **badges not conveyed by color alone**, honor `prefers-reduced-motion`.
- **Performance.** Fast first load (developer audience; speed also reinforces the "fast loop"
  message). Prefer a static-site approach, minimal JavaScript, optimized assets; aim for strong
  Lighthouse scores.
- **Privacy-respecting analytics.** Avoid trackers that contradict the product's privacy stance;
  prefer cookieless analytics or none (to confirm).
- **Internationalization.** v1 is English-only; keep copy out of images and structured so
  localization is possible later. Low priority.
- **Responsive, mobile-first.** Install command, loop diagram, capability tiles, terminal demo, and
  module map must remain legible and usable on mobile.

---

## Part G — Out of scope for v1 (do not block on these)

Final visual identity (logo, color, type), final copywriting polish, illustrations/imagery, any
multi-page expansion (docs/blog), and a live server-executed terminal playground. The priority is
the messaging, the content structure, and these section/functional requirements.
