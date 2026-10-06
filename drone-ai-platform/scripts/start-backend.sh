#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR/backend"
source "$APP_DIR/.venv/bin/activate"
if [[ -f "$APP_DIR/.env" ]]; then set -a; source "$APP_DIR/.env"; set +a; fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
