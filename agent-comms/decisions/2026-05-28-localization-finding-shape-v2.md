---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-28
slug: localization-finding-shape-v2
related:
  - agent-comms/decisions/2026-05-28-localization-finding-shape.md
  - agent-comms/handoffs/localization-team-2026-05-28-engine-completion.md
  - agent-comms/verifications/2026-05-28-localization-engine-completion.md
---

# Decision: Localization Finding schema v2 — closes v1 §6 and §X

CEO-approved on 2026-05-28. **Supersedes
[`2026-05-28-localization-finding-shape.md`](./2026-05-28-localization-finding-shape.md)
(v1)**. This v2 codifies the three surface changes shipped by the
engine-completion slice `8ec124a`:

1. The `LocalizationUnavailable.to_dict()` "known gap" flagged by v1 §6
   is now closed — the serialization shape is pinned below.
2. The `REASON_MISSING_DERIVED_FACTS` split promised in v1 §X is
   implemented — the 5-element `KNOWN_REASONS` and routing rules are
   pinned below.
3. Two new latest-resolution helpers
   (`resolve_latest_analyzable_run`, `derive_latest_localization`)
   ship; their Unavailable shape and kwargs surface are pinned below.

**All other v1 constraints carry forward unchanged** — §1 (12-key
`LocalizationFinding`), §2 (9-key `LocalizationEntry`), §3 (`tied_with`
convention), §4 (6-key `CodeLocation`), §5 (3-key `EvidenceCitation`),
§7 (persistence path), §A (cache short-circuit), §N (test code in
output is intended behavior, NOT filtered), and the binding constraints
+ forward-compat rules remain in force.

## Source of truth (anchors)

- `src/novetest/localization/results.py` — `REASON_*` constants (5),
  `KNOWN_REASONS` frozenset, `LocalizationUnavailable.to_dict()`.
- `src/novetest/localization/retrieval.py` — `get_localization_findings`
  cache-empty routing.
- `src/novetest/localization/derive.py` — `resolve_latest_analyzable_run`,
  `derive_latest_localization`, tombstoned-input routing.
- All shapes below are frozen at the form shipped by commit `8ec124a`
  and verified by `2026-05-28-localization-engine-completion`.

## §6′. `LocalizationUnavailable` — 3 fields + `to_dict()` pinned

Dataclass unchanged from v1 §6:

```python
@dataclass(slots=True, frozen=True)
class LocalizationUnavailable:
    run_reference: RunReference | None
    reason: str   # one of KNOWN_REASONS (5 elements; see §X′)
    detail: str | None = None
```

`to_dict()` shape (newly pinned, replaces the v1 §6 "known gap" note):

```json
{
  "run_reference": null | { "run_id": "<ULID>", "created_at": "<ISO8601-UTC>" },
  "reason": "<one of KNOWN_REASONS>",
  "detail": null | "<human-readable>"
}
```

Binding:
- **3 keys, all always present.** `run_reference` and `detail` are
  emitted as `null` when their respective field is `None` — omitting
  the key is a wire-contract violation.
- **Key order is `run_reference`, `reason`, `detail`** (matches
  `RegressionUnavailable.to_dict()`).
- `run_reference` (when non-null) is the result of
  `RunReference.to_dict()` — re-uses the existing serializer.
- **JSON-stable** — verified by `test_to_dict_is_json_serializable`.

## §X′. `KNOWN_REASONS` — 5 elements (split implemented)

Final closed set, replacing v1 §6's 4-element table:

| Reason | Fires when | Recoverable? |
|---|---|---|
| `no_failed_tests` | Run Record has 0 failed test results | N/A (no failure to localize) |
| `no_coverage` | Coverage Facts unavailable OR `mapping_granularity != "per-test"` | Yes (re-run with `--coverage`, or wait for follow-up modes) |
| `no_run_evidence` | `retrieve_run_evidence` raises (no live and no tombstoned record); also surfaces from `resolve_latest_analyzable_run` when store has zero runs | No (unknown run_id) |
| `missing_derived_facts` (NEW v2) | Cache empty — `get_localization_findings` called before `derive_localization_findings` | **Yes — caller should call `derive`** |
| `run_not_analyzable` (RETAINED, NARROWED) | Run Record is tombstoned (audit confirmed `derive.py:136`); also from `resolve_latest_analyzable_run` when all runs in store are non-analyzable | No (tombstoned or evidence corruption) |

### Convention pin: underscore form (NOT hyphen)

The new constant is `REASON_MISSING_DERIVED_FACTS = "missing_derived_facts"`
— **underscore form**, distinct from Regression's hyphenated
`"missing-derived-facts"`. The closed-enum `__post_init__` guard
explicitly rejects the hyphenated form (verified by
`test_unavailable_hyphenated_missing_derived_facts_is_rejected`).

The two engines' reason-string conventions stay independent. Consumers
must use the right form per engine — there is no shared cross-engine
reason vocabulary at v2.

### Routing rules (binding)

| Site | Reason emitted |
|---|---|
| `retrieval.py::get_localization_findings` — cache absent | `missing_derived_facts` (detail: `"findings not yet derived"`) |
| `derive.py::derive_localization_findings` — tombstoned input | `run_not_analyzable` (narrowed-retained) |
| `derive.py::resolve_latest_analyzable_run` — store empty | `no_run_evidence` (detail: `"no runs in store"`) |
| `derive.py::resolve_latest_analyzable_run` — all non-analyzable | `run_not_analyzable` (detail: `"no analyzable runs in store (N candidates checked)"`) |

## §C. `resolve_latest_analyzable_run` — NEW v2 surface

Signature:

```python
def resolve_latest_analyzable_run(
    store: ProjectStore,
) -> RunReference | LocalizationUnavailable: ...
```

Binding behavior:
- Walks `list_run_history(store)` **newest-first**.
- For each candidate, runs `check_localization_availability(store, ref)`
  (the cheap probe). Returns the first reference for which it returns
  `True`.
- **Pure read** — never derives, never writes. The
  `test_resolve_does_not_invoke_derive` spy + filesystem assertion is
  the binding contract on this.
- Unavailable outcomes always carry `run_reference=None` — the resolver
  is a per-store query, not a per-run query, so there is no single
  ref to point at. This is the first producer in the codebase to
  surface `run_reference=None` in practice; consumers must handle the
  null case (the `to_dict()` shape pinned in §6′ already covers this).

### N count semantics (deviation #2 disposition)

The `"no analyzable runs in store (N candidates checked)"` detail
string reports **N = total candidates probed**, including tombstoned
entries encountered during the walk. Rationale: the user-facing
semantic of this detail is "I tried N times and none worked"; the
filtering of tombstoned runs lives inside
`check_localization_availability` and is correctly opaque to the
resolver itself. **Pinned as-is** (not narrowed to live-only count).

## §D. `derive_latest_localization` — NEW v2 surface

Signature:

```python
def derive_latest_localization(
    store: ProjectStore,
    *,
    formula: str = "ochiai",
    top_n: int = 10,
) -> LocalizationFinding | LocalizationUnavailable: ...
```

Binding behavior:
- Pure composition: `resolve_latest_analyzable_run(store)` → return
  the `LocalizationUnavailable` unchanged when one is produced, OR
  call `derive_localization_findings(store, ref, top_n=top_n, formula=formula)`
  and return its result.
- No additional logic. The function is intentionally a thin facade so
  that the upcoming `novetest localization latest` CLI verb projects
  one entry point onto envelopes without composing twice.

### Kwargs ordering note (deviation #1 disposition)

`derive_latest_localization` declares `(store, *, formula, top_n)`.
`derive_localization_findings` declares `(store, run_reference, top_n, *, formula)`.

Both `formula` and `top_n` are keyword-only post-`*` on each, so the
ordering is **functionally irrelevant** to callers (Python keyword
binding is positional-name not declaration-order). **Pinned as-is**
on both functions; no reconcile required. The upcoming CLI verb
exposes both as `--formula` / `--top-n` flags, so the internal kwargs
surface is invisible to users.

## §N′. Test code in localization output — unchanged from v1

The v1 §N ruling (test code IS NOT filtered, schema does NOT carry
`is_test_code`, SBFL math degrades test-body rank as `1/√totalfail`)
**stands unchanged**. Quoted here for emphasis: do not re-open this
without a CEO product decision.

## Binding constraints (incremental over v1)

In addition to all v1 binding constraints:

7. **`LocalizationUnavailable.to_dict()` is binding**: 3 keys, key
   order `run_reference`, `reason`, `detail`, all always present
   (null-not-absent), JSON-stable.
8. **`KNOWN_REASONS` is the closed 5-element set above.** Adding a
   new reason requires v3.
9. **`resolve_latest_analyzable_run` is pure-read.** Triggering
   `derive_localization_findings` from its body is a contract violation.
10. **`derive_latest_localization` is pure composition.** Any logic
    beyond the documented resolver-then-derive pipeline requires v3.

## Forward-compatible extension rules (carry forward + 1 addition)

- All v1 forward-compat rules carry forward.
- Adding `regression_fact` to `EvidenceCitation.kind` enum (reserved
  in v1 §5) requires v3 of THIS decision (not a v2-of-v2).

## Affected commands (unchanged from v1, restated)

- `novetest localization <run_id>` (next cycle) — emits this shape.
- `novetest localization latest` (next cycle) — projects
  `derive_latest_localization` onto the same envelope shape.
- `inspect` Localization section (next cycle) — must reuse this
  shape.

## Affected teams / files

- **Localization Team** — owns the shape source-of-truth
  (`models/localization_finding.py`, `localization/results.py`,
  `localization/derive.py`). v2 is implemented; no further binding
  work required for the schema itself until v3 is triggered.
- **Orchestration Team** — projects this onto CLI envelopes in the
  upcoming Localization CLI verb cycle. May not alter the persisted
  shape.
- **Memory Team** — owns the `has_localization_findings` availability
  flag whose probe path is pinned by v1 §7 (unchanged).
- **All teams** — v2 is binding; v1 is historical record.

## Effective date

2026-05-28 (the same day v1 was issued; the engine-completion slice
shipped within the same day's planning rotation).

## Supersedes

- [`2026-05-28-localization-finding-shape.md`](./2026-05-28-localization-finding-shape.md)
  — v1, retained as historical record. All clauses NOT explicitly
  changed by this v2 carry forward unchanged from v1.
