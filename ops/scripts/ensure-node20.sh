#!/usr/bin/env bash
# Frontend dev requires Node.js 20+
set -euo pipefail

need="${MCHAT_NODE_MIN_MAJOR:-20}"
ver="$(node -v 2>/dev/null | sed 's/^v//' || echo 0)"
major="${ver%%.*}"

if [[ "${major:-0}" -ge "$need" ]]; then
  exit 0
fi

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [[ -s "$NVM_DIR/nvm.sh" ]]; then
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh"
  if nvm use 20 2>/dev/null || nvm use 22 2>/dev/null || nvm install 20; then
    major="$(node -v | sed 's/^v//' | cut -d. -f1)"
    [[ "${major:-0}" -ge "$need" ]] && exit 0
  fi
fi

echo "Node.js >= ${need} required (current: v${ver})"
echo "  Ubuntu: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs"
echo "  nvm:    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && nvm install 20"
exit 1
