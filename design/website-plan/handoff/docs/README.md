# novetest — Docs pages (build package)

This folder is the **content source** for the Docs section of
`ailovestesting.com`. Eight markdown files: one Docs landing index plus
seven content pages, in the order a reader should encounter them. Same
content shape across the whole set; same tab convention everywhere
the human and the AI agent need to see different commands or output.

> The marketing landing page lives in `../README.md` /
> `../site-requirements.md` / `../assets-and-links.md`. This folder is
> additive: the landing page links to **Docs → Introduction** as its
> deeper-reading destination.

---

## Files in this folder

| # | File | Page on the site (suggested URL) |
|---|---|---|
| 0 | `README.md` (this file) | `/docs` (Docs landing index) |
| 1 | `introduction.md` | `/docs/introduction` |
| 2 | `installation.md` | `/docs/installation` |
| 3 | `quick-start.md` | `/docs/quick-start` |
| 4 | `supported-languages.md` | `/docs/languages` |
| 5 | `understanding-results.md` | `/docs/understanding-results` |
| 6 | `advanced-usage.md` | `/docs/advanced` |
| 7 | `troubleshooting.md` | `/docs/troubleshooting` |

Pages are independently readable but assume the reading order above —
each page's "What to read next" footer points to the natural follow-up.

The **left-sidebar navigation order** on the site should match this
table.

---

## The `For human` / `For agent` tab convention

novetest has two primary readers — **the human developer** at a
terminal and **the AI coding agent** consuming the JSON envelope.
Most of the conceptual material is identical for both; only the
**commands they type** and the **output they read** differ.

Rather than ship two parallel doc sets (the engineering side already
maintains those internally), each Docs page is **one document** with
a UI tab control that swaps only the divergent passages.

### Source convention used in these markdown files

Wherever the page needs to show divergent content, you will find a
fenced container of the following form:

````markdown
::: tabs
@tab For human

```bash
novetest test
```

Renders human-readable text on a TTY.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest test
```

Returns a `novetest/v1` JSON envelope on stdout.

:::
````

Rules:

1. **The opening fence is `::: tabs` on its own line.**
2. **The closing fence is `:::` on its own line** (no `tabs` repeated).
3. **Each tab is introduced by `@tab <label>` on its own line**, where
   `<label>` is the human-readable tab title. **At MVP there are
   exactly two labels: `For human` and `For agent`, in that order.**
4. Anything between an `@tab` and the next `@tab` (or the closing
   `:::`) is the body of that tab and is itself ordinary markdown
   (paragraphs, code blocks, tables, lists — all allowed).
5. The convention is **only used where content diverges.** Shared
   sentences, shared tables, and shared concepts must NOT be wrapped
   in tabs — that would force the reader to click a tab to read
   identical text. **Default to shared.**
6. **Tab state on the page is global and sticky.** When a reader picks
   `For agent` in the first tab block on a page, every later tab block
   on that same page should also open on `For agent`. (Reader picks
   their role once, near the top.) Persist the choice across
   page-to-page navigation within the Docs section in the same
   localStorage key.
7. A toggle in the top-right of every Docs page that says
   **"Audience: human · agent"** (with the current role highlighted)
   is **REQUIRED**. It must drive the same global state as the
   in-page tabs, and the in-page tabs must reflect changes from it.
   The reason: most readers will scroll past the first tab without
   touching it, and the toggle gives them an obvious affordance to
   switch later.
8. If the page has zero tab blocks, hide the toggle on that page.

### Implementation guidance for the website team

The convention maps directly onto any modern docs framework:

| Framework | Approach |
|---|---|
| Docusaurus | A remark plugin that rewrites the fenced container into `<Tabs><TabItem>...</TabItem></Tabs>`; sync state across blocks via the `groupId` prop with the same value on every block. |
| VitePress | Use `vitepress-plugin-tabs` (or `@vitepress-tabs/tabs`) and the `::: tabs` fenced container is the supported native syntax. |
| MkDocs Material | Enable the `pymdownx.tabbed` extension; rewrite the fence into `=== "For human"` / `=== "For agent"` at build time. |
| Custom (Next.js / SvelteKit / Astro) | A markdown-it container plugin extracts the blocks; render with your own `<TabGroup>` component sourcing state from a top-level audience-context store. |

The fenced-container form was chosen because (a) it survives
copy-paste as plain markdown for archival and offline reading, and
(b) every modern docs framework has a one-plugin path to render it
as tabs.

### Audience defaults & detection

- On first visit to the Docs section, default to **For human**.
  Rationale: humans clicking through marketing -> Docs are the larger
  cold-traffic segment; agents land via direct URL with a known
  intent.
- Persist the user's last choice in `localStorage` under key
  `novetest:docs:audience` with allowed values `"human"` or `"agent"`.
- If the URL carries `?audience=agent` (or `?audience=human`), use
  that value and persist it. This lets us link directly into the
  agent view from external documentation.
- Do NOT default to "agent" based on user-agent sniffing. Agents that
  consume these pages programmatically use the raw markdown source in
  this folder, not the rendered HTML.

---

## Document-level conventions

Every page in this folder follows the same skeleton:

1. **H1 title** - the page name, matching the sidebar label.
2. **Lead paragraph** - what this page is for, no fluff.
3. **Body** - sections with H2 headings; tab blocks only where content
   diverges; otherwise prose, tables, and code blocks shared by both
   audiences.
4. **"What to read next" footer** - short list of internal links to
   the next natural pages.

All code samples in these pages are **real, byte-accurate output** the
CLI produces today. Treat them as canonical reference. If the website
team needs to truncate a long sample for layout, indicate the
truncation explicitly (`/* ... */`) - never paraphrase.

---

## What's NOT in this folder

- **The marketing landing copy** - that's in `../site-requirements.md`.
- **API reference / schema definitions** - `novetest/v1` envelope
  schemas are an in-product asset, served as JSON Schema from the
  GitHub repo. The Docs pages link to them where relevant; they are
  not embedded.
- **A blog or release-notes feed** - out of scope for v1 Docs.
- **A live REPL / playground** - out of scope; the scripted terminal
  demo lives on the landing page (`../site-requirements.md` F5).

---

## Status

- **Bundle version**: docs-v1, 2026-06-24
- **Pages**: 7 (plus this index)
- **Tab convention version**: 1 (additive changes only; new labels
  must not break existing labels)
- **Source CLI version**: every example output on every page was
  captured against `novetest 0.1.2` (Latest on GitHub Releases as of
  the bundle date)
