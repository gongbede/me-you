#!/usr/bin/env bash
set -euo pipefail

backend_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON:-}"

if [[ -z "$python_bin" ]]; then
  if [[ -x /usr/local/py-utils/venvs/pytest/bin/python ]]; then
    python_bin=/usr/local/py-utils/venvs/pytest/bin/python
  else
    python_bin=python
  fi
fi

export PYTHONPATH="$backend_dir${PYTHONPATH:+:$PYTHONPATH}"
cd "$backend_dir"
exec "$python_bin" -m pytest "$@"