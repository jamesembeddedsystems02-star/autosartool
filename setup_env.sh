#!/usr/bin/env bash
# Create and provision a Python virtual environment for the BMS HIL tool.
#
# Usage:
#   ./setup_env.sh          # runtime env (.venv) + editable install
#   ./setup_env.sh --dev    # also install dev/test deps (pytest, numpy, ...)
#
# After running:  source .venv/bin/activate  &&  bms-hil selftest
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VENV_DIR="${VENV_DIR:-.venv}"
PYTHON="${PYTHON:-python3}"
DEV=0
[[ "${1:-}" == "--dev" ]] && DEV=1

echo ">> Using interpreter: $("$PYTHON" --version 2>&1)"

if [[ ! -d "$VENV_DIR" ]]; then
  echo ">> Creating virtual environment in $VENV_DIR"
  "$PYTHON" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo ">> Upgrading pip"
python -m pip install --upgrade pip >/dev/null

if [[ "$DEV" == "1" ]]; then
  echo ">> Installing dev dependencies"
  pip install -r requirements-dev.txt
  pip install -e ".[dev,hardware,config]"
else
  echo ">> Installing runtime dependencies"
  pip install -r requirements.txt || echo "   (optional deps failed; core still works)"
  pip install -e .
fi

echo ""
echo ">> Environment ready. Activate it with:"
echo "     source $VENV_DIR/bin/activate"
echo ">> Then try:"
echo "     bms-hil selftest"
echo "     bms-hil demo"
echo "     bms-hil test"
