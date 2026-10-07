#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${TMPDIR:-/tmp}/me-you-uvicorn.pid"

if [[ -s "$PID_FILE" ]]; then
  api_pid="$(<"$PID_FILE")"
  if [[ "$api_pid" =~ ^[0-9]+$ ]] && kill -0 "$api_pid" 2>/dev/null; then
    process_args="$(ps -p "$api_pid" -o args= || true)"
    if [[ "$process_args" == *uvicorn* && "$process_args" == *app.main:app* ]]; then
      kill -TERM "$api_pid"
      printf 'Stopped backend (pid %s).\n' "$api_pid"
    else
      printf 'PID file points to an unexpected process; refusing to stop pid %s.\n' "$api_pid" >&2
      exit 1
    fi
  fi
  rm -f "$PID_FILE"
fi

cd "$ROOT_DIR"
docker compose stop postgres