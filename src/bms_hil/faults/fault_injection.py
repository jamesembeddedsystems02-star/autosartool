"""Fault injection: schedule and apply defects to the plant during a test.

Each :class:`Fault` becomes active over a time window ``[start_s, end_s)`` and
mutates the battery plant (a cell's sensor bias, an open connection, a forced
imbalance, etc.). The :class:`FaultInjector` is registered as a scheduler
callback and applies/reverts faults as simulated time crosses their windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..core.logging_setup import get_logger
from ..plant.battery_pack import BatteryPack

log = get_logger("bms_hil.faults")


@dataclass
class Fault:
    """Base fault with an activation window. Subclasses implement apply/revert."""

    name: str
    cell_index: int = 0
    start_s: float = 0.0
    end_s: float = float("inf")
    _active: bool = field(default=False, init=False)

    def apply(self, pack: BatteryPack) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def revert(self, pack: BatteryPack) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def update(self, pack: BatteryPack, t_s: float) -> None:
        want = self.start_s <= t_s < self.end_s
        if want and not self._active:
            self.apply(pack)
            self._active = True
            log.info("[t=%.2fs] fault ON: %s (cell %d)", t_s, self.name, self.cell_index)
        elif not want and self._active:
            self.revert(pack)
            self._active = False
            log.info("[t=%.2fs] fault OFF: %s (cell %d)", t_s, self.name, self.cell_index)


@dataclass
class CellVoltageOffsetFault(Fault):
    offset_v: float = 0.5

    def apply(self, pack: BatteryPack) -> None:
        pack.cells[self.cell_index].voltage_offset_v = self.offset_v

    def revert(self, pack: BatteryPack) -> None:
        pack.cells[self.cell_index].voltage_offset_v = 0.0


@dataclass
class TempSensorOffsetFault(Fault):
    offset_c: float = 40.0

    def apply(self, pack: BatteryPack) -> None:
        pack.cells[self.cell_index].temp_offset_c = self.offset_c

    def revert(self, pack: BatteryPack) -> None:
        pack.cells[self.cell_index].temp_offset_c = 0.0


@dataclass
class OpenCircuitFault(Fault):
    def apply(self, pack: BatteryPack) -> None:
        pack.cells[self.cell_index].open_circuit_fault = True

    def revert(self, pack: BatteryPack) -> None:
        pack.cells[self.cell_index].open_circuit_fault = False


@dataclass
class CellImbalanceFault(Fault):
    """Force one cell's SOC away from the rest to create a delta-V imbalance."""

    target_soc: float = 0.9
    _restored: bool = field(default=False, init=False)

    def apply(self, pack: BatteryPack) -> None:
        pack.set_cell_soc(self.cell_index, self.target_soc)

    def revert(self, pack: BatteryPack) -> None:
        # Imbalance is a one-shot state change; nothing to actively revert.
        pass


class FaultInjector:
    """Owns a list of faults and applies them each scheduler step."""

    def __init__(self, pack: BatteryPack, faults: Optional[List[Fault]] = None) -> None:
        self.pack = pack
        self.faults: List[Fault] = list(faults or [])

    def add(self, fault: Fault) -> None:
        self.faults.append(fault)

    def step(self, t_s: float, dt_s: float) -> None:  # scheduler callback signature
        for fault in self.faults:
            fault.update(self.pack, t_s)

    def clear(self) -> None:
        for fault in self.faults:
            if fault._active:
                fault.revert(self.pack)
                fault._active = False
        self.faults.clear()
