#!/usr/bin/env bash
# Local development: backend on :8000 (auto-reload) + frontend on :5173 (hot reload).
# Usage: ./dev.sh            password "dev", unless set in .env, backend/.env or the environment
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x backend/.venv/bin/uvicorn ]; then
  echo "Setting up backend/.venv…"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements-dev.txt
fi
if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend packages…"
  (cd frontend && npm install --no-audit --no-fund)
fi

# Environment variables override the .env files, so only fall back to "dev" when no
# password is configured anywhere (BAW_PASSWORD or BAW_PASSWORD_HASH in .env or backend/.env).
if [ -z "${BAW_PASSWORD:-}${BAW_PASSWORD_HASH:-}" ] && ! grep -qs '^BAW_PASSWORD' .env backend/.env; then
  export BAW_PASSWORD=dev
  echo "App password: dev"
fi

(cd backend && exec .venv/bin/uvicorn app.main:create_app --factory \
  --host 127.0.0.1 --port 8000 --reload --reload-dir app) &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT

echo "Open http://localhost:5173"
cd frontend && npm run dev
