#!/usr/bin/env bash
# Source in your shell for mchat dev: PATH + venv activate.
#   source scripts/env.sh
#   mchat skill list

if [[ -n "${BASH_VERSION:-}" ]]; then
  _MCHAT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
elif [[ -n "${ZSH_VERSION:-}" ]]; then
  _MCHAT_ROOT="$(cd "$(dirname "${(%):-%x}")/.." && pwd)"
else
  echo "source scripts/env.sh requires bash or zsh" >&2
  return 1 2>/dev/null || exit 1
fi

export MCHAT_ROOT="$_MCHAT_ROOT"
export PATH="$MCHAT_ROOT/bin:$MCHAT_ROOT/src/backend/venv/bin:$PATH"

if [[ -f "$MCHAT_ROOT/src/backend/venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$MCHAT_ROOT/src/backend/venv/bin/activate"
fi

unset _MCHAT_ROOT
