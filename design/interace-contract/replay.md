# Interface Contract - Replay

**Scope:** Replay sub-product. Reconstructs Replay context from a stored Run Record, re-executes through the governed Run path under reconstructed conditions, and classifies reproducibility against the original run as a Replay Result. Replay produces facts only; it does not prescribe a fix and does not implement an independent test runner.

**Upstream references**
- `design/product-plans/subproducts/nove-test-replay.md`
- `design/requirements-analysis/requirements-specification/groups/replay.md`
- `design/requirements-analysis/system-responsibility-model.md` (SR-017, SR-018)
- `design/requirements-analysis/domain-model.md`

---

## Conventions

- **External** - Directly invokable by an actor (AI Agent, Developer) through the `novetest` CLI surface.
- **Internal** - Invokable only by other Nove Test modules (Orchestration) within the tool boundary.
- Inputs and outputs use domain-entity vocabulary from `design/requirements-analysis/domain-model.md`.

---

## Replay Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest replay <run_id>` | External | Run Reference of the original Run Record | Replay Result with classification (reproducible / inconsistent / unable to replay), reference to original Run Record, and reference to replayed Run Record when one is produced |
| `replay_run(run_reference)` | Internal | Run Reference of the original Run Record (resolved through Memory) | Replay Result entity bound to a Replay Attempt; references both the original Run Reference and the replayed Run Reference when produced |
| `reconstruct_replay_context(run_reference)` | Internal | Run Reference | Replay Attempt context (originalRunId, resolved Test Target, recorded Native Engine context, attemptedAt) used to drive Run; or unable-to-replay state when context cannot be reconstructed |
| `classify_replay_consistency(original_run_reference, replayed_run_reference)` | Internal | Original Run Reference and replayed Run Reference | Replay Result with classification (reproducible / inconsistent / unable to replay) and consistency summary derived from the two Run Records |
| `get_replay_result(run_reference)` | Internal | Run Reference (original) | Previously derived Replay Result for the original run, or unavailable state if no Replay Attempt has been made |
| `check_replay_availability(run_reference)` | Internal | Run Reference | Availability flag indicating whether a Replay Attempt can be reconstructed for the run (used by Orchestration eligibility evaluation) |

---

## Notes

- Replay submits execution through Run via `execute_with_engine_context` (or `execute`) so the same governed native engine path is reused (REQ-REP-002).
- A Replay Attempt may complete with `unable to replay` without producing a replayed Run Record (REQ-REP-004 assumption); Replay Result still preserves the original Run Reference.
- Orchestration consumes `get_replay_result` and `replay_run` for the integrated workflow and the top-level `novetest replay <run_id>` command.
