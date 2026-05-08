# Requirements Index

## References

- `design/requirements-analysis/context-model.md`
- `design/requirements-analysis/use-case-model.md`
- `design/requirements-analysis/domain-model.md`
- `design/requirements-analysis/system-responsibility-model.md`
- User-approved grouping: `orchestration`, `run`, `memory`, `coverage`, `regression`, `localization`, `replay`

---

## Requirement Groups

| Group | Description | File | Status |
|-------|------------|------|--------|
| orchestration | Top-level Nove Test workflow orchestration, status reporting, recommendation synthesis, and evidence citation. | `groups/orchestration.md` | Draft |
| run | Test-target resolution, native-engine selection, execution invocation, result normalization, and run reference assignment. | `groups/run.md` | Draft |
| memory | Run evidence persistence, retrieval, listing, and safer deletion or tombstone handling. | `groups/memory.md` | Draft |
| coverage | Coverage fact derivation and cross-run coverage comparison. | `groups/coverage.md` | Draft |
| regression | Latest comparison-baseline resolution and regression fact derivation. | `groups/regression.md` | Draft |
| localization | Latest analyzable-run selection and suspicious-location derivation. | `groups/localization.md` | Draft |
| replay | Replay-context reconstruction and replay-consistency classification. | `groups/replay.md` | Draft |

---

## Group Summary

| Group | Functional Count | Non-Functional Count | Total |
|-------|------------------|----------------------|-------|
| orchestration | 5 | 3 | 8 |
| run | 5 | 3 | 8 |
| memory | 5 | 3 | 8 |
| coverage | 4 | 2 | 6 |
| regression | 4 | 2 | 6 |
| localization | 4 | 2 | 6 |
| replay | 4 | 2 | 6 |

---

## Overall Status Summary

| Status | Count |
|--------|-------|
| Draft | 48 |
| Approved | 0 |
| Implemented | 0 |
| Verified | 0 |

---

## Notes

- Each functional requirement is traced to at least one approved system responsibility and to the related use cases and entities named in upstream artifacts.
- Requirement groups are aligned to the product structure requested by the user: one top-level `orchestration` group plus one group per active sub-product.
- All generated requirements are in `Draft` status. Status transitions should follow `Draft` -> `Approved` -> `Implemented` -> `Verified`.

---

## Assumptions

- The current analysis workspace remains `design/requirements-analysis/` for this Nove Test task.
- Safer deletion behavior in the Memory group means preserving citation and history integrity through tombstone or equivalent retained trace behavior.

---

## Open Questions

None.

---

## Status Definitions

- **Draft**: Generated but not yet reviewed by a human
- **Approved**: Reviewed and accepted by a human; ready for implementation
- **Implemented**: Implemented in the system
- **Verified**: Verified through testing or validation
