"""Single Li-ion cell model: 2nd-order equivalent circuit + lumped thermal.

Electrical model (Thevenin / 2-RC) with a state of health (SOH) capacity fade
and temperature-dependent ohmic resistance:

    R0(T)      = R0_ref * (1 + alpha*(T_ref - T)) * (1 + r_growth*(1 - SOH))
    V_terminal = OCV(SOC) - I*R0(T) - V_rc1 - V_rc2      (I > 0 == discharge)
    dV_rc/dt   = I/C_rc - V_rc/(R_rc*C_rc)               (per RC branch)
    dSOC/dt    = -I / (3600 * Q_nom * SOH)               (coulomb counting)

Thermal model (lumped mass):

    C_th * dT/dt = P_loss - (T - T_amb) / R_th
    P_loss       = I^2*R0(T) + V_rc1^2/R_rc1 + V_rc2^2/R_rc2

The open-circuit-voltage curve is a small SOC->OCV lookup table with linear
interpolation, representative of an NMC cell. Sign convention: positive current
is discharge (current leaving the cell).

The second RC branch and temperature/SOH corrections default to values that keep
the model behaving like the previous single-RC cell, so existing calibrations
and tests remain valid while higher-fidelity effects can be dialled in.
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

_REF_TEMP_C = 25.0


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
    r0_ohm: float = 0.0025            # ohmic resistance at reference temperature
    rc_r_ohm: float = 0.0015          # RC1 (fast) resistance
    rc_c_f: float = 5000.0            # RC1 capacitance
    rc2_r_ohm: float = 0.0008         # RC2 (slow) resistance
    rc2_c_f: float = 60000.0          # RC2 capacitance
    r0_temp_coeff_per_c: float = 0.008  # +0.8%/degC of R0 as temp drops below ref
    r0_soh_growth: float = 0.5        # R0 grows by this fraction at SOH=0
    thermal_mass_j_per_k: float = 850.0
    thermal_resistance_k_per_w: float = 5.0
    ambient_temp_c: float = 25.0


@dataclass
class CellModel:
    """Stateful single-cell simulation. Call :meth:`step` each control cycle."""

    params: CellParams = field(default_factory=CellParams)
    soc: float = 0.5
    temp_c: float = 25.0
    soh: float = 1.0            # 1.0 = healthy, < 1.0 = capacity/resistance fade
    v_rc1: float = 0.0          # fast RC branch overpotential (V)
    v_rc2: float = 0.0          # slow RC branch overpotential (V)
    _terminal_v: float = 0.0
    # Diagnostics / fault-injection knobs (applied on top of physics):
    voltage_offset_v: float = 0.0   # sensor/cell voltage bias
    temp_offset_c: float = 0.0      # temperature sensor bias
    soc_leak_a: float = 0.0         # parasitic self-discharge current
    open_circuit_fault: bool = False  # broken connection -> no current flows

    def __post_init__(self) -> None:
        self._terminal_v = ocv_from_soc(self.soc)

    # ---- derived parameters ----------------------------------------------
    def r0_at(self, temp_c: float) -> float:
        """Temperature- and SOH-corrected ohmic resistance."""
        p = self.params
        temp_factor = 1.0 + p.r0_temp_coeff_per_c * (_REF_TEMP_C - temp_c)
        soh_factor = 1.0 + p.r0_soh_growth * (1.0 - self.soh)
        return max(1e-6, p.r0_ohm * temp_factor * soh_factor)

    @property
    def effective_capacity_ah(self) -> float:
        return max(1e-6, self.params.capacity_ah * self.soh)

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
        r0 = self.r0_at(self.temp_c)

        # Coulomb counting (+ parasitic leak always discharges), SOH-derated.
        effective_i = i + self.soc_leak_a
        self.soc -= effective_i * dt_s / (3600.0 * self.effective_capacity_ah)
        self.soc = min(1.0, max(0.0, self.soc))

        # RC branch updates (explicit Euler; step is small vs. time constants).
        tau1 = max(1e-6, p.rc_r_ohm * p.rc_c_f)
        self.v_rc1 += ((i / p.rc_c_f) - (self.v_rc1 / tau1)) * dt_s
        tau2 = max(1e-6, p.rc2_r_ohm * p.rc2_c_f)
        self.v_rc2 += ((i / p.rc2_c_f) - (self.v_rc2 / tau2)) * dt_s

        # Terminal voltage.
        ocv = ocv_from_soc(self.soc)
        self._terminal_v = ocv - i * r0 - self.v_rc1 - self.v_rc2

        # Thermal update: ohmic + polarization losses vs. convective cooling.
        p_loss = (
            i * i * r0
            + self.v_rc1 * self.v_rc1 / max(1e-9, p.rc_r_ohm)
            + self.v_rc2 * self.v_rc2 / max(1e-9, p.rc2_r_ohm)
        )
        cooling = (self.temp_c - p.ambient_temp_c) / max(1e-9, p.thermal_resistance_k_per_w)
        dtemp = (p_loss - cooling) / max(1e-9, p.thermal_mass_j_per_k)
        self.temp_c += dtemp * dt_s

        return self._terminal_v
