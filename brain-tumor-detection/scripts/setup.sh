#!/usr/bin/env bash
# Create a virtualenv and install dependencies.
#
#   ./scripts/setup.sh            # standard install (PyPI torch)
#   TORCH_VARIANT=cpu ./scripts/setup.sh   # smaller CPU-only PyTorch
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
VENV_DIR="${VENV_DIR:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TORCH_VARIANT="${TORCH_VARIANT:-}"

echo "==> BrainScan AI setup"
echo "    project : ${PROJECT_ROOT}"
echo "    python  : $(${PYTHON_BIN} --version 2>&1)"

if [ ! -d "${VENV_DIR}" ]; then
  echo "==> Creating virtualenv in ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip >/dev/null

if [ "${TORCH_VARIANT}" = "cpu" ]; then
  echo "==> Installing CPU-only PyTorch"
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
  pip install -r requirements.txt
else
  echo "==> Installing requirements.txt"
  pip install -r requirements.txt
fi

mkdir -p data/models data/uploads

echo
echo "==> Setup complete."
echo "    activate : source ${VENV_DIR}/bin/activate"
echo "    train    : ./scripts/train-demo-model.sh      (or train on a real dataset)"
echo "    run      : ./scripts/run-dev.sh"
