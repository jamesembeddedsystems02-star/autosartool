#!/usr/bin/env python3
"""BMS HIL — single-file edition.

A complete, self-contained Hardware-in-the-Loop (HIL) test tool for a Battery
Management System (BMS) ECU. It simulates a battery pack, runs a reference BMS
ECU control loop against it, injects faults, and executes an automated test
suite — all in ONE file with the Python standard library only.

    No install. No virtualenv. No dependencies. Just:

        python run_bms_hil.py            # interactive menu
        python run_bms_hil.py selftest   # quick health check
        python run_bms_hil.py demo       # charge -> discharge -> fault demo
        python run_bms_hil.py test       # full regression suite + HTML report

(The `src/bms_hil` package in this repo is the full, modular version with a
virtual/real CAN transport, DBC/cantools decoding and UDS diagnostics. This
single file mirrors its physics and ECU logic in a copy-and-run form.)
"""

from __future__ import annotations

import argparse
import html
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Configuration — edit these to model your own pack / ECU calibration.
# ---------------------------------------------------------------------------
CONFIG: Dict[str, float] = {
    # Pack
    "series_cells": 12,
    "nominal_capacity_ah": 50.0,
    "initial_soc": 0.55,
    "initial_temp_c": 25.0,
    "soh": 1.0,
    "isolation_kohm": 50000.0,
    # Cell (2-RC Thevenin + lumped thermal)
    "r0_ohm": 0.0025,
    "rc1_r_ohm": 0.0015,
    "rc1_c_f": 5000.0,
    "rc2_r_ohm": 0.0008,
    "rc2_c_f": 60000.0,
    "r0_temp_coeff_per_c": 0.008,
    "thermal_mass_j_per_k": 850.0,
    "thermal_resistance_k_per_w": 5.0,
    "ambient_temp_c": 25.0,
    # ECU protection thresholds
    "cell_overvoltage_v": 4.20,
    "cell_undervoltage_v": 2.80,
    "over_temp_c": 55.0,
    "under_temp_c": -10.0,
    "critical_temp_c": 70.0,
    "over_current_charge_a": 150.0,
    "over_current_discharge_a": 200.0,
    "isolation_min_kohm": 500.0,
    "balancing_start_delta_v": 0.030,
    "balancing_current_a": 0.10,
    "precharge_time_s": 0.2,
    # Loop
    "step_ms": 10.0,
    "report_dir": "reports",
}

# Representative NMC open-circuit-voltage curve (SOC -> OCV).
_OCV_TABLE: List[Tuple[float, float]] = [
    (0.00, 3.00), (0.05, 3.40), (0.10, 3.55), (0.20, 3.63), (0.30, 3.68),
    (0.40, 3.73), (0.50, 3.78), (0.60, 3.85), (0.70, 3.93), (0.80, 4.02),
    (0.90, 4.11), (1.00, 4.20),
]
_REF_TEMP_C = 25.0


def ocv_from_soc(soc: float) -> float:
    s = min(1.0, max(0.0, soc))
    if s <= _OCV_TABLE[0][0]:
        return _OCV_TABLE[0][1]
    if s >= _OCV_TABLE[-1][0]:
        return _OCV_TABLE[-1][1]
    for (s0, v0), (s1, v1) in zip(_OCV_TABLE, _OCV_TABLE[1:]):
        if s0 <= s <= s1:
            return v0 + (s - s0) / (s1 - s0) * (v1 - v0)
    return _OCV_TABLE[-1][1]


# ---------------------------------------------------------------------------
# Fault-bit definitions
# ---------------------------------------------------------------------------
class Fault:
    OVERVOLTAGE = 1 << 0
    UNDERVOLTAGE = 1 << 1
    OVERTEMP = 1 << 2
    UNDERTEMP = 1 << 3
    OVERCURRENT_CHARGE = 1 << 4
    OVERCURRENT_DISCHARGE = 1 << 5
    CELL_IMBALANCE = 1 << 6
    SENSOR_FAULT = 1 << 7
    ISOLATION = 1 << 8
    THERMAL_RUNAWAY = 1 << 9

    _ALL = [
        ("OVERVOLTAGE", OVERVOLTAGE), ("UNDERVOLTAGE", UNDERVOLTAGE),
        ("OVERTEMP", OVERTEMP), ("UNDERTEMP", UNDERTEMP),
        ("OVERCURRENT_CHARGE", OVERCURRENT_CHARGE),
        ("OVERCURRENT_DISCHARGE", OVERCURRENT_DISCHARGE),
        ("CELL_IMBALANCE", CELL_IMBALANCE), ("SENSOR_FAULT", SENSOR_FAULT),
        ("ISOLATION", ISOLATION), ("THERMAL_RUNAWAY", THERMAL_RUNAWAY),
    ]

    @staticmethod
    def names(flags: int) -> List[str]:
        return [n for n, b in Fault._ALL if flags & b]


# ---------------------------------------------------------------------------
# Plant: single cell + pack
# ---------------------------------------------------------------------------
@dataclass
class Cell:
    soc: float
    temp_c: float
    soh: float = 1.0
    v_rc1: float = 0.0
    v_rc2: float = 0.0
    v_terminal: float = 0.0
    # fault-injection knobs
    voltage_offset_v: float = 0.0
    temp_offset_c: float = 0.0
    open_circuit: bool = False

    def __post_init__(self) -> None:
        self.v_terminal = ocv_from_soc(self.soc)

    def r0_at(self, t: float) -> float:
        factor = 1.0 + CONFIG["r0_temp_coeff_per_c"] * (_REF_TEMP_C - t)
        return max(1e-6, CONFIG["r0_ohm"] * factor)

    @property
    def eff_capacity_ah(self) -> float:
        return max(1e-6, CONFIG["nominal_capacity_ah"] * self.soh)

    @property
    def measured_v(self) -> float:
        return self.v_terminal + self.voltage_offset_v

    @property
    def measured_t(self) -> float:
        return self.temp_c + self.temp_offset_c

    def step(self, current_a: float, dt: float) -> None:
        i = 0.0 if self.open_circuit else current_a
        self.soc -= i * dt / (3600.0 * self.eff_capacity_ah)
        self.soc = min(1.0, max(0.0, self.soc))
        tau1 = max(1e-6, CONFIG["rc1_r_ohm"] * CONFIG["rc1_c_f"])
        self.v_rc1 += ((i / CONFIG["rc1_c_f"]) - (self.v_rc1 / tau1)) * dt
        tau2 = max(1e-6, CONFIG["rc2_r_ohm"] * CONFIG["rc2_c_f"])
        self.v_rc2 += ((i / CONFIG["rc2_c_f"]) - (self.v_rc2 / tau2)) * dt
        r0 = self.r0_at(self.temp_c)
        self.v_terminal = ocv_from_soc(self.soc) - i * r0 - self.v_rc1 - self.v_rc2
        p_loss = (i * i * r0
                  + self.v_rc1 ** 2 / max(1e-9, CONFIG["rc1_r_ohm"])
                  + self.v_rc2 ** 2 / max(1e-9, CONFIG["rc2_r_ohm"]))
        cooling = (self.temp_c - CONFIG["ambient_temp_c"]) / CONFIG["thermal_resistance_k_per_w"]
        self.temp_c += (p_loss - cooling) / CONFIG["thermal_mass_j_per_k"] * dt


class Pack:
    def __init__(self) -> None:
        self.soh = float(CONFIG["soh"])
        self.isolation_kohm = float(CONFIG["isolation_kohm"])
        self.cells = [
            Cell(soc=CONFIG["initial_soc"], temp_c=CONFIG["initial_temp_c"], soh=self.soh)
            for _ in range(int(CONFIG["series_cells"]))
        ]
        self.current_a = 0.0

    def step(self, current_a: float, dt: float) -> None:
        self.current_a = current_a
        for c in self.cells:
            c.step(current_a, dt)

    # measurements
    @property
    def voltages(self) -> List[float]:
        return [c.measured_v for c in self.cells]

    @property
    def min_v(self) -> float:
        return min(self.voltages)

    @property
    def max_v(self) -> float:
        return max(self.voltages)

    @property
    def delta_v(self) -> float:
        return self.max_v - self.min_v

    @property
    def pack_v(self) -> float:
        return sum(self.voltages)

    @property
    def max_temp(self) -> float:
        return max(c.measured_t for c in self.cells)

    @property
    def avg_soc(self) -> float:
        return sum(c.soc for c in self.cells) / len(self.cells)

    def bleed(self, dt: float) -> None:
        thr = CONFIG["balancing_start_delta_v"]
        cur = CONFIG["balancing_current_a"]
        lo = self.min_v
        for c in self.cells:
            if (c.measured_v - lo) >= thr:
                c.soc -= cur * dt / (3600.0 * c.eff_capacity_ah)
                c.soc = min(1.0, max(0.0, c.soc))


# ---------------------------------------------------------------------------
# Reference BMS ECU (device-under-test stand-in)
# ---------------------------------------------------------------------------
OPEN, PRECHARGE, CLOSED = "OPEN", "PRECHARGE", "CLOSED"


class Ecu:
    def __init__(self) -> None:
        self.state = OPEN
        self.fault_flags = 0
        self.soc_pct = CONFIG["initial_soc"] * 100.0
        self.soh_pct = 100.0
        self.pack_v = 0.0
        self.current_a = 0.0
        self.max_temp = 25.0
        self.isolation_kohm = CONFIG["isolation_kohm"]
        self.balancing_active = False
        self.thermal_runaway = False
        self._precharge_t = 0.0
        self._seen = False

    @property
    def contactor_closed(self) -> bool:
        return self.state == CLOSED

    def measure(self, pack: Pack) -> None:
        self.pack_v = pack.pack_v
        self.current_a = pack.current_a
        self.soc_pct = pack.avg_soc * 100.0
        self.soh_pct = pack.soh * 100.0
        self.max_temp = pack.max_temp
        self.isolation_kohm = pack.isolation_kohm
        self._min_v = pack.min_v
        self._max_v = pack.max_v
        self._delta_v = pack.delta_v
        self._seen = True

    def update(self, dt: float) -> None:
        if not self._seen:
            return
        f = self.fault_flags
        if self._max_v >= CONFIG["cell_overvoltage_v"]:
            f |= Fault.OVERVOLTAGE
        if self._min_v <= CONFIG["cell_undervoltage_v"]:
            f |= Fault.UNDERVOLTAGE
        if self.max_temp >= CONFIG["over_temp_c"]:
            f |= Fault.OVERTEMP
        if self.max_temp <= CONFIG["under_temp_c"]:
            f |= Fault.UNDERTEMP
        if self.max_temp >= CONFIG["critical_temp_c"]:
            f |= Fault.THERMAL_RUNAWAY
            self.thermal_runaway = True
        if self.current_a < -CONFIG["over_current_charge_a"]:
            f |= Fault.OVERCURRENT_CHARGE
        if self.current_a > CONFIG["over_current_discharge_a"]:
            f |= Fault.OVERCURRENT_DISCHARGE
        if self.isolation_kohm < CONFIG["isolation_min_kohm"]:
            f |= Fault.ISOLATION
        if self._max_v > 5.5 or self._min_v < 0.5:
            f |= Fault.SENSOR_FAULT

        if f != self.fault_flags:
            log(f"    ECU fault asserted: {', '.join(Fault.names(f & ~self.fault_flags))}")
        self.fault_flags = f

        # Contactor state machine with precharge dwell.
        if self.fault_flags:
            self.state = OPEN
            self._precharge_t = 0.0
        elif self.state == OPEN:
            self.state = PRECHARGE
            self._precharge_t = 0.0
        elif self.state == PRECHARGE:
            self._precharge_t += dt
            if self._precharge_t >= CONFIG["precharge_time_s"]:
                self.state = CLOSED

        self.balancing_active = (
            self.contactor_closed and self._delta_v >= CONFIG["balancing_start_delta_v"]
        )

    def clear_faults(self) -> None:
        self.fault_flags = 0
        self.thermal_runaway = False

    @property
    def avail_discharge_kw(self) -> float:
        if self.fault_flags:
            return 0.0
        return max(0.0, self.pack_v) * CONFIG["over_current_discharge_a"] / 1000.0

    @property
    def avail_charge_kw(self) -> float:
        if self.fault_flags:
            return 0.0
        return max(0.0, self.pack_v) * CONFIG["over_current_charge_a"] / 1000.0


# ---------------------------------------------------------------------------
# HIL bench: closes the loop between pack and ECU, logs signals
# ---------------------------------------------------------------------------
class Bench:
    def __init__(self) -> None:
        self.pack = Pack()
        self.ecu = Ecu()
        self.dt = CONFIG["step_ms"] / 1000.0
        self.t = 0.0
        self._cmd = 0.0
        self.log_rows: List[Dict[str, float]] = []

    def command(self, current_a: float) -> None:
        self._cmd = current_a

    def clear_log(self) -> None:
        self.log_rows.clear()

    def run_for(self, seconds: float) -> None:
        for _ in range(max(1, int(round(seconds / self.dt)))):
            cur = self._cmd
            if self.ecu._seen and not self.ecu.contactor_closed:
                cur = 0.0  # open contactor isolates the load
            self.pack.step(cur, self.dt)
            self.ecu.measure(self.pack)
            if self.ecu.balancing_active:
                self.pack.bleed(self.dt)
            self.ecu.update(self.dt)
            self.t += self.dt
            self.log_rows.append({
                "time_s": self.t, "pack_v": self.pack.pack_v, "current_a": self.pack.current_a,
                "soc_pct": self.pack.avg_soc * 100.0, "min_cell_v": self.pack.min_v,
                "max_cell_v": self.pack.max_v, "delta_v": self.pack.delta_v,
                "max_temp_c": self.pack.max_temp, "fault_flags": float(self.ecu.fault_flags),
                "contactor": 1.0 if self.ecu.contactor_closed else 0.0,
            })

    def settle(self, seconds: float = 0.3) -> None:
        self.run_for(seconds)

    # log helpers
    def col(self, name: str) -> List[float]:
        return [r[name] for r in self.log_rows]

    def col_max(self, name: str) -> float:
        vals = self.col(name)
        return max(vals) if vals else float("nan")

    def col_min(self, name: str) -> float:
        vals = self.col(name)
        return min(vals) if vals else float("nan")

    def save_csv(self, path: str) -> None:
        if not self.log_rows:
            return
        cols = list(self.log_rows[0].keys())
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(",".join(cols) + "\n")
            for r in self.log_rows:
                fh.write(",".join(f"{r[c]:.5g}" for c in cols) + "\n")


# ---------------------------------------------------------------------------
# Assertions / test framework
# ---------------------------------------------------------------------------
class Check:
    def __init__(self) -> None:
        self.log: List[str] = []
        self.failures: List[str] = []

    def _rec(self, ok: bool, desc: str) -> bool:
        self.log.append(("[PASS] " if ok else "[FAIL] ") + desc)
        if not ok:
            self.failures.append(desc)
        return ok

    def true(self, v, desc):
        return self._rec(bool(v), desc)

    def false(self, v, desc):
        return self._rec(not v, desc)

    def eq(self, a, b, desc):
        return self._rec(a == b, f"{desc} (got {a!r}, want {b!r})")

    def gt(self, a, b, desc):
        return self._rec(a > b, f"{desc} (got {a:.4g} > {b:.4g})")

    def lt(self, a, b, desc):
        return self._rec(a < b, f"{desc} (got {a:.4g} < {b:.4g})")

    def close(self, a, b, tol, desc):
        return self._rec(abs(a - b) <= tol, f"{desc} (got {a:.4g} ~ {b:.4g} +/-{tol:g})")

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass
class Result:
    name: str
    category: str
    status: str
    message: str
    duration_s: float
    log: List[str] = field(default_factory=list)


Scenario = Tuple[str, str, Callable[[Bench, Check], None]]


# ---------------------------------------------------------------------------
# Scenarios (16) — same coverage as the full package suite
# ---------------------------------------------------------------------------
def sc_contactor_close(b: Bench, c: Check) -> None:
    c.false(b.ecu.contactor_closed, "contactor open at power-up")
    b.settle()
    c.true(b.ecu.contactor_closed, "contactor closed once healthy")
    c.eq(b.ecu.fault_flags, 0, "no faults at power-up")


def sc_precharge(b: Bench, c: Check) -> None:
    c.false(b.ecu.contactor_closed, "open at power-up")
    b.run_for(0.1)
    c.eq(b.ecu.state, PRECHARGE, "ECU in precharge state")
    c.false(b.ecu.contactor_closed, "main contactor not closed during precharge")
    b.run_for(0.25)
    c.true(b.ecu.contactor_closed, "closed after precharge dwell")


def sc_charge(b: Bench, c: Check) -> None:
    b.settle()
    soc0, v0 = b.pack.avg_soc, b.pack.pack_v
    b.command(-40.0)
    b.run_for(15.0)
    c.gt(b.pack.avg_soc, soc0, "SOC increased under charge")
    c.gt(b.pack.pack_v, v0, "pack voltage rose under charge")
    c.eq(b.ecu.fault_flags, 0, "no faults during nominal charge")


def sc_discharge(b: Bench, c: Check) -> None:
    b.settle()
    soc0 = b.pack.avg_soc
    b.command(40.0)
    b.run_for(15.0)
    c.lt(b.pack.avg_soc, soc0, "SOC decreased under discharge")
    c.eq(b.ecu.fault_flags, 0, "no faults during nominal discharge")


def sc_soc_tracking(b: Bench, c: Check) -> None:
    b.settle()
    b.command(30.0)
    b.run_for(10.0)
    c.close(b.ecu.soc_pct, b.pack.avg_soc * 100.0, 2.0, "ECU SOC tracks plant SOC")


def sc_drive_cycle(b: Bench, c: Check) -> None:
    b.settle()
    c.true(b.ecu.contactor_closed, "contactor closed before cycle")
    b.clear_log()
    profile = [(0, 0), (2, 120), (4, 40), (5, -80), (7, 30), (9, 100),
               (11, 20), (12, -60), (14, 50), (16, 0)]
    soc0 = b.pack.avg_soc
    t = 0.0
    while t < profile[-1][0]:
        b.command(_interp(profile, t))
        b.run_for(0.1)
        t += 0.1
    c.eq(b.col_max("fault_flags"), 0.0, "no faults during drive cycle")
    c.eq(b.col_min("contactor"), 1.0, "contactor stayed closed through cycle")
    c.lt(b.col_max("max_temp_c"), CONFIG["over_temp_c"], "temperature stayed under limit")
    c.lt(b.pack.avg_soc, soc0, "net SOC decreased over cycle")


def sc_overvoltage(b: Bench, c: Check) -> None:
    b.settle()
    b.pack.cells[0].voltage_offset_v = 0.5
    b.run_for(0.3)
    c.true(b.ecu.fault_flags & Fault.OVERVOLTAGE, "OVERVOLTAGE latched")
    c.false(b.ecu.contactor_closed, "contactor opened on overvoltage")


def sc_undervoltage(b: Bench, c: Check) -> None:
    b.settle()
    b.pack.cells[3].voltage_offset_v = -1.2
    b.run_for(0.3)
    c.true(b.ecu.fault_flags & Fault.UNDERVOLTAGE, "UNDERVOLTAGE latched")
    c.false(b.ecu.contactor_closed, "contactor opened on undervoltage")


def sc_overtemp(b: Bench, c: Check) -> None:
    b.settle()
    b.pack.cells[5].temp_offset_c = 40.0
    b.run_for(0.3)
    c.true(b.ecu.fault_flags & Fault.OVERTEMP, "OVERTEMP latched")
    c.false(b.ecu.contactor_closed, "contactor opened on overtemperature")


def sc_overcurrent(b: Bench, c: Check) -> None:
    b.settle()
    b.command(250.0)
    b.run_for(0.3)
    c.true(b.ecu.fault_flags & Fault.OVERCURRENT_DISCHARGE, "OVERCURRENT latched")
    c.false(b.ecu.contactor_closed, "contactor opened on overcurrent")


def sc_thermal_runaway(b: Bench, c: Check) -> None:
    b.settle()
    b.pack.cells[0].temp_offset_c = 50.0  # 75 C > 70 C critical
    b.run_for(0.3)
    c.true(b.ecu.fault_flags & Fault.THERMAL_RUNAWAY, "THERMAL_RUNAWAY latched")
    c.true(b.ecu.thermal_runaway, "ECU thermal_runaway flag set")
    c.false(b.ecu.contactor_closed, "contactor opened")


def sc_isolation(b: Bench, c: Check) -> None:
    b.settle()
    c.gt(b.ecu.isolation_kohm, CONFIG["isolation_min_kohm"], "isolation healthy before fault")
    b.pack.isolation_kohm = 100.0
    b.run_for(0.3)
    c.true(b.ecu.fault_flags & Fault.ISOLATION, "ISOLATION latched")
    c.false(b.ecu.contactor_closed, "contactor opened on isolation fault")


def sc_balancing(b: Bench, c: Check) -> None:
    b.settle()
    b.pack.cells[2].soc = 0.90
    b.run_for(0.2)
    c.gt(b.pack.delta_v, CONFIG["balancing_start_delta_v"], "delta exceeds balancing threshold")
    c.true(b.ecu.balancing_active, "ECU balancing active")
    hi0 = b.pack.cells[2].soc
    b.run_for(10.0)
    c.lt(b.pack.cells[2].soc, hi0, "high cell bled down by balancing")


def sc_soh(b: Bench, c: Check) -> None:
    b.pack.soh = 0.82
    for cell in b.pack.cells:
        cell.soh = 0.82
    b.settle()
    c.close(b.ecu.soh_pct, 82.0, 1.0, "ECU reports pack SOH")
    c.gt(b.ecu.avail_discharge_kw, 0.0, "available discharge power reported")
    b.pack.cells[0].voltage_offset_v = 0.6
    b.run_for(0.2)
    c.eq(b.ecu.avail_discharge_kw, 0.0, "power collapses to zero under fault")


def sc_contactor_isolates(b: Bench, c: Check) -> None:
    b.settle()
    b.command(30.0)
    b.run_for(1.0)
    c.true(b.ecu.contactor_closed, "closed under nominal load")
    b.pack.cells[0].temp_offset_c = 45.0
    b.run_for(0.5)
    c.false(b.ecu.contactor_closed, "opened on fault")
    b.run_for(0.2)
    c.close(b.pack.current_a, 0.0, 1e-6, "load current isolated after contactor opens")


def sc_fault_recover(b: Bench, c: Check) -> None:
    b.settle()
    b.pack.cells[0].voltage_offset_v = 0.5
    b.run_for(0.3)
    c.true(b.ecu.fault_flags & Fault.OVERVOLTAGE, "OV tripped")
    b.pack.cells[0].voltage_offset_v = 0.0
    b.ecu.clear_faults()
    b.run_for(0.3)
    c.eq(b.ecu.fault_flags, 0, "faults cleared")
    c.true(b.ecu.contactor_closed, "contactor re-closed after recovery")


def _interp(points: List[Tuple[float, float]], t: float) -> float:
    if t <= points[0][0]:
        return points[0][1]
    if t >= points[-1][0]:
        return points[-1][1]
    for (t0, i0), (t1, i1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            return i0 + (t - t0) / (t1 - t0) * (i1 - i0)
    return points[-1][1]


SUITE: List[Scenario] = [
    ("contactor_closes_when_healthy", "contactor", sc_contactor_close),
    ("precharge_delays_main_contactor", "contactor", sc_precharge),
    ("charge_increases_soc", "functional", sc_charge),
    ("discharge_decreases_soc", "functional", sc_discharge),
    ("ecu_soc_tracks_plant", "functional", sc_soc_tracking),
    ("drive_cycle_replay_stays_safe", "drive_cycle", sc_drive_cycle),
    ("overvoltage_opens_contactor", "protection", sc_overvoltage),
    ("undervoltage_opens_contactor", "protection", sc_undervoltage),
    ("overtemperature_opens_contactor", "protection", sc_overtemp),
    ("overcurrent_discharge_opens_contactor", "protection", sc_overcurrent),
    ("thermal_runaway_trips_and_isolates", "protection", sc_thermal_runaway),
    ("low_isolation_opens_contactor", "protection", sc_isolation),
    ("balancing_activates_on_imbalance", "balancing", sc_balancing),
    ("soh_and_power_limits_reported", "reporting", sc_soh),
    ("contactor_opens_and_isolates_load", "contactor", sc_contactor_isolates),
    ("fault_clears_and_contactor_recloses", "protection", sc_fault_recover),
]


# ---------------------------------------------------------------------------
# Console helpers (color if a TTY)
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty()
_QUIET = False


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def log(msg: str) -> None:
    if not _QUIET:
        print(msg)


# ---------------------------------------------------------------------------
# Runner + reports
# ---------------------------------------------------------------------------
def run_suite(scenarios: List[Scenario]) -> List[Result]:
    results: List[Result] = []
    for name, category, fn in scenarios:
        bench = Bench()
        check = Check()
        start = time.perf_counter()
        try:
            fn(bench, check)
            status = "pass" if check.ok else "fail"
            message = "" if check.ok else "; ".join(check.failures)
        except Exception as exc:  # noqa: BLE001
            status, message = "error", f"{type(exc).__name__}: {exc}"
        dur = time.perf_counter() - start
        results.append(Result(name, category, status, message, dur, list(check.log)))
        tag = {"pass": _c("32", "PASS"), "fail": _c("31", "FAIL"),
               "error": _c("33", "ERROR")}[status]
        line = f"  {tag}  {name:<38} ({dur*1000:5.1f} ms)"
        if status != "pass":
            line += "  -> " + message
        log(line)
    return results


def write_html(results: List[Result], path: str, trace_datauri: str = "") -> str:
    n = len(results)
    p = sum(1 for r in results if r.status == "pass")
    f = sum(1 for r in results if r.status == "fail")
    e = sum(1 for r in results if r.status == "error")
    dur = sum(r.duration_s for r in results)
    rows = []
    for r in results:
        detail = html.escape(r.message)
        if r.log:
            detail += "<pre>" + html.escape("\n".join(r.log)) + "</pre>"
        rows.append(
            f'<tr><td>{html.escape(r.name)}</td><td>{html.escape(r.category)}</td>'
            f'<td><span class="st {r.status}">{r.status}</span></td>'
            f'<td>{r.duration_s*1000:.1f} ms</td><td>{detail}</td></tr>')
    trace = (f'<div class="trace"><h2>Signal trace</h2>'
             f'<img src="{trace_datauri}" alt="trace"></div>') if trace_datauri else ""
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>BMS HIL Report</title><style>
body{{font-family:system-ui,Arial,sans-serif;margin:2rem;background:#fafafa;color:#1a1a1a}}
h1{{margin-bottom:.2rem}} .sub{{color:#666}}
.summary{{display:flex;gap:1rem;margin:1.2rem 0}}
.card{{border-radius:8px;padding:.8rem 1.2rem;color:#fff;min-width:70px}} .card b{{font-size:1.5rem;display:block}}
.total{{background:#37474f}} .pass{{background:#2e7d32}} .fail{{background:#c62828}} .err{{background:#ef6c00}}
table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
th,td{{text-align:left;padding:.5rem .8rem;border-bottom:1px solid #eee;vertical-align:top}} th{{background:#eceff1}}
.st{{font-weight:700;text-transform:uppercase;font-size:.7rem;padding:.1rem .5rem;border-radius:4px;color:#fff}}
.st.pass{{background:#2e7d32}} .st.fail{{background:#c62828}} .st.error{{background:#ef6c00}}
pre{{white-space:pre-wrap;color:#444;font-size:.8rem;margin:.3rem 0 0}}
.trace img{{max-width:100%;border:1px solid #ddd;border-radius:8px;background:#fff}}
</style></head><body>
<h1>BMS HIL Test Report</h1>
<p class="sub">Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S UTC} &middot; {dur*1000:.0f} ms</p>
<div class="summary">
<div class="card total"><b>{n}</b>tests</div><div class="card pass"><b>{p}</b>passed</div>
<div class="card fail"><b>{f}</b>failed</div><div class="card err"><b>{e}</b>errors</div></div>
<table><thead><tr><th>Test</th><th>Category</th><th>Status</th><th>Time</th><th>Detail</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>{trace}</body></html>"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path


def maybe_plot_datauri(bench: Bench) -> str:
    """Return a base64 PNG data URI of the trace if matplotlib is available."""
    try:
        import base64
        import io

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    t = bench.col("time_s")
    fig, ax = plt.subplots(4, 1, figsize=(9, 9), sharex=True)
    ax[0].plot(t, bench.col("pack_v"), color="#1565c0"); ax[0].set_ylabel("Pack V")
    ax[1].plot(t, bench.col("min_cell_v"), color="#2e7d32", label="min")
    ax[1].plot(t, bench.col("max_cell_v"), color="#c62828", label="max")
    ax[1].set_ylabel("Cell V"); ax[1].legend(fontsize=8)
    ax[2].plot(t, bench.col("current_a"), color="#ef6c00"); ax[2].axhline(0, color="#999", lw=.6)
    ax[2].set_ylabel("Current A")
    ax[3].plot(t, bench.col("max_temp_c"), color="#6a1b9a"); ax[3].set_ylabel("Max °C")
    ax[3].set_xlabel("Time (s)")
    for a in ax:
        a.grid(True, alpha=.3)
    fig.suptitle("BMS HIL signal trace"); fig.tight_layout(rect=(0, 0, 1, .98))
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=110); plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_selftest() -> int:
    log(_c("1", "BMS HIL self-test"))
    b = Bench()
    b.settle(0.3)
    checks = [
        ("contactor closed when healthy", b.ecu.contactor_closed),
        ("no spurious faults", b.ecu.fault_flags == 0),
        ("pack voltage plausible", 30.0 < b.ecu.pack_v < 55.0),
        ("SOC reported", 40.0 < b.ecu.soc_pct < 70.0),
    ]
    ok = True
    for desc, passed in checks:
        log(f"  [{_c('32','PASS') if passed else _c('31','FAIL')}] {desc}")
        ok = ok and passed
    log(_c("32", "  self-test PASSED") if ok else _c("31", "  self-test FAILED"))
    return 0 if ok else 1


def cmd_demo() -> int:
    log(_c("1", "BMS HIL demo — charge -> discharge -> overtemperature fault"))
    b = Bench()
    b.settle(0.3)
    log(f"  power-up: contactor={b.ecu.contactor_closed} soc={b.pack.avg_soc*100:.1f}%")
    log("  charging at 40 A for 8 s ...")
    b.command(-40.0); b.run_for(8.0)
    log(f"    soc={b.pack.avg_soc*100:.2f}%  pack={b.pack.pack_v:.1f} V  max_cell={b.pack.max_v:.3f} V")
    log("  discharging at 60 A for 8 s ...")
    b.command(60.0); b.run_for(8.0)
    log(f"    soc={b.pack.avg_soc*100:.2f}%  pack={b.pack.pack_v:.1f} V  max_temp={b.pack.max_temp:.1f} C")
    log("  injecting overtemperature on cell 4 ...")
    b.pack.cells[4].temp_offset_c = 45.0
    b.run_for(0.5)
    log(f"    fault_flags=0x{b.ecu.fault_flags:04X} ({', '.join(Fault.names(b.ecu.fault_flags)) or 'none'}) "
        f"contactor={b.ecu.contactor_closed}")
    out = CONFIG["report_dir"]
    csv = os.path.join(out, "demo_trace.csv")
    b.save_csv(csv)
    log(f"  signal trace: {csv} ({len(b.log_rows)} samples)")
    uri = maybe_plot_datauri(b)
    if uri:
        try:
            import base64
            png = os.path.join(out, "demo_trace.png")
            with open(png, "wb") as fh:
                fh.write(base64.b64decode(uri.split(",", 1)[1]))
            log(f"  trace plot:   {png}")
        except Exception:
            pass
    else:
        log("  (install matplotlib for a PNG trace plot: pip install matplotlib)")
    return 0


def cmd_test(output_dir: str) -> int:
    log(_c("1", f"BMS HIL regression suite — {len(SUITE)} scenarios"))
    results = run_suite(SUITE)
    n = len(results)
    p = sum(1 for r in results if r.status == "pass")
    f = sum(1 for r in results if r.status == "fail")
    e = sum(1 for r in results if r.status == "error")
    # a trace to embed in the report
    trace_bench = Bench(); trace_bench.settle(0.3)
    prof = [(0, 0), (2, 120), (4, 40), (5, -80), (7, 30), (9, 100), (11, 20), (14, 50), (16, 0)]
    t = 0.0
    while t < prof[-1][0]:
        trace_bench.command(_interp(prof, t)); trace_bench.run_for(0.1); t += 0.1
    trace_bench.pack.cells[0].temp_offset_c = 50.0; trace_bench.run_for(0.5)
    html_path = write_html(results, os.path.join(output_dir, "report.html"),
                           maybe_plot_datauri(trace_bench))
    bar = _c("32", "PASS") if (f + e) == 0 else _c("31", "FAIL")
    log("  " + "-" * 56)
    log(f"  RESULTS [{bar}]: {n} total | {_c('32', str(p)+' pass')} | "
        f"{_c('31', str(f)+' fail')} | {_c('33', str(e)+' error')}")
    log(f"  HTML report: {html_path}")
    return 0 if (f + e) == 0 else 1


def cmd_menu() -> int:
    while True:
        print()
        print(_c("1", "=== BMS Management ECU — HIL Test Tool ==="))
        print("  1) Self-test        (quick health check)")
        print("  2) Run demo         (charge / discharge / fault, writes trace)")
        print("  3) Run test suite   (16 scenarios + HTML report)")
        print("  4) Show config      (pack / ECU parameters)")
        print("  5) Quit")
        try:
            choice = input(_c("1", "Select [1-5]: ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice == "1":
            cmd_selftest()
        elif choice == "2":
            cmd_demo()
        elif choice == "3":
            cmd_test(CONFIG["report_dir"])
        elif choice == "4":
            cmd_info()
        elif choice in ("5", "q", "quit", "exit"):
            return 0
        else:
            print("  (enter 1-5)")


def cmd_info() -> int:
    print(_c("1", "Resolved configuration:"))
    for k, v in CONFIG.items():
        print(f"  {k:<28} = {v}")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_bms_hil.py",
        description="Battery Management ECU HIL test tool (single-file edition).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run with no command for an interactive menu.")
    parser.add_argument("command", nargs="?", default="menu",
                        choices=["menu", "selftest", "demo", "test", "info"],
                        help="what to run (default: menu)")
    parser.add_argument("-o", "--output-dir", default=CONFIG["report_dir"],
                        help="report output directory")
    parser.add_argument("-q", "--quiet", action="store_true", help="less console output")
    args = parser.parse_args(argv)

    global _QUIET
    _QUIET = args.quiet
    CONFIG["report_dir"] = args.output_dir

    if args.command == "selftest":
        return cmd_selftest()
    if args.command == "demo":
        return cmd_demo()
    if args.command == "test":
        return cmd_test(args.output_dir)
    if args.command == "info":
        return cmd_info()
    return cmd_menu()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
