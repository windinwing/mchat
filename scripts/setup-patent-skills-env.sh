#!/usr/bin/env bash
# Print recommended .env lines for external patent skills (separate repo).
# Does not modify files unless --write is passed.

set -euo pipefail

PATENT_SKILLS_DIR="${PATENT_SKILLS_DIR:-${HOME}/dev/skills/patents}"
ENV_FILE="${MCHAT_ENV_FILE:-$(cd "$(dirname "$0")/.." && pwd)/src/backend/.env}"

lines() {
  cat <<EOF
# --- patent workflow showcase (external skills repo) ---
EXTRA_SKILLS_DIRS=${PATENT_SKILLS_DIR}
PATENT_SKILLS_SOURCE=${PATENT_SKILLS_DIR}
PATENT_WORKFLOW_SHOWCASE_ENABLED=true
PATENT_WORKFLOW_SEARCH_SKILL=patent-search
PATENT_WORKFLOW_REPORT_SKILL=patent-report
EOF
}

if [[ "${1:-}" == "--write" ]]; then
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing $ENV_FILE — copy from .env.example first"
    exit 1
  fi
  if grep -q '^EXTRA_SKILLS_DIRS=' "$ENV_FILE" 2>/dev/null; then
    echo "EXTRA_SKILLS_DIRS already set in $ENV_FILE — edit manually if needed"
  else
    echo "" >> "$ENV_FILE"
    lines >> "$ENV_FILE"
    echo "Appended patent showcase env to $ENV_FILE"
  fi
else
  echo "# Add to src/backend/.env (or export before make dev):"
  lines
  echo ""
  echo "# Then reload skills:"
  echo "  cd src/backend && python ../../scripts/reload-patent-skills.py"
fi
