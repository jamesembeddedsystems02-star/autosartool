#!/usr/bin/env bash
# Simplest way to run the BMS HIL tool on macOS / Linux.
#   ./run.sh            -> interactive menu
#   ./run.sh test       -> run the test suite
#   ./run.sh demo       -> run the demo
# Double-click also works in most file managers.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3 is not installed. Install it from https://www.python.org/downloads/"
  read -r -p "Press Enter to close..." _
  exit 1
fi
exec "$PY" run_bms_hil.py "$@"
