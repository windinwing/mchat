#!/usr/bin/env bash
# Print path to a Python >=3.10 usable for venv (pyenv / system / explicit names).
set -euo pipefail

try_python() {
  local bin="$1"
  [[ -n "$bin" && -x "$bin" ]] || return 1
  "$bin" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)' 2>/dev/null
}

# 1) Common command names (must actually run, not only exist as pyenv shims)
for name in python3.12 python3.11 python3; do
  if command -v "$name" >/dev/null 2>&1; then
    bin="$(command -v "$name")"
    if try_python "$bin"; then
      echo "$bin"
      exit 0
    fi
  fi
done

# 2) pyenv installed versions (newest first)
if command -v pyenv >/dev/null 2>&1; then
  while IFS= read -r ver; do
    [[ -n "$ver" ]] || continue
    bin="$(pyenv root)/versions/${ver}/bin/python"
    if try_python "$bin"; then
      echo "$bin"
      exit 0
    fi
  done < <(pyenv versions --bare 2>/dev/null | sort -Vr)
fi

echo "ERROR: No Python 3.10+ found. Install python3.12 or: pyenv install 3.12.0 && pyenv local 3.12.0" >&2
exit 1
