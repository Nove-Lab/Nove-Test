# Implementation Plan - Recommendation Synthesis

**Scope:** Implementation strategy for the top-level Orchestration sub-product's `synthesize_recommendation` interface and its `cite_recommendation_evidence` companion. Synthesis approach, recommendation categories, evidence citation schema, determinism contract.

**Upstream**
- Foundations: [`foundations.md`](./foundations.md)
- Localization strategy (input source): [`localization-strategy.md`](./localization-strategy.md)
- Orchestration interface contract: [`design/interace-contract/orchestration.md`](../interace-contract/orchestration.md)
- Orchestration product plan: [`design/product-plans/overall-architecture.md`](../product-plans/overall-architecture.md)
- Requirements: [`design/requirements-analysis/requirements-specification/groups/orchestration.md`](../requirements-analysis/requirements-specification/groups/orchestration.md)

---

## 1. Deterministic, Rule-Based Synthesis

**Decision: pure rule-based, deterministic, template-driven. No LLM call in the synthesis path.**

### Trade-off review

| Approach | Pros | Cons |
| --- | --- | --- |
| LLM call in the synth path | Natural prose; can summarize across facts | Non-deterministic; adds latency; consumes the *consumer's* token budget twice (we generate prose, the agent re-parses); hallucination risk on fact citations |
| Rule-based templates | Deterministic; fast; every output field is traceable to a fact; trivially testable; golden-fixture testable | Prose is stiff |
| Hybrid (deterministic facts → LLM-templated text) | Reads better | Same non-determinism and hallucination surface as pure LLM, just smaller |

### Decisive argument

**The consumer is an AI agent.** The agent has its own LLM. Our job is to serve a structured fact bundle so the agent can reason; if we wrap it in prose, the agent must un-wrap it. A rule-based synthesizer that emits `{category, summary_template, slots, evidence_citations}` lets the agent either render the template or ignore it and read the slots directly.

This also aligns with NFR-ORCH-002: every recommendation must be resolvable to its cited evidence "without requiring informal terminal-text interpretation." LLM-generated prose violates this NFR's spirit.

### Where an LLM might enter (later, optional)

The only place a future LLM might enter is **rendering prose summaries for human display**. Even there, prefer fixed templates with slot interpolation. If a future feature wants prose summaries, gate it behind a `--narrative` flag that wraps the deterministic JSON, and never let it influence `evidence_citations` or `slots`.

### Implementation location

```
src/novetest/orchestration/recommendation/
  synthesizer.py     # rule-based synthesis
  citations.py       # cite_recommendation_evidence
  categories.py      # closed taxonomy
  templates.py       # one template per category, slot-driven
```

`synthesizer.py` is the only file under `recommendation/` that decides categories. `citations.py` is a pure projection from facts to citation objects.

---

## 2. Recommendation Categories

**Decision: closed taxonomy. Closed beats open because it is testable, the agent can switch on category, and we can version it.**

| Category | Trigger condition | Example |
| --- | --- | --- |
| `investigate_location` | Localization Finding with `confidence >= medium` and `rank <= 3` | "Investigate `BarService.compute` in `src/foo/bar.py:58`" |
| `investigate_regression` | Regression Fact: test newly failing this run | "Test `test_x` passed in run R1, fails in run R2" |
| `flaky_suspected` | Replay Result with inconsistent outcomes across reruns | "Test `test_y` passed 3/5 reruns" |
| `coverage_gap` | Coverage Fact shows uncovered branch in code path implicated by Localization | "Branch at `bar.py:63` uncovered; suspected location" |
| `regression_with_localization` | Regression Fact AND Localization Finding overlap on file/symbol | (compound; highest priority) |
| `unavailable_analysis` | One or more facts are unavailable | "Localization unavailable: no per-test coverage; ran in aggregate mode" |
| `all_green` | Status = passing, no regression, no flake | "All tests green; no action recommended" |

### Three rules enforced by the synthesizer

1. **Compound categories are ranked above single-source categories.** `regression_with_localization` outranks bare `investigate_location` because the regression fact disambiguates the suspicion. The priority order is encoded in `categories.py`.
2. **Each category has a fixed schema.** No optional fields that float in and out. Absent data is `null`, not missing.
3. **Categories are stable identifiers.** Versioned via `recommendation_schema_version` in the envelope. Agents can pin behavior.

### Adding a new category

A new category requires:
1. An entry in `categories.py` with priority and trigger predicate.
2. A template in `templates.py` listing the slot keys.
3. A golden-fixture test under `tests/fixtures/projects/<scenario>/` that produces it.
4. Bumping `recommendation_schema_version`.

This deliberate friction prevents the taxonomy from growing organically.

---

## 3. Evidence Citation Schema

**Decision: explicit, polymorphic-by-`kind`, agent-traversable. Each citation carries enough state to round-trip back through Memory.**

### Wire shape

```json
{
  "recommendation_id": "rec_<run_id>_<seq>",
  "category": "investigate_location",
  "priority": 1,
  "summary": "Investigate BarService.compute in src/foo/bar.py:58",
  "slots": {
    "symbol": "BarService.compute",
    "file": "src/foo/bar.py",
    "primary_line": 58,
    "rank": 1,
    "score_normalized": 0.92,
    "formula": "ochiai"
  },
  "evidence_citations": [
    {
      "kind": "localization_finding",
      "run_reference": "run_2026_05_11_abcd",
      "finding_id": "loc_run_2026_05_11_abcd_0001",
      "selector": { "code_location_id": "cl_0007" }
    },
    {
      "kind": "test_result",
      "run_reference": "run_2026_05_11_abcd",
      "test_id": "tests/test_bar.py::test_compute_negative",
      "outcome": "failed"
    },
    {
      "kind": "coverage_fact",
      "run_reference": "run_2026_05_11_abcd",
      "selector": { "file": "src/foo/bar.py", "lines": [58, 63] },
      "mode": "aggregate"
    },
    {
      "kind": "regression_fact",
      "run_reference_from": "run_2026_05_10_prev",
      "run_reference_to": "run_2026_05_11_abcd",
      "selector": { "test_id": "tests/test_bar.py::test_compute_negative" }
    }
  ]
}
```

### Design rules

- `kind` is a **closed enum** matching the domain entities: `localization_finding`, `coverage_fact`, `regression_fact`, `replay_result`, `test_result`, `run_reference`.
- Every citation carries enough state (`run_reference`, `selector`, optional explicit ids) to resolve back to the source via the existing internal interfaces (`memory/retrieve_run_evidence`, `localization/get_localization_findings`, `coverage/get_coverage_facts`, `regression/get_regression_facts`, `replay/get_replay_result`). This satisfies NFR-ORCH-002 directly.
- `selector` is **intentionally polymorphic per kind**. Do not try to unify it - agents switch on `kind`.
- A recommendation has **>=1** citation (REQ-ORCH-005). Compound categories carry one citation per source fact - do not collapse.
- Citation order within a recommendation is stable: by `kind` then by selector key.

### `cite_recommendation_evidence` is scoped to Recommendations only

Per the earlier orchestration deduplication review, this interface no longer accepts Localization Findings. Localization owns its own internal Evidence Citations (computed during `derive_localization_findings`). The recommendation's citation list **may include** a `localization_finding` reference, but the Localization Finding's *internal* citations are not re-cited at the recommendation layer.

---

## 4. Determinism Contract

**Decision: same fact bundle in -> byte-identical recommendation list out.**

### Concrete contract

- Same fact bundle in -> byte-identical recommendation list out (modulo a stable timestamp field that should be isolated or omitted from comparison).
- Ordering is deterministic: sort by `(priority asc, category asc, primary_slot asc)` where `primary_slot` is the category-specific stable key (e.g. `file:line` for `investigate_location`, `test_id` for `investigate_regression`).
- ID generation is deterministic: `rec_<run_id>_<sha1(category|primary_slot)[:8]>`.
- No wall-clock-dependent tiebreaks.
- No reliance on `dict` insertion order during scoring (Python 3.7+ guarantees this, but be explicit).

### Testability

This is testable - golden-fixture tests under `tests/fixtures/projects/localization-branch/` (already in `CLAUDE.md`) can pin recommendation output for a given run record. Use `syrupy` snapshots over the JSON envelope; commit the snapshots; break-changes are loud in PR review.

With an LLM in the loop you cannot write that test; you can only write a similarity test, which is the wrong contract for an interface other systems will pin against.

---

## 5. Putting It Together

### Synthesis flow

```python
# orchestration/recommendation/synthesizer.py
def synthesize_recommendation(
    fact_bundle: FactBundle,         # coverage / regression / localization / replay / status
) -> list[Recommendation]:
    triggered: list[CategoryHit] = []
    for category in CATEGORIES_BY_PRIORITY:
        triggered.extend(category.match(fact_bundle))

    # compound categories swallow their constituents
    triggered = compound_resolution(triggered)

    recs = [build_recommendation(hit, fact_bundle) for hit in triggered]
    recs.sort(key=stable_sort_key)
    return recs
```

The function is pure. Same `fact_bundle` -> same `list[Recommendation]`.

### Build flow per recommendation

```python
def build_recommendation(hit: CategoryHit, bundle: FactBundle) -> Recommendation:
    template = TEMPLATES[hit.category]
    slots = template.extract_slots(hit, bundle)
    citations = cite_recommendation_evidence(hit, bundle)
    return Recommendation(
        recommendation_id=stable_id(hit, bundle),
        category=hit.category,
        priority=hit.priority,
        summary=template.render(slots),
        slots=slots,
        evidence_citations=citations,
    )
```

### Output envelope

The recommendation list is wrapped in the standard Nove Test envelope (see [`foundations.md`](./foundations.md#2-cli-framework-and-output-contract)):

```json
{
  "schema": "novetest/v1",
  "command": "test",
  "ok": true,
  "data": {
    "run_reference": "run_2026_05_11_abcd",
    "stage_eligibility": {
      "coverage": "available",
      "regression": "available",
      "localization": "sbfl_aggregate",
      "replay": "not_run"
    },
    "recommendation_schema_version": 1,
    "recommendations": [ /* see §3 */ ]
  },
  "errors": [],
  "warnings": []
}
```

`stage_eligibility` lets the agent see at a glance which evidence drove the recommendations and which was unavailable.

---

## 6. Implementation Notes

- **Recommendations are NOT persisted by default.** They are derived from the persisted facts each time `novetest test` runs or `novetest inspect` is called. We may cache them in the run directory for `inspect` performance, but the contract is "same facts -> same recommendations" so caching is an optimization, not a correctness requirement.
- **The Status entity's `recommendation_summary`** (if added in Phase 6) is a count-by-category projection of the latest recommendation set; it is not an independent fact.
- **No randomness anywhere.** Even tie-breaking among equal-priority recommendations uses a stable sort key.
- **No I/O during synthesis.** All fact data must be passed in. Synthesis is a pure function over `FactBundle`. Memory / Coverage / Regression / Localization / Replay reads happen *before* synthesis, in the workflow that builds `FactBundle`.

---

## 7. Open Items

Flagged for Phase 6 implementation; see [`delivery-phasing.md`](./delivery-phasing.md#open-questions):

1. **`recommendation_schema_version` v1 freeze.** The slot keys per category in §2 should be frozen at the start of Phase 6 and changes after that bump the version.
2. **Compound category scope.** Phase 6 ships only `regression_with_localization` as a compound. Other compounds (`flaky_with_localization`, `coverage_gap_with_regression`) are explicit deferrals.
3. **`--narrative` prose mode.** Out of scope for Phase 6 unless an early adopter explicitly asks. If it ships, it is an additive presentation layer over the deterministic JSON, never a replacement.
4. **Recommendation persistence and history.** Whether to persist recommendation lists per run for fast `inspect` is an optimization to revisit after Phase 6 measures the cost of re-derivation.

---

## 8. Closed taxonomy v1 — authoritative list

**The single source of truth for category names is the code:**
[`src/novetest/orchestration/recommendation/categories.py`](../../src/novetest/orchestration/recommendation/categories.py)
(`CATEGORIES` frozenset + `CATEGORIES_BY_PRIORITY`). The v1 list, highest
priority first:

1. `regression_with_localization`
2. `investigate_location`
3. `investigate_regression`
4. `coverage_gap`
5. `flaky_suspected`
6. `unavailable_analysis`
7. `all_green`

**Paraphrasing these names anywhere downstream is forbidden.** Agents pin
routing to the exact `recommendations[].category` strings; a doc that
invents a nicer-sounding name (this happened — `tests_failed`,
`coverage_regressed`, `flaky_suspect` et al. shipped in user docs on
2026-06-25 and never matched the code) produces routing that silently
never fires. Any doc that lists categories must cross-reference this
section, and this section must never be edited except in lockstep with
`categories.py`.

### Checklist for every future taxonomy change

1. Land the category constant (and matcher) in `categories.py` first —
   the code change IS the taxonomy change.
2. Update this section and every category table in
   `design/user-doc/{human,agent}/` and
   `design/website-plan/handoff/docs/` in the same commit (or the
   immediately following one).
3. Confirm the renderer mapping (`src/novetest/cli/renderers/test.py`
   `_category_glyph` / `_citation_line`) — glyphs and citation kinds are
   part of the same frozen surface.
4. Bump `recommendation_schema_version` if slot keys changed; regen
   `agent-comms/INDEX.md` if the change was routed via a task.
