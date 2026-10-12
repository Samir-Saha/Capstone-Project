#!/usr/bin/env bash
# Starts Reps on macOS/Linux: the Python API and the web app.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x apps/api/.venv/bin/python ]; then
  python3 -m venv apps/api/.venv
  apps/api/.venv/bin/pip install -q -e "apps/api[dev]"
fi
[ -d apps/web/node_modules ] || (cd apps/web && npm install)
[ -f .env ] && set -a && . ./.env && set +a

(cd apps/api && .venv/bin/python -m uvicorn reps_api.main:app --port 8000) &
API=$!
trap 'kill $API' EXIT
cd apps/web && npm run dev
