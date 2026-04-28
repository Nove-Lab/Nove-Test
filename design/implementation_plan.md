# Nove Test — Implementation plan (CTO guide)

**Audience:** Engineering leads and sub-product owners.  
**Purpose:** Lock **high-level stack choices** and **MVP boundaries** so teams can start detailed design without rewriting foundations later. This is **not** a full requirements traceability matrix; details will evolve.

**MVP scope:** Python vertical slice first (see [`overall_plan.md`](./overall_plan.md)). Other language packs are out of scope for this document.

**Default platform assumptions for MVP:** Linux/macOS developer machines and Linux CI runners; local-first execution; no remote workers.

**Product order:** Sections follow **Nove Test Run → Memory → Oracle → Trace → Replay → Explorer → Orchestrator → Console**, aligned with [`architecture.md`](./architecture.md).

---

## 1. Nove Test Run

### Core

- **Process model:** Run tests as **subprocesses** (or subprocess trees) with explicit **cwd**, **env allowlist**, **timeouts**, and **resource limits** where the OS allows (wall clock always; memory/CPU where practical). Avoid in-process test execution for the MVP so Run stays a thin, trustworthy boundary.
- **Session contract:** Emit a stable **`run_id`**, bounded **stdout/stderr** capture, exit metadata, and **environment fingerprint** fields shared with Memory and downstream products.
- **Determinism tiers:** Implement **T1** (best-effort local) as MVP default; record lockfile digest and runtime version so **T2** comparisons are possible even if full hermetic **T3** is deferred.
- **Integration:** Run exposes a narrow API invoked by **Nove Test Orchestrator** or directly by agents/CLI; other sub-products do not spawn the native runner directly for Nove-governed work.

### Language variants

#### Python (MVP coverage)

- **Invocation:** Prefer **`pytest`** via subprocess (`python -m pytest …`) for ecosystem compatibility; keep a path open for a later “programmatic pytest” mode if latency becomes an issue.
- **Fingerprinting:** Capture **Python interpreter version**, **`requirements.txt` / `uv.lock` / `poetry.lock` / `pdm.lock` hash** (whichever is present), **OS/arch**, and optional **container image id** when running inside CI containers.
- **Determinism knobs:** Set **`PYTHONHASHSEED`** where applicable; document **test order** policy (e.g. `--randomly` off, explicit ordering flags); avoid `xdist` in MVP unless a dedicated profile is defined later.
- **Sandbox (light MVP):** Prefer **separate process + restricted env** over deep kernel sandboxing; document OS-level hardening (e.g. `bubblewrap` / `firejail`) as a **post-MVP** adapter, not a blocker for the first slice.

---

## 2. Nove Test Memory

### Core

- **Storage model:** **SQLite (or equivalent embedded index)** for baselines, classifications, flake scores, and **artifact handles**—not raw blobs inside the DB.
- **Artifact substrate (with Memory engineering):** **Content-addressed object layout** on disk (e.g. `objects/ab/cdef…`) plus index for manifests, reverse lookups, and export bundles; **SHA-256** or **BLAKE3** for content ids (pick one in Phase 1); **immutability** once committed; verify digest on read in CI-sensitive paths.
- **Operations:** Baseline **promotion/demotion** with **audit log**; classification `new / known / fixed / flaky-suspected / muted`; merge **continuity** into the next invocation bundle.
- **Agent annotations:** Store as an **overlay table** keyed by invocation/session, never overwriting engine-derived classification.

### Language variants

_Not applicable for MVP._ Memory stays **language-agnostic**; Python only affects what artifacts flow in from other sub-products.

---

## 3. Nove Test Oracle

### Core

- **Deterministic taxonomy:** Map normalized signals → **small fixed verdict enum** + **evidence blocks** + **fingerprint**; no ML on the critical path for MVP.
- **Separation:** Keep **assertion failures** (framework-reported) distinct from **infra / crash / timeout** classes for agent routing.

### Language variants

#### Python (MVP coverage)

- **Primary signals:** **pytest exit codes**, **`pytest` summary / short test summary info**, captured **stderr**, and optional **`--junitxml=…`** for structured per-test outcomes.
- **Parsing:** Prefer **JUnit XML** + pytest’s structured hooks where stable; fall back to regex only for last-resort stderr patterns.

---

## 4. Nove Test Trace

### Core

- **Attach mode:** Prefer **one instrumentation pass per session** shared with Run where possible (Trace subscribes to the same run Run started).
- **Artifact shape:** Emit **coverage snapshot handles** (never inline large blobs in agent payloads); optional **delta vs baseline** on demand (baseline handles from Memory).
- **MVP evidence:** Always attach a **failure-time snapshot** (stack + last events) for failed tests, even when full tracing is off.

### Language variants

#### Python (MVP coverage)

- **Coverage engine:** **`coverage.py`** with **branch coverage** enabled where supported; emit **JSON or LCOV** for stable parsing.
- **Per-test attribution:** Use **`pytest-cov`** or equivalent integration so coverage maps align with pytest node ids where feasible.
- **Overhead:** Start with **default instrumentation**; add **sampling / reduced scope** only if CI time budgets force it (deferred until measured).

---

## 5. Nove Test Replay

### Core

- **Replayer first:** Serialize **command vector**, **cwd**, **env subset**, **inputs**, **fingerprints**, and **RNG/clock policy** into a **replay recipe** artifact; verify with **N repeats** under Orchestrator flake policy.
- **Reducer:** Defer full minimization if needed; baseline can be **byte/file-level delta-debug**; structural shrinking is a **follow-on** once replay is stable.

### Language variants

#### Python (MVP coverage)

- **Replay:** Prefer **shell-stable recipes** (`python -m pytest …`) stored as structured JSON + optional human-facing command string.
- **Reduction:** Use a **small delta-debug loop** over files/args/env; consider **Hypothesis**’s shrinking only where tests are already Hypothesis-based (optional integration, not a default dependency for all users).

---

## 6. Nove Test Explorer

### Core

- **Feedback loop:** Coverage-guided **mutation** over seed tests/inputs with explicit **lineage** (seed → operator → parameters).
- **Execution boundary:** Explorer **never** spawns the native runner directly—only requests **child sessions through Run** (via **Nove Test Orchestrator** when present) with budgets.
- **Corpus:** Candidates and promoted entries are **handles** in the Memory/artifact substrate; dedupe by **digest + structural hints** (language pack may supply normalizers later).

### Language variants

#### Python (MVP coverage)

- **Mutation:** Start with a **maintained mutation tool** (e.g. **Mutmut**, **Cosmic Ray**) *or* a minimal **AST-based mutator** (`libcst` / `ast`) for controlled operators—pick one path in Phase 2 kickoff based on repo fit and maintenance cost.
- **Harness:** Reuse **pytest** discovery and markers so mutations stay inside the project’s natural test layout.

---

## 7. Nove Test Orchestrator

### Core

- **Runtime:** Implement as a **Python library + CLI entrypoint** (`novetest`) for MVP velocity and tight integration with pytest subprocess orchestration.
- **DAG engine:** Explicit **stage graph** (Run → Trace ∥ Oracle → Explorer children → Replay → Memory) with **cancellation**, **partial results**, and **correlation ids**.
- **Policies:** Central **budget arbiter**, **idempotency** keyed by `invocation_id`, **flake rerun** policy, **scrub gate** before persistence writes.
- **Payload assembly:** Build **tiered JSON** (`summary` / `standard` / `deep`) per [`subproducts/nove-test-orchestrator.md`](./subproducts/nove-test-orchestrator.md); stable ordering contract.
- **Agent envelope (full stack):** **`typer`** or **`click`** for `novetest` subcommands (`run`, `replay`, `annotate`, …); stdout JSON + optional `--output path`. **`pydantic`** (or **jsonschema** + codegen) for versioned payloads; every response includes `schema_version` / `engine_version`. **Streaming:** MVP can ship **NDJSON lines to stderr** or a **named pipe / file tail** pattern first; **plan-only mode** (`plan: true`) returns DAG + cost estimate without execution.

### Language variants

_Not applicable._ Orchestrator is stack-neutral; Python is the implementation language, not a “variant.”

---

## 8. Nove Test Console

### Core

- **MVP bar:** **Read-heavy** view over the same JSON the agent gets: **static HTML** generated from a template **or** a **minimal Vite + React** page that loads a dumped JSON payload—choose one in Phase 3 kickoff; avoid building a full design system before engine contracts freeze.
- **Governance:** Baseline promote/demote and mute actions call the **same Orchestrator APIs** the CLI uses, with **audit entries** in SQLite.
- **Adapters:** One adapter surface per shipped sub-product so the Console shell stays thin.

### Language variants

_Not applicable for MVP._

---

## Cross-cutting CTO decisions (summary)

| Topic | MVP direction |
|--------|----------------|
| **Core implementation language** | **Python 3.11+** for Orchestrator, CLI, and glue; subprocess-isolated pytest for **Run**. |
| **Persistence** | **SQLite + content-addressed files** for **Memory** (artifact substrate). |
| **Test harness** | **pytest** as the default for the Python slice. |
| **Coverage** | **coverage.py** (+ pytest integration) for **Trace**. |
| **Mutation / exploration** | One supported **Python mutation path** (tool or AST-based); not both in parallel unless maintenance cost is accepted. |
| **Sandbox** | **Process + env policy** first; OS/container sandbox adapters later. |
| **Non-Python languages** | Explicitly **deferred**; adapters will follow the same **sub-product** contracts. |

---

## Suggested reading order for implementers

1. [`architecture.md`](./architecture.md) — product family spine  
2. Per-sub-product specs under [`subproducts/`](./subproducts/)  
3. [`subproducts/nove-test-orchestrator.md`](./subproducts/nove-test-orchestrator.md) (full-stack agent contract) and [`subproducts/nove-test-console.md`](./subproducts/nove-test-console.md) (human surface)  
4. **This file** — stack and sequencing guardrails  

When a sub-product owner proposes a technology not listed here, the bar is: **same contracts**, **equal or lower operational complexity**, and **no silent broadening of MVP scope**.
