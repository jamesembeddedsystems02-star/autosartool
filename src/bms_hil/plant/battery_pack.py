"""Battery pack model: a series/parallel arrangement of :class:`CellModel`.

For HIL purposes the pack is modelled as ``series_cells`` cells in series,
each cell itself representing ``parallel_strings`` paralleled cells (so the
per-cell capacity is scaled up and the same string current is shared). Pack
current is the load applied to every series element; pack voltage is the sum of
cell terminal voltages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..core.config import Config
from .cell_model import CellModel, CellParams


@dataclass
class PackState:
    """Snapshot of pack-level measurements for a given step."""

    time_s: float
    current_a: float
    pack_voltage_v: float
    cell_voltages_v: List[float]
    cell_temps_c: List[float]
    cell_socs: List[float]

    @property
    def min_cell_v(self) -> float:
        return min(self.cell_voltages_v)

    @property
    def max_cell_v(self) -> float:
        return max(self.cell_voltages_v)

    @property
    def cell_delta_v(self) -> float:
        return self.max_cell_v - self.min_cell_v

    @property
    def max_temp_c(self) -> float:
        return max(self.cell_temps_c)

    @property
    def min_temp_c(self) -> float:
        return min(self.cell_temps_c)

    @property
    def avg_soc(self) -> float:
        return sum(self.cell_socs) / len(self.cell_socs)


class BatteryPack:
    """Aggregate plant model exposing a single :meth:`step` per control cycle."""

    def __init__(self, config: Config) -> None:
        pack_cfg = config.section("pack")
        cell_cfg = config.section("cell")

        self.series = int(pack_cfg.get("series_cells", 12))
        self.parallel = int(pack_cfg.get("parallel_strings", 1))
        per_cell_capacity = float(pack_cfg.get("nominal_capacity_ah", 50.0)) * self.parallel

        params = CellParams(
            capacity_ah=per_cell_capacity,
            r0_ohm=float(cell_cfg.get("internal_resistance_ohm", 0.012)) / self.parallel,
            rc_r_ohm=float(cell_cfg.get("rc_resistance_ohm", 0.008)) / self.parallel,
            rc_c_f=float(cell_cfg.get("rc_capacitance_f", 4000.0)) * self.parallel,
            thermal_mass_j_per_k=float(cell_cfg.get("thermal_mass_j_per_k", 850.0)),
            thermal_resistance_k_per_w=float(cell_cfg.get("thermal_resistance_k_per_w", 5.0)),
            ambient_temp_c=float(cell_cfg.get("ambient_temp_c", 25.0)),
        )

        init_soc = float(pack_cfg.get("initial_soc", 0.55))
        init_temp = float(pack_cfg.get("initial_temp_c", 25.0))
        self.cells: List[CellModel] = [
            CellModel(params=CellParams(**vars(params)), soc=init_soc, temp_c=init_temp)
            for _ in range(self.series)
        ]

        self._last_state = self._snapshot(0.0, 0.0)

    # ---- simulation -------------------------------------------------------
    def step(self, current_a: float, dt_s: float, time_s: float = 0.0) -> PackState:
        """Apply *current_a* (positive = discharge) to the series string."""
        for cell in self.cells:
            cell.step(current_a, dt_s)
        self._last_state = self._snapshot(time_s, current_a)
        return self._last_state

    def _snapshot(self, time_s: float, current_a: float) -> PackState:
        v = [c.measured_voltage for c in self.cells]
        t = [c.measured_temp_c for c in self.cells]
        s = [c.soc for c in self.cells]
        return PackState(
            time_s=time_s,
            current_a=current_a,
            pack_voltage_v=sum(v),
            cell_voltages_v=v,
            cell_temps_c=t,
            cell_socs=s,
        )

    @property
    def state(self) -> PackState:
        return self._last_state

    # ---- balancing support ------------------------------------------------
    def apply_balancing(self, bleed_currents_a: List[float], dt_s: float) -> None:
        """Discharge individual cells by passive balancing bleed currents."""
        for cell, bleed in zip(self.cells, bleed_currents_a):
            if bleed <= 0.0:
                continue
            cell.soc -= bleed * dt_s / (3600.0 * cell.params.capacity_ah)
            cell.soc = min(1.0, max(0.0, cell.soc))

    def set_cell_soc(self, index: int, soc: float) -> None:
        self.cells[index].soc = min(1.0, max(0.0, soc))
