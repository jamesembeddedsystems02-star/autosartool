"""Single Li-ion cell model: 1st-order equivalent circuit + lumped thermal.

Electrical model (Thevenin / 1-RC):

    V_terminal = OCV(SOC) - I*R0 - V_rc          (I > 0 == discharge)
    dV_rc/dt   = I/C_rc - V_rc/(R_rc*C_rc)
    dSOC/dt    = -I / (3600 * Q_nom)             (coulomb counting)

Thermal model (lumped mass):

    C_th * dT/dt = P_loss - (T - T_amb) / R_th
    P_loss       = I^2*R0 + V_rc^2/R_rc

The open-circuit-voltage curve is a small SOC->OCV lookup table with linear
interpolation, representative of an NMC cell. Sign convention: positive current
is discharge (current leaving the cell).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

# Representative NMC OCV curve as (SOC, OCV) breakpoints, monotonic in SOC.
_OCV_TABLE: List[Tuple[float, float]] = [
    (0.00, 3.00),
    (0.05, 3.40),
    (0.10, 3.55),
    (0.20, 3.63),
    (0.30, 3.68),
    (0.40, 3.73),
    (0.50, 3.78),
    (0.60, 3.85),
    (0.70, 3.93),
    (0.80, 4.02),
    (0.90, 4.11),
    (1.00, 4.20),
]


def ocv_from_soc(soc: float) -> float:
    """Linear-interpolated open-circuit voltage for a state of charge 0..1."""
    s = min(1.0, max(0.0, soc))
    table = _OCV_TABLE
    if s <= table[0][0]:
        return table[0][1]
    if s >= table[-1][0]:
        return table[-1][1]
    for (s0, v0), (s1, v1) in zip(table, table[1:]):
        if s0 <= s <= s1:
            frac = (s - s0) / (s1 - s0)
            return v0 + frac * (v1 - v0)
    return table[-1][1]


@dataclass
class CellParams:
    capacity_ah: float = 50.0
    r0_ohm: float = 0.012
    rc_r_ohm: float = 0.008
    rc_c_f: float = 4000.0
    thermal_mass_j_per_k: float = 850.0
    thermal_resistance_k_per_w: float = 5.0
    ambient_temp_c: float = 25.0


@dataclass
class CellModel:
    """Stateful single-cell simulation. Call :meth:`step` each control cycle."""

    params: CellParams = field(default_factory=CellParams)
    soc: float = 0.5
    temp_c: float = 25.0
    v_rc: float = 0.0            # RC branch overpotential (V)
    _terminal_v: float = 0.0
    # Diagnostics / fault-injection knobs (applied on top of physics):
    voltage_offset_v: float = 0.0   # sensor/cell voltage bias
    temp_offset_c: float = 0.0      # temperature sensor bias
    soc_leak_a: float = 0.0         # parasitic self-discharge current
    open_circuit_fault: bool = False  # broken connection -> no current flows

    def __post_init__(self) -> None:
        self._terminal_v = ocv_from_soc(self.soc)

    @property
    def terminal_voltage(self) -> float:
        """True terminal voltage from last :meth:`step` (no sensor bias)."""
        return self._terminal_v

    @property
    def measured_voltage(self) -> float:
        """Voltage as a sensor would report it (includes injected bias)."""
        return self._terminal_v + self.voltage_offset_v

    @property
    def measured_temp_c(self) -> float:
        return self.temp_c + self.temp_offset_c

    def step(self, current_a: float, dt_s: float) -> float:
        """Advance the cell by *dt_s* seconds under load *current_a*.

        Positive current discharges the cell. Returns the true terminal
        voltage. An open-circuit fault forces the branch current to zero.
        """
        p = self.params
        i = 0.0 if self.open_circuit_fault else current_a

        # Coulomb counting (+ parasitic leak always discharges).
        effective_i = i + self.soc_leak_a
        self.soc -= effective_i * dt_s / (3600.0 * p.capacity_ah)
        self.soc = min(1.0, max(0.0, self.soc))

        # RC branch update (explicit Euler; step is small vs. time constant).
        tau = max(1e-6, p.rc_r_ohm * p.rc_c_f)
        dv_rc = (i / p.rc_c_f) - (self.v_rc / tau)
        self.v_rc += dv_rc * dt_s

        # Terminal voltage.
        ocv = ocv_from_soc(self.soc)
        self._terminal_v = ocv - i * p.r0_ohm - self.v_rc

        # Thermal update: ohmic + polarization losses vs. convective cooling.
        p_loss = (i * i * p.r0_ohm) + (self.v_rc * self.v_rc / max(1e-9, p.rc_r_ohm))
        ambient = p.ambient_temp_c
        cooling = (self.temp_c - ambient) / max(1e-9, p.thermal_resistance_k_per_w)
        dtemp = (p_loss - cooling) / max(1e-9, p.thermal_mass_j_per_k)
        self.temp_c += dtemp * dt_s

        return self._terminal_v
