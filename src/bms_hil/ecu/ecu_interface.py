"""Tester-side interface to the BMS ECU (works against stub or real hardware).

The HIL tests never touch the ECU internals directly; they go through this
interface, which:

* sends the plant's simulated cell measurements to the ECU,
* sends tester commands (requested current, clear-faults),
* listens for the ECU's periodic status messages and exposes the latest as a
  typed :class:`EcuStatus`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..io.can_interface import CanBus
from ..io.signal_db import (
    SignalDatabase,
    default_bms_database,
    MSG_PACK_STATUS,
    MSG_LIMITS_STATUS,
)
from ..plant.battery_pack import PackState


@dataclass
class EcuStatus:
    pack_voltage_v: float = 0.0
    pack_current_a: float = 0.0
    soc_pct: float = 0.0
    mode: int = 0
    contactor_closed: bool = False
    fault_flags: int = 0
    max_cell_temp_c: float = 0.0
    max_charge_current_a: float = 0.0
    max_discharge_current_a: float = 0.0
    valid: bool = False


class EcuInterface:
    def __init__(self, bus: CanBus, db: Optional[SignalDatabase] = None) -> None:
        self.bus = bus
        self.db = db or default_bms_database()
        self.status = EcuStatus()

    # ---- tester -> ECU ----------------------------------------------------
    def publish_cell_measurements(self, state: PackState) -> None:
        frame = self.db.encode("SIM_CellVoltages", {
            "MinCellVoltage": state.min_cell_v,
            "MaxCellVoltage": state.max_cell_v,
            "CellDelta": state.cell_delta_v,
            "MaxCellTemp": state.max_temp_c,
        })
        self.bus.send(frame)

    def send_command(self, requested_current_a: float, command: int = 0,
                     clear_faults: bool = False) -> None:
        frame = self.db.encode("TESTER_Command", {
            "RequestedCurrent": requested_current_a,
            "Command": float(command),
            "ClearFaults": 1.0 if clear_faults else 0.0,
        })
        self.bus.send(frame)

    # ---- ECU -> tester ----------------------------------------------------
    def poll(self) -> EcuStatus:
        """Drain pending frames and update :attr:`status`."""
        while True:
            frame = self.bus.recv(timeout=0.0)
            if frame is None:
                break
            if frame.arbitration_id == MSG_PACK_STATUS:
                vals = self.db.decode(frame)
                self.status.pack_voltage_v = vals["PackVoltage"]
                self.status.pack_current_a = vals["PackCurrent"]
                self.status.soc_pct = vals["PackSOC"]
                self.status.mode = int(vals["PackMode"])
                self.status.valid = True
            elif frame.arbitration_id == MSG_LIMITS_STATUS:
                vals = self.db.decode(frame)
                self.status.contactor_closed = bool(int(vals["ContactorClosed"]))
                self.status.fault_flags = int(vals["FaultFlags"])
                self.status.max_cell_temp_c = vals["MaxCellTemp"]
                self.status.max_charge_current_a = vals["MaxChargeCurrent"]
                self.status.max_discharge_current_a = vals["MaxDischargeCurrent"]
        return self.status
