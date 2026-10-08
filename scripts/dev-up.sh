#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_BIN="$BACKEND_DIR/.venv/bin"
PID_FILE="${TMPDIR:-/tmp}/me-you-uvicorn.pid"
LOG_FILE="${TMPDIR:-/tmp}/me-you-uvicorn.log"

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  printf 'backend/.env was missing; copied backend/.env.example to backend/.env.\n'
fi

if [[ ! -x "$VENV_BIN/alembic" || ! -x "$VENV_BIN/uvicorn" ]]; then
  printf 'Backend dependencies are missing; create backend/.venv and install backend/requirements.txt.\n' >&2
  exit 1
fi

cd "$ROOT_DIR"
docker compose up -d --wait postgres

(
  cd "$BACKEND_DIR"
  "$VENV_BIN/alembic" upgrade head
)

if [[ -s "$PID_FILE" ]]; then
  api_pid="$(<"$PID_FILE")"
  if [[ "$api_pid" =~ ^[0-9]+$ ]] && kill -0 "$api_pid" 2>/dev/null; then
    if curl --fail --silent http://127.0.0.1:8000/health/ready >/dev/null; then
      printf 'Backend already healthy (pid %s).\n' "$api_pid"
      exit 0
    fi
    printf 'Tracked backend process %s is running but not healthy; inspect %s or run dev-down.\n' "$api_pid" "$LOG_FILE" >&2
    exit 1
  fi
  rm -f "$PID_FILE"
fi

if curl --fail --silent --max-time 2 http://127.0.0.1:8000/health/ready >/dev/null; then
  printf 'An untracked API is already listening on port 8000; refusing to start a duplicate.\n' >&2
  exit 1
fi

cd "$BACKEND_DIR"
nohup "$VENV_BIN/uvicorn" app.main:app --host 0.0.0.0 --port 8000 >>"$LOG_FILE" 2>&1 </dev/null &
printf '%s\n' "$!" > "$PID_FILE"

if ! curl --fail --silent --show-error --retry 20 --retry-connrefused --retry-delay 1 --retry-max-time 25 -o /dev/null http://127.0.0.1:8000/health/ready; then
  printf 'Backend failed to become healthy; recent log output follows:\n' >&2
  tail -n 40 "$LOG_FILE" >&2
  exit 1
fi

printf 'Backend ready at http://localhost:8000 (pid %s). Log: %s\n' "$(<"$PID_FILE")" "$LOG_FILE"