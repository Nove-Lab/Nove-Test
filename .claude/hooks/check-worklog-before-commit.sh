#!/usr/bin/env bash
# PreToolUse hook: block `git commit` when src/ or tests/ are staged but WORKLOG.md is not.
# Receives the PreToolUse JSON payload on stdin.
set -euo pipefail

input=$(cat)

# Cheap pre-filter: skip work entirely for Bash calls that do not mention `git commit`.
if ! printf '%s' "$input" | grep -q 'git commit'; then
  exit 0
fi

# Extract the actual command string from tool_input.command.
command=$(python3 - "$input" <<'PY'
import json, sys
try:
    data = json.loads(sys.argv[1])
    print(data.get("tool_input", {}).get("command", ""))
except Exception:
    print("")
PY
)

# Match `git commit` as a real subcommand (not `git commit-tree`, not inside a string).
# Accept the start of line or after a shell separator (&&, ||, ;, |, &, newline, space).
if ! printf '%s\n' "$command" | grep -qE '(^|[[:space:]&;|])git[[:space:]]+commit([[:space:]]|$)'; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

staged=$(git diff --cached --name-only 2>/dev/null || true)
if [ -z "$staged" ]; then
  exit 0
fi

src_staged=$(printf '%s\n' "$staged" | grep -E '^(src/|tests/)' || true)
worklog_staged=$(printf '%s\n' "$staged" | grep -E '^WORKLOG\.md$' || true)

if [ -n "$src_staged" ] && [ -z "$worklog_staged" ]; then
  cat >&2 <<'EOF'
BLOCKED: this commit modifies src/ or tests/ but does not stage WORKLOG.md.

Per CLAUDE.md "Multi-Agent Worklog Harness":
  1. Append a new entry to the top of WORKLOG.md (format documented in that file).
  2. Tick any newly-satisfied DoD bullets in design/implementation-plan/delivery-phasing.md.
  3. git add WORKLOG.md design/implementation-plan/delivery-phasing.md
  4. Retry the commit.
EOF
  exit 2
fi

exit 0
