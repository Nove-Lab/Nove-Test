---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-06-10
slug: release-team-2026-06-10-v0.1.1-wheel-version-bump-and-tag
related:
  - agent-comms/history/2026-06-10-v0.1.0-inaugural-release-and-apache-2.0-license-adoption.md
  - agent-comms/decisions/2026-06-10-license-apache-2.0-with-cla.md
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
---

# Release team task: wheel-version bump (0.0.0 -> 0.1.1) + v0.1.1 tag push as first public-facing release

## Mission

Close the wheel-internal version mismatch surfaced by Manual Test
during the v0.1.0 cycle (history
`2026-06-10-v0.1.0-inaugural-release-and-apache-2.0-license-adoption.md`),
and push the **v0.1.1 git tag that becomes the first publicly
CEO-promoted Nove Test release**.

**Strategic positioning**:
- **v0.1.0** = inaugural license + tag landing; ships internally with
  `pyproject.toml::version = "0.0.0"`; **stays as internal validation
  tag**, never publicly promoted.
- **v0.1.1** = first public Nove Test release; user-observable wheel
  version aligns with the git tag.

Minimal slice: ONE file changed (`pyproject.toml`), one tag pushed,
zero src/tests/workflow modifications. Brief is correspondingly small.

## Pre-flight reading

1. `agent-comms/history/2026-06-10-v0.1.0-inaugural-release-and-apache-2.0-license-adoption.md` — yesterday's cycle's full context
2. `agent-comms/decisions/2026-06-10-license-apache-2.0-with-cla.md` — license decision (no re-validation needed)
3. `agent-comms/decisions/2026-05-14-install-script-hosting-url.md` — Amendment 2026-06-10 documents interim raw-URL policy (informational)
4. Current `pyproject.toml` — line 4 is the edit target

## File to modify (ONE)

### `pyproject.toml`

Current line 4:

```toml
version = "0.0.0"
```

Replace with:

```toml
version = "0.1.1"
```

**That is the entire source change.** Zero other edits.

Rationale: Manual Test §"Issues found / Nit #2" + history
§"Load-bearing learnings / Item 3" explicitly recommend this bump
before any public-facing release. The 1-line change resolves the
user-observable `installedVersion: "0.0.0"` mismatch with the git tag
that was the only blocker between the v0.1.0 state and a clean public
launch.

## Verification BEFORE pushing tag

Run these in order; cite output in the handoff:

```sh
# 1. mypy clean (sanity — zero src/ change so should remain green)
uv run mypy --strict src/novetest
# Expected: Success: no issues found in 93 source files

# 2. Test suite (baseline maintained — same numbers as v0.1.0 cycle)
uv run pytest -q tests/unit tests/integration
# Expected: 1229 passed + 23 skipped + 1 failed (the pre-existing
# dotnet-host-equip failure documented in prior cycles)

# 3. Wheel builds at the new version
rm -rf /tmp/v011-wheel
uv build --wheel --out-dir /tmp/v011-wheel
ls /tmp/v011-wheel/
# Expected: novetest-0.1.1-py3-none-any.whl present (file name reflects bump)

# 4. The installed CLI reports the new version
uv pip install --force-reinstall /tmp/v011-wheel/novetest-0.1.1-py3-none-any.whl
uv run novetest --version --output json
# Expected: "installedVersion": "0.1.1" in the envelope's data block
```

Bullet 4 is the LOAD-BEARING gate — it proves the mismatch is closed.
Cite the verbatim `--version --output json` output in the handoff.

## Procedural posture — "일괄" pattern continues

Per the precedent established in the v0.1.0 cycle (recorded in
history §"Load-bearing learnings / Item 4: Release team self-merge via
'일괄' directive"), Release team is **pre-authorized to FF-merge to
`main` within the same session** for this slice because it matches the
safe profile:

- Single-team slice (no cross-team dependencies)
- Zero `src/novetest/**` and zero `tests/**` modifications
- Single-file footprint (`pyproject.toml`) cannot conflict with any
  other in-flight worktree
- Trivial 1-line edit; no test surface drift

Main Branch team is NOT separately invoked. Release team does:
worktree -> 1-line edit -> FF-merge to main -> tag push -> handoff.

## v0.1.1 tag push procedure

After the pyproject.toml change is FF-merged to `main`:

1. Verify `ci.yml` is green on the merged HEAD:
   ```sh
   gh run list --workflow ci.yml --branch main --limit 3
   ```

2. Verify no pre-existing v0.1.1 tag:
   ```sh
   gh release list --limit 5
   git tag --list | grep v0.1
   ```
   Expected: v0.1.0 exists; v0.1.1 does NOT exist yet.

3. Create + push annotated tag:
   ```sh
   git tag -a v0.1.1 -m "Nove Test v0.1.1 — first public release; wheel-internal version aligned with git tag"
   git push origin v0.1.1
   ```

4. `release-test.yml` auto-triggers on the v0.1.1 tag push (same 5-job
   pipeline as v0.1.0 cycle):
   - 3 PyApp builds (linux-x86_64, linux-aarch64, macos-universal2) + .sha256 sidecars
   - install-script-e2e smoke (localhost HTTP fixture)
   - `release` job creates draft GitHub Release `v0.1.1` with all 6 assets

5. Verify the draft release exists:
   ```sh
   gh release view v0.1.1
   ```
   Confirm `isDraft: true` and 6 attached assets at expected byte
   sizes (similar to v0.1.0's 6.18M / 6.72M / 12.18M binaries + ~88-92
   byte sidecars; slight byte drift is normal across rebuilds).

6. **Do NOT promote v0.1.1 to public.** That is CEO's separate action
   via GitHub UI or `gh release edit v0.1.1 --draft=false`.

7. **Do NOT delete the existing v0.1.0 draft release.** It stays as
   the internal validation artifact. CEO decides at promotion time
   whether to delete it for tidiness or keep as historical record.

## Empirical curl-pipe-sh smoke (NEW DoD)

After v0.1.1 draft release exists + assets propagate (~30-90s CDN
propagation; wait 2 minutes before retry), run the same auth-mirror
pattern Manual Test used in the v0.1.0 cycle:

```sh
# Clean container or dev host
mkdir -p /tmp/v011-smoke && cd /tmp/v011-smoke

# Mirror the v0.1.1 draft assets (gh CLI carries auth token)
gh release download v0.1.1 -R Nove-Lab/Nove-Test \
  -p 'novetest-linux-x86_64*' -D ./mirror/v0.1.1

# Serve via localhost
python3 -m http.server 28101 >/tmp/http.log 2>&1 &

# Fetch install.sh from v0.1.1 tag's snapshot (immutable; recommended over main for smoke)
curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/v0.1.1/scripts/install.sh \
  -o install.sh
chmod +x install.sh

# Install with version + base-URL pins (since draft is auth-gated)
NOVETEST_INSTALL_BASE_URL=http://127.0.0.1:28101 \
  NOVETEST_INSTALL_VERSION=v0.1.1 \
  NOVETEST_INSTALL_PREFIX=/tmp/v011-smoke/install-prefix \
  ./install.sh

# CRITICAL: verify installedVersion in envelope matches v0.1.1
/tmp/v011-smoke/install-prefix/novetest --version --output json
```

Expected: `"installedVersion": "0.1.1"` in the envelope's data block.

If your dev host has incompatible glibc (Ubuntu 22.04 / 2.35 vs the
binary's 2.39 dep), the binary will fail to execute locally — that's
expected per the v0.1.0 cycle's findings. The `release-test.yml::install-script-e2e`
job runs the same flow on ubuntu-latest (24.04 / glibc 2.39) where it
DOES succeed; cite that as the load-bearing evidence in handoff.

## Out of scope (explicitly NOT this slice)

- README promotion to repo root — PM territory; handled in PM cycle-close
- v0.1.0 draft release deletion — CEO discretion at v0.1.1 promotion time
- Any other code/test changes
- DNS routing / Cloudflare setup / homepage hosting (decision Amendment 2026-06-10 documents the deferred status)
- CLA Assistant bot OAuth setup (still post-v0.1.1)
- THIRD_PARTY_NOTICES expansion beyond what's already shipped at v0.1.0
- Any decision document modifications (the v0.1.1 launch is governed by the existing license + install-URL decisions; no new policy)

## Definition of done

10 bullets:

1. [ ] `pyproject.toml::version = "0.1.1"` (1-line change verified in diff)
2. [ ] `uv build --wheel` produces `novetest-0.1.1-py3-none-any.whl` (filename verifies)
3. [ ] `uv run mypy --strict src/novetest` clean (93 source files unchanged)
4. [ ] `uv run pytest -q tests/unit tests/integration` baseline maintained (1229 passed + 23 skipped + 1 pre-existing dotnet failure)
5. [ ] `uv run novetest --version --output json` returns `installedVersion: "0.1.1"` (the load-bearing gate)
6. [ ] FF-merged to `main` (per 일괄 pattern); cite merge SHA
7. [ ] `v0.1.1` annotated git tag pushed
8. [ ] `release-test.yml` run on `v0.1.1` tag GREEN (5/5 jobs); cite run number
9. [ ] Draft GitHub Release `v0.1.1` exists with 6 assets; cite `gh release view v0.1.1` output
10. [ ] Empirical mirror-smoke (per §"Empirical curl-pipe-sh smoke" above) returns `installedVersion: "0.1.1"`; cite verbatim envelope output

Plus standard hygiene:
11. [ ] WORKLOG entry (this slice DOES touch `pyproject.toml` which is Release territory; entry per format)
12. [ ] Handoff at `agent-comms/handoffs/release-team-2026-06-10-v0.1.1-wheel-version-bump-and-tag.md` with DoD-bullets-believed-closed list
13. [ ] `python3 tools/regen_comms_index.py`

## Failure modes to anticipate (PM-pinned)

1. **CI matrix transient flake** (per v0.1.0 cycle's empirically-exonerated `27249991740` runner-provisioning flake on Windows × py3.12 step 5 "Install uv"). If `ci.yml` shows red on the merge commit but the failure is step-#5-runner-provisioning (Install uv / Install Rust / etc., 1-second failures BEFORE tests run), surface as exonerated transient with the per-step JSON forensics. Tests must actually run and pass for a real regression.

2. **release-test.yml asset byte-size drift** — rebuilds produce
   slightly different binary sizes due to PyApp / python-build-standalone
   non-determinism. Acceptable: ±5% size drift vs v0.1.0 baselines. Not
   a failure.

3. **CDN propagation lag for the draft release assets** — wait 2 minutes
   after the `release` job completes before running the empirical smoke.
   GH Releases CDN can take 30-90s to propagate fresh draft assets to
   the `gh release download` path.

4. **uv build failing on the new version string** — `0.1.1` is a fully
   PEP 440-compliant version; should work without issue. If it fails,
   the message will be clear (PEP 440 mismatch); surface as a question
   without retry.

5. **glibc mismatch on dev host** — expected when binary built against
   newer glibc. Document in handoff per v0.1.0 cycle's pattern; the
   release-test.yml install-script-e2e job (ubuntu-latest 24.04 /
   glibc 2.39) IS the binding empirical evidence that the binary runs
   correctly on the canonical target.

## Handoff "DoD bullets believed closed" list (template)

In the handoff include:

```markdown
## DoD bullets believed closed — PM to verify and tick

This slice closes:

- v0.1.0 cycle's wheel-version-mismatch nit (Manual Test findings §"Issues found / Nit #2") — empirically resolved by DoD #5 + #10 above
- v0.1.1 milestone: first public-facing Nove Test release tag exists with verified-clean version envelope

This slice re-validates (no new DoD ticks; all already [x]):
- Phase 0 §"Definition-of-done" bullet #1 (ci.yml GREEN at merge HEAD)
- Phase 0 §"Definition-of-done" bullet #4 (release-test.yml GREEN at v0.1.1 tag)
- Phase 0 §"Definition-of-done" bullet #5 (install-script-e2e job in release-test.yml runs successfully)
- Phase 0 §"Definition-of-done" bullet #6 (SHA-256 verification via install.sh fires correctly)
```

## Cycle close direction

After Manual Test verifies (or you self-validate via the empirical smoke
per the 일괄 pattern) and PM cycle-closes:

- CEO promotes draft GitHub Release `v0.1.1` to public via GitHub UI or
  `gh release edit v0.1.1 --draft=false` — **THE actual launch moment**
- CEO decides whether to delete the v0.1.0 draft release (tidy) or keep
  as internal validation historical record
- PM promotes README v3 (currently at `design/marketing/README-v0.1.1-draft.md`)
  to repo root `README.md` in cycle-close commit
- PM may distill into a small history entry capturing the bump
  + first-public-promotion moment

## Reporting back (in handoff)

- Worktree path / branch / commit SHAs (pre-bump + post-bump)
- Verbatim diff of `pyproject.toml` (1 line)
- All verification command outputs (mypy, pytest, uv build filename, --version envelope)
- ci.yml run number + URL for the merged HEAD
- release-test.yml run number + URL for v0.1.1 tag
- `gh release view v0.1.1` output (isDraft + 6 assets)
- Empirical smoke command + verbatim `novetest --version --output json` output
- WORKLOG entry text
- Confirmation that v0.1.0 draft release was NOT deleted
- Any release-pipeline surprises
