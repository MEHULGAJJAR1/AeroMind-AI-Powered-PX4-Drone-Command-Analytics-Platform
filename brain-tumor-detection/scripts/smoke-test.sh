#!/usr/bin/env bash
# End-to-end smoke test against a running server.
#
#   ./scripts/run-dev.sh &          # in another terminal
#   ./scripts/smoke-test.sh         # or: BASE_URL=http://host:5000 ./scripts/smoke-test.sh
set -euo pipefail

cd "$(dirname "$0")/.."

BASE_URL="${BASE_URL:-http://127.0.0.1:${BTD_PORT:-5000}}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "==> Target: ${BASE_URL}"

echo "==> 1/5 health"
curl -fsS "${BASE_URL}/api/health" | python -c "import json,sys; d=json.load(sys.stdin)['data']; print('    status:', d['status'], '| model:', d['model_available'])"

echo "==> 2/5 generating a test MRI phantom"
python - <<PY
from training.synthetic import make_phantom
make_phantom(256, tumor=True, seed=1).convert("RGB").save("${TMP_DIR}/scan.png")
open("${TMP_DIR}/not-an-image.png", "wb").write(b"this is not an image")
PY

echo "==> 3/5 valid prediction"
curl -fsS -X POST "${BASE_URL}/api/predict" -F "image=@${TMP_DIR}/scan.png" | python -c "
import json, sys
d = json.load(sys.stdin)['data']['prediction']
print(f\"    label={d['label']} confidence={d['confidence']:.4f} probabilities={d['probabilities']}\")"

echo "==> 4/5 invalid file is rejected (expect HTTP 422)"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/api/predict" -F "image=@${TMP_DIR}/not-an-image.png")
echo "    HTTP ${code}"
[ "${code}" = "422" ] || { echo "    !! expected 422"; exit 1; }

echo "==> 5/5 history + stats"
curl -fsS "${BASE_URL}/api/predictions?limit=1" | python -c "import json,sys; d=json.load(sys.stdin)['data']; print('    history entries:', d['total'])"
curl -fsS "${BASE_URL}/api/stats" | python -c "import json,sys; d=json.load(sys.stdin)['data']; print('    tumor rate:', d.get('tumor_rate'), '| avg confidence:', d.get('average_confidence'))"

echo
echo "==> Smoke test passed."
