#!/usr/bin/env bash
# Train a DEMO model on procedurally generated MRI phantoms.
#
# This proves the whole pipeline (data → training → checkpoint → serving) on a
# machine without the real dataset. The resulting model is NOT medically
# meaningful — train on a real dataset before using it for anything serious:
#
#   python -m training.train --data-dir data/brain-tumor --epochs 25
#
# Usage: ./scripts/train-demo-model.sh [per_class] [epochs] [img_size]
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

PER_CLASS="${1:-150}"
EPOCHS="${2:-12}"
IMG_SIZE="${3:-128}"
DATA_DIR="data/synthetic"
MODEL_DIR="data/models"

echo "==> Generating ${PER_CLASS} synthetic phantoms per class in ${DATA_DIR}"
python -m training.synthetic --out "${DATA_DIR}" --per-class "${PER_CLASS}" --size 192 --seed 7

echo "==> Training demo model (${EPOCHS} epochs, ${IMG_SIZE}px)"
python -m training.train \
  --data-dir "${DATA_DIR}" \
  --output-dir "${MODEL_DIR}" \
  --epochs "${EPOCHS}" \
  --img-size "${IMG_SIZE}" \
  --batch-size 16 \
  --val-fraction 0.2 \
  --tag demo \
  --notes "DEMO model trained on synthetic phantoms - pipeline validation only, not for diagnosis." \
  --export-torchscript

echo
echo "==> Demo model ready in ${MODEL_DIR}"
echo "    Start the server: ./scripts/run-dev.sh"
