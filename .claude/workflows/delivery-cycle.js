export const meta = {
  name: 'delivery-cycle',
  description: 'Run one Nove Test delivery cycle: work teams (parallel) → Main Branch merge+gate → Manual Test E2E. The CEO gates (plan approval, push) sit OUTSIDE this workflow.',
  phases: [
    { title: 'Execute', detail: 'work teams build slices in parallel worktrees → handoffs/' },
    { title: 'Merge', detail: 'Main Branch merges handoffs, runs pytest+mypy gate, commits → verifications/ (NO push)' },
    { title: 'Verify', detail: 'Manual Test runs E2E → findings/' },
  ],
}

// ---------------------------------------------------------------------------
// Driven by the PM-orchestrator (main session) AFTER the CEO approves the plan
// at Gate 1. Its return value feeds the Gate-2 report. Push is NOT done here.
//
//   Workflow({ name: 'delivery-cycle', args: PLAN })                              // preferred
//   Workflow({ scriptPath: '.claude/workflows/delivery-cycle.js', args: PLAN })   // fallback
//
// PLAN shape (built at plan-time, approved at Gate 1):
//   {
//     tasks: [ { team: 'novetest-run-team',
//                taskFile: 'agent-comms/tasks/run-team-2026-07-06-s0.md',
//                label: 'run' }, ... ],   // one per work team; dispatched in parallel
//     verify: true                         // false → doc-only cycle, skip Manual Test
//   }
// See agent-comms/decisions/2026-07-06-pm-orchestrated-delivery-cycle.md.
// ---------------------------------------------------------------------------

const HANDOFF = {
  type: 'object',
  properties: {
    team:        { type: 'string' },
    handoffFile: { type: 'string' },
    worktree:    { type: 'string' },
    gate:        { type: 'string', enum: ['green', 'red', 'n/a'] },
    dodClaims:   { type: 'array', items: { type: 'string' } },
    blocked:     { type: 'boolean' },
    note:        { type: 'string' },
  },
  required: ['team', 'gate', 'blocked'],
  additionalProperties: true,
}

const MERGE = {
  type: 'object',
  properties: {
    gate:             { type: 'string', enum: ['green', 'red'] },
    commits:          { type: 'array', items: { type: 'string' } },
    verificationFile: { type: 'string' },
    questionsFile:    { type: 'string' },
    note:             { type: 'string' },
  },
  required: ['gate'],
  additionalProperties: true,
}

const FINDINGS = {
  type: 'object',
  properties: {
    verdict:      { type: 'string', enum: ['passed', 'failed', 'partial', 'skipped'] },
    findingsFile: { type: 'string' },
    issues:       { type: 'array', items: { type: 'string' } },
    note:         { type: 'string' },
  },
  required: ['verdict'],
  additionalProperties: true,
}

const plan = args || {}
const tasks = Array.isArray(plan.tasks) ? plan.tasks : []
if (!tasks.length) {
  log('delivery-cycle: args.tasks is empty — nothing to dispatch.')
  return { ok: false, reason: 'empty-plan' }
}

// --- Stage 1: work teams in parallel (barrier: Main Branch needs every handoff) ---
phase('Execute')
log(`Dispatching ${tasks.length} work team(s) in parallel.`)
const built = (await parallel(tasks.map(t => () =>
  agent(
    [
      `You are ${t.team}, dispatched by the PM-orchestrator as a work stage of the delivery cycle.`,
      `Read and execute your task brief at ${t.taskFile} EXACTLY per your charter:`,
      `work in an isolated git worktree, run your verification gate, append a top WORKLOG.md entry,`,
      `write your handoff at agent-comms/handoffs/, and run python3 tools/regen_comms_index.py.`,
      `Do NOT merge, do NOT push, do NOT touch other teams' files.`,
      `If blocked, write agent-comms/questions/ and return blocked:true.`,
      `Return the handoff filename, worktree path, gate result, and the DoD bullets you believe closed.`,
    ].join(' '),
    { agentType: t.team, phase: 'Execute', label: `build:${t.label || t.team}`, schema: HANDOFF }
  )
))).filter(Boolean)

const ready   = built.filter(h => !h.blocked && h.gate !== 'red')
const blocked = built.filter(h => h.blocked || h.gate === 'red')
if (!ready.length) {
  log('delivery-cycle: no green handoffs — halting before merge. Orchestrator should re-plan.')
  return { ok: false, stage: 'execute', built, blocked }
}
if (blocked.length) {
  log(`${blocked.length} slice(s) blocked/red — carrying to the orchestrator; merging the ${ready.length} green one(s).`)
}

// --- Stage 2: Main Branch merges the green handoffs + runs the gate (commit, NO push) ---
phase('Merge')
const merge = await agent(
  [
    `You are novetest-main-branch-team, the merge stage of the delivery cycle.`,
    `Merge these ready handoffs into main per your charter: ${ready.map(h => h.handoffFile).filter(Boolean).join(', ')}.`,
    `Resolve conflicts surgically; run the FULL gate (uv run pytest -q tests/unit tests/integration AND uv run mypy);`,
    `commit one clean commit per slice; write agent-comms/verifications/ and regen the index.`,
    `COMMIT ONLY — do NOT push (push is the CEO's Gate 2, after this workflow returns).`,
    `If the gate fails, write agent-comms/questions/ and return gate:'red' with the failure summary.`,
    `Return the gate result, the commit hash(es), and the verifications/ filename.`,
  ].join(' '),
  { agentType: 'novetest-main-branch-team', phase: 'Merge', label: 'merge', schema: MERGE }
)
if (!merge || merge.gate === 'red') {
  log('delivery-cycle: merge gate RED (or merge agent returned nothing) — halting before verify.')
  return { ok: false, stage: 'merge', built, blocked, merge }
}

// --- Stage 3: Manual Test E2E (skipped for doc-only cycles) ---
let findings = { verdict: 'skipped', note: 'doc-only cycle or verify:false' }
if (plan.verify !== false) {
  phase('Verify')
  findings = (await agent(
    [
      `You are novetest-manual-test-team, the verify stage of the delivery cycle.`,
      `Your inbox is the open agent-comms/verifications/ file Main Branch just wrote`,
      merge.verificationFile ? `(${merge.verificationFile}; merged commit ${(merge.commits || [])[0] || 'see verification'}).` : `(merged commit ${(merge.commits || [])[0] || 'see verification'}).`,
      `Run the verification steps as written, then probe your own edge cases per your charter.`,
      `Write agent-comms/findings/ with a plain-language verdict for the PM's Gate-2 report, and regen the index.`,
      `Return your verdict and the findings/ filename.`,
    ].join(' '),
    { agentType: 'novetest-manual-test-team', phase: 'Verify', label: 'verify', schema: FINDINGS }
  )) || { verdict: 'skipped', note: 'manual-test agent returned null' }
} else {
  log('delivery-cycle: verify:false — skipping Manual Test (doc-only cycle).')
}

return { ok: true, built, blocked, merge, findings }
