"""Configuration loading and typed access.

Configuration is layered:

1. Built-in defaults (:data:`DEFAULT_CONFIG`) so the tool always runs.
2. An optional YAML/JSON file that overrides the defaults (deep-merged).
3. Explicit keyword overrides passed in code / from the CLI.

YAML support uses PyYAML when available and falls back to JSON otherwise, so
there is never a hard third-party dependency just to read config.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

try:  # optional dependency
    import yaml  # type: ignore

    _HAVE_YAML = True
except Exception:  # pragma: no cover - exercised only without PyYAML
    _HAVE_YAML = False


# ---------------------------------------------------------------------------
# Built-in defaults. These describe a small demonstration 12S1P pack so the
# self-test path is fully functional out of the box.
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "pack": {
        "series_cells": 12,          # cells in series
        "parallel_strings": 1,       # parallel strings
        "nominal_capacity_ah": 50.0,  # per-cell usable capacity
        "initial_soc": 0.55,         # 0..1
        "initial_temp_c": 25.0,
        "soh": 1.0,                  # pack state of health (capacity fade)
        "isolation_resistance_kohm": 50000.0,  # HV-to-chassis isolation
    },
    "cell": {
        "internal_resistance_ohm": 0.0025,
        "rc_resistance_ohm": 0.0015,
        "rc_capacitance_f": 5000.0,
        "rc2_resistance_ohm": 0.0008,   # second (slow) RC branch
        "rc2_capacitance_f": 60000.0,
        "r0_temp_coeff_per_c": 0.008,   # R0 rise per degC below reference
        "r0_soh_growth": 0.5,           # R0 growth fraction at SOH=0
        "thermal_mass_j_per_k": 850.0,
        "thermal_resistance_k_per_w": 5.0,
        "ambient_temp_c": 25.0,
    },
    "ecu": {
        # Protection thresholds enforced by the (simulated) BMS ECU.
        "cell_overvoltage_v": 4.20,
        "cell_undervoltage_v": 2.80,
        "over_temp_c": 55.0,
        "under_temp_c": -10.0,
        "over_current_charge_a": 150.0,
        "over_current_discharge_a": 200.0,
        "balancing_start_delta_v": 0.030,
        "balancing_current_a": 0.10,
        "critical_temp_c": 70.0,         # thermal-runaway warning threshold
        "isolation_min_kohm": 500.0,     # below this -> isolation fault
        "precharge_time_s": 0.2,         # precharge dwell before main contactor
    },
    "can": {
        "backend": "virtual",        # "virtual" (built-in) or "python-can"
        "channel": "hil0",
        "bitrate": 500000,
        "python_can_interface": "virtual",  # used only when backend=python-can
        "dbc_path": None,            # optional .dbc (needs cantools); None = built-in DB
    },
    "schedule": {
        "step_ms": 10.0,             # simulation/control step
        "realtime": False,           # pace loop to wall clock if True
    },
    "logging": {
        "level": "INFO",
        "signal_log": True,
    },
    "report": {
        "output_dir": "reports",
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *override* into a copy of *base*."""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _load_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if path.endswith((".yaml", ".yml")):
        if _HAVE_YAML:
            return yaml.safe_load(text) or {}
        raise RuntimeError(
            f"Cannot read YAML config {path!r}: PyYAML is not installed. "
            "Install it (pip install pyyaml) or use a .json config."
        )
    return json.loads(text)


@dataclass
class Config:
    """Typed, dotted-path accessor around the merged configuration dict."""

    data: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_CONFIG))

    @classmethod
    def load(
        cls,
        path: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> "Config":
        merged = copy.deepcopy(DEFAULT_CONFIG)
        if path:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Config file not found: {path}")
            merged = _deep_merge(merged, _load_file(path))
        if overrides:
            merged = _deep_merge(merged, overrides)
        return cls(merged)

    def get(self, dotted: str, default: Any = None) -> Any:
        """Return ``self.data["a"]["b"]`` for a dotted key ``"a.b"``."""
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, name: str) -> Dict[str, Any]:
        value = self.data.get(name, {})
        return value if isinstance(value, dict) else {}

    def __getitem__(self, key: str) -> Any:
        return self.data[key]
