#!/usr/bin/env bash
# novetest-standup.sh — one-command morning briefing for the CEO.
#
# Automates Step 0 of CEO_ROUTINE.md: refreshes agent-comms/INDEX.md, then
# prints a prioritized, read-only snapshot of the project's coordination state.
# Changes nothing except INDEX.md (regenerated). Safe to run any time.
#
# Usage (from repo root or anywhere inside the repo):
#   ./tools/novetest-standup.sh

set -euo pipefail

# Resolve repo root from this script's location, so it works from any CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

COMMS="agent-comms"
TODAY="$(date +%Y-%m-%d)"

# Count *.md files in a comms channel (excludes .gitkeep). Prints an integer.
count_md() {
  local dir="$1"
  [ -d "$dir" ] || { echo 0; return; }
  find "$dir" -maxdepth 1 -name '*.md' -type f 2>/dev/null | wc -l | tr -d ' '
}

# List *.md basenames in a channel, indented; or "(none)".
list_md() {
  local dir="$1"
  if [ ! -d "$dir" ] || [ -z "$(find "$dir" -maxdepth 1 -name '*.md' -type f 2>/dev/null)" ]; then
    echo "     (none)"
    return
  fi
  find "$dir" -maxdepth 1 -name '*.md' -type f 2>/dev/null | sort | while read -r f; do
    echo "     - $(basename "$f")"
  done
}

# --- 0. Refresh the index so everything below is current --------------------
python3 tools/regen_comms_index.py >/dev/null 2>&1 || \
  echo "WARN: regen_comms_index.py failed — INDEX.md may be stale" >&2

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
HEAD_SHORT="$(git rev-parse --short HEAD 2>/dev/null || echo '?')"
if [ -z "$(git status --porcelain 2>/dev/null)" ]; then
  TREE="clean"
else
  TREE="DIRTY"
fi

echo "═══ Nove Test — Standup  $TODAY ═══"
echo "branch: $BRANCH @ $HEAD_SHORT    tree: $TREE"
echo

# --- Blockers ---------------------------------------------------------------
echo "BLOCKERS  ($COMMS/questions/)                    [$(count_md "$COMMS/questions")]"
list_md "$COMMS/questions"
echo

# --- Findings awaiting PM review --------------------------------------------
echo "FINDINGS awaiting PM review                      [$(count_md "$COMMS/findings")]"
list_md "$COMMS/findings"
echo

# --- In flight --------------------------------------------------------------
echo "IN FLIGHT"
echo "     tasks/          [$(count_md "$COMMS/tasks")]"
list_md "$COMMS/tasks" | sed 's/^/  /'
echo "     handoffs/       [$(count_md "$COMMS/handoffs")]"
list_md "$COMMS/handoffs" | sed 's/^/  /'
echo "     verifications/  [$(count_md "$COMMS/verifications")]"
list_md "$COMMS/verifications" | sed 's/^/  /'
echo

# --- Recent decisions (7d) --------------------------------------------------
echo "RECENT DECISIONS (last 7 days)"
recent_decisions="$(find "$COMMS/decisions" -maxdepth 1 -name '*.md' -type f -mtime -7 2>/dev/null | sort)"
if [ -z "$recent_decisions" ]; then
  echo "     (none)"
else
  printf '%s\n' "$recent_decisions" | while read -r f; do echo "     - $(basename "$f")"; done
fi
echo

# --- Recent commits ---------------------------------------------------------
echo "RECENT COMMITS"
git log --oneline -5 2>/dev/null | sed 's/^/     /' || echo "     (no history)"
echo

# --- Stale worktrees --------------------------------------------------------
WT_OTHER="$(git worktree list 2>/dev/null | grep -v "\[$BRANCH\]" || true)"
WT_COUNT="$(printf '%s' "$WT_OTHER" | grep -c . || true)"
echo "STALE WORKTREES (besides current)                [$WT_COUNT]"
if [ -z "$WT_OTHER" ]; then
  echo "     (none)"
else
  printf '%s\n' "$WT_OTHER" | sed 's/^/     /'
fi
echo

# --- Suggested entry point --------------------------------------------------
Q=$(count_md "$COMMS/questions")
F=$(count_md "$COMMS/findings")
H=$(count_md "$COMMS/handoffs")
V=$(count_md "$COMMS/verifications")
T=$(count_md "$COMMS/tasks")
if [ "$Q" -gt 0 ] || [ "$F" -gt 0 ]; then
  echo "-> Today: open blockers/findings exist. Convene PM (CEO_ROUTINE step 1) to triage first."
elif [ "$V" -gt 0 ]; then
  echo "-> Today: verifications waiting. Dispatch Manual Test (CEO_ROUTINE step 4)."
elif [ "$H" -gt 0 ]; then
  echo "-> Today: handoffs waiting. Dispatch Main Branch (CEO_ROUTINE step 3)."
elif [ "$T" -gt 0 ]; then
  echo "-> Today: tasks assigned, not yet picked up. Dispatch the work teams (CEO_ROUTINE step 2)."
else
  echo "-> Today: no in-flight work. Convene PM (CEO_ROUTINE step 1) to plan."
fi
