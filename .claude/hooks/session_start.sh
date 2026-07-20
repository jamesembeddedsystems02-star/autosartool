#!/usr/bin/env bash
# SessionStart hook: make sure the BMS HIL package and its dev tooling are
# importable so tests (pytest), linting (ruff) and type-checking (mypy) can run
# during a Claude Code (web or local) session. Idempotent and non-fatal.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 0

PY="${PYTHON:-python3}"

if ! "$PY" -c "import bms_hil" >/dev/null 2>&1; then
  echo "[session_start] installing bms-hil with dev extras ..."
  "$PY" -m pip install --quiet -e ".[dev]" ruff mypy >/dev/null 2>&1 \
    || echo "[session_start] editable install failed (continuing)"
fi

# Quick sanity check; never fail the session on it.
"$PY" -c "import bms_hil; print('[session_start] bms_hil', bms_hil.__version__, 'ready')" 2>/dev/null || true
exit 0
