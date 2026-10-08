#!/usr/bin/env bash
# Start the Flask development server.
#
#   ./scripts/run-dev.sh                 # http://localhost:5000
#   PORT=8080 ./scripts/run-dev.sh
#   BTD_DEVICE=cuda ./scripts/run-dev.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export BTD_HOST="${BTD_HOST:-0.0.0.0}"
export BTD_PORT="${PORT:-${BTD_PORT:-5000}}"

if [ ! -f data/models/model.pt ] && [ ! -f data/models/model_scripted.pt ]; then
  echo "!! No model found in data/models — the app will start but predictions return HTTP 503."
  echo "   Train one first:  ./scripts/train-demo-model.sh"
  echo
fi

exec python run.py --host "${BTD_HOST}" --port "${BTD_PORT}" "$@"
