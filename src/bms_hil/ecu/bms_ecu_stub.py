"""A simulated BMS ECU that acts as the device-under-test stand-in.

On a real HIL bench the device-under-test is a physical BMS ECU wired to the
bus; the tool's job is to stimulate it and check its responses. To let the
whole toolchain run and be tested with no hardware, this module implements a
*reference* BMS ECU with the control logic a real one would have:

* reads simulated cell voltages/temperatures/current from the plant messages,
* estimates pack SOC,
* enforces protection limits (OV/UV/OT/UT/OC) and opens the main contactor on a
  latching fault,
* commands passive cell balancing above a delta-V threshold,
* publishes ``BMS_PackStatus`` and ``BMS_LimitsStatus`` periodically,
* answers a small set of UDS diagnostic requests.

Swap this out for a real ECU by pointing the CAN backend at hardware; the
tester-side code in :mod:`ecu_interface` does not change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..core.logging_setup import get_logger
from ..io.can_interface import CanBus, CanFrame
from ..io.signal_db import (
    SignalDatabase,
    default_bms_database,
    MSG_CELL_VOLTAGES,
    MSG_TESTER_COMMAND,
)
from ..io import uds_client as uds

log = get_logger("bms_hil.ecu")


class FaultBits:
    """Bit positions in the ``FaultFlags`` bitfield."""

    OVERVOLTAGE = 1 << 0
    UNDERVOLTAGE = 1 << 1
    OVERTEMP = 1 << 2
    UNDERTEMP = 1 << 3
    OVERCURRENT_CHARGE = 1 << 4
    OVERCURRENT_DISCHARGE = 1 << 5
    CELL_IMBALANCE = 1 << 6
    SENSOR_FAULT = 1 << 7

    @staticmethod
    def names(flags: int) -> List[str]:
        out = []
        for name, bit in [
            ("OVERVOLTAGE", FaultBits.OVERVOLTAGE),
            ("UNDERVOLTAGE", FaultBits.UNDERVOLTAGE),
            ("OVERTEMP", FaultBits.OVERTEMP),
            ("UNDERTEMP", FaultBits.UNDERTEMP),
            ("OVERCURRENT_CHARGE", FaultBits.OVERCURRENT_CHARGE),
            ("OVERCURRENT_DISCHARGE", FaultBits.OVERCURRENT_DISCHARGE),
            ("CELL_IMBALANCE", FaultBits.CELL_IMBALANCE),
            ("SENSOR_FAULT", FaultBits.SENSOR_FAULT),
        ]:
            if flags & bit:
                out.append(name)
        return out


@dataclass
class EcuThresholds:
    cell_overvoltage_v: float = 4.20
    cell_undervoltage_v: float = 2.80
    over_temp_c: float = 55.0
    under_temp_c: float = -10.0
    over_current_charge_a: float = 150.0
    over_current_discharge_a: float = 200.0
    balancing_start_delta_v: float = 0.030
    balancing_current_a: float = 0.10

    @classmethod
    def from_config_section(cls, section: dict) -> "EcuThresholds":
        return cls(**{k: section[k] for k in vars(cls()) if k in section})


# UDS DID map used by the diagnostics tests.
DID_SOC = 0xF010
DID_FAULT_FLAGS = 0xF011
DID_MAX_CELL_TEMP = 0xF012
ROUTINE_CONTACTOR_SELFTEST = 0x0201


@dataclass
class BmsEcuStub:
    """Reference BMS ECU. Call :meth:`step` each control cycle."""

    bus: CanBus
    thresholds: EcuThresholds = field(default_factory=EcuThresholds)
    db: SignalDatabase = field(default_factory=default_bms_database)
    publish_period_s: float = 0.05

    # Runtime state
    contactor_closed: bool = False
    fault_flags: int = 0
    soc_pct: float = 55.0
    pack_voltage_v: float = 0.0
    pack_current_a: float = 0.0
    max_cell_temp_c: float = 25.0
    min_cell_v: float = 3.7
    max_cell_v: float = 3.7
    cell_delta_v: float = 0.0
    balancing_active: bool = False
    _counter: int = 0
    _since_publish_s: float = 0.0
    _requested_current_a: float = 0.0
    _command: int = 0  # 0 idle, 1 charge, 2 discharge

    def __post_init__(self) -> None:
        # Contactor closes once the ECU has seen valid data and no faults.
        self._seen_data = False

    # ---- main control cycle ----------------------------------------------
    def step(self, dt_s: float) -> None:
        self._drain_rx()
        self._run_protection()
        self._run_balancing()
        self._since_publish_s += dt_s
        if self._since_publish_s >= self.publish_period_s:
            self._since_publish_s = 0.0
            self._publish()

    def _drain_rx(self) -> None:
        while True:
            frame = self.bus.recv(timeout=0.0)
            if frame is None:
                return
            if frame.arbitration_id == MSG_CELL_VOLTAGES:
                self._on_cell_voltages(frame)
            elif frame.arbitration_id == MSG_TESTER_COMMAND:
                self._on_tester_command(frame)
            elif frame.arbitration_id == 0x7E0:  # UDS request
                self._on_uds(frame)

    def _on_cell_voltages(self, frame: CanFrame) -> None:
        vals = self.db.decode(frame)
        self.min_cell_v = vals["MinCellVoltage"]
        self.max_cell_v = vals["MaxCellVoltage"]
        self.cell_delta_v = vals["CellDelta"]
        self.max_cell_temp_c = vals["MaxCellTemp"]
        self._seen_data = True

    def _on_tester_command(self, frame: CanFrame) -> None:
        vals = self.db.decode(frame)
        self._requested_current_a = vals["RequestedCurrent"]
        self._command = int(vals["Command"])
        if int(vals.get("ClearFaults", 0)) == 1:
            self.clear_faults()

    # ---- protection & balancing ------------------------------------------
    def _run_protection(self) -> None:
        if not self._seen_data:
            return
        t = self.thresholds
        flags = self.fault_flags  # faults latch until cleared

        if self.max_cell_v >= t.cell_overvoltage_v:
            flags |= FaultBits.OVERVOLTAGE
        if self.min_cell_v <= t.cell_undervoltage_v:
            flags |= FaultBits.UNDERVOLTAGE
        if self.max_cell_temp_c >= t.over_temp_c:
            flags |= FaultBits.OVERTEMP
        if self.max_cell_temp_c <= t.under_temp_c:
            flags |= FaultBits.UNDERTEMP

        # Current sign: + = discharge, - = charge.
        if self.pack_current_a < -t.over_current_charge_a:
            flags |= FaultBits.OVERCURRENT_CHARGE
        if self.pack_current_a > t.over_current_discharge_a:
            flags |= FaultBits.OVERCURRENT_DISCHARGE

        # Plausibility / sensor fault: impossible cell voltage.
        if self.max_cell_v > 5.5 or self.min_cell_v < 0.5:
            flags |= FaultBits.SENSOR_FAULT

        if flags != self.fault_flags:
            newly = FaultBits.names(flags & ~self.fault_flags)
            log.warning("ECU fault(s) asserted: %s", ", ".join(newly))
        self.fault_flags = flags

        # Contactor logic: open (safe) on any latched fault; otherwise close
        # once valid data has been seen.
        if self.fault_flags:
            if self.contactor_closed:
                log.warning("ECU opening main contactor due to fault 0x%04X",
                            self.fault_flags)
            self.contactor_closed = False
        else:
            self.contactor_closed = True

    def _run_balancing(self) -> None:
        active = (
            self.contactor_closed
            and self.cell_delta_v >= self.thresholds.balancing_start_delta_v
        )
        if active and not self.balancing_active:
            log.info("ECU starting cell balancing (delta=%.3f V)", self.cell_delta_v)
        self.balancing_active = active
        if self.cell_delta_v >= self.thresholds.balancing_start_delta_v:
            self.fault_flags |= 0  # imbalance is informational, not latching here

    # ---- publication ------------------------------------------------------
    def set_pack_measurements(self, pack_voltage_v: float, pack_current_a: float,
                              soc_pct: float) -> None:
        """Called by the HIL loop to hand the ECU pack-level analog inputs."""
        self.pack_voltage_v = pack_voltage_v
        self.pack_current_a = pack_current_a
        self.soc_pct = soc_pct

    def _publish(self) -> None:
        self._counter = (self._counter + 1) & 0xFF
        status = self.db.encode("BMS_PackStatus", {
            "PackVoltage": self.pack_voltage_v,
            "PackCurrent": self.pack_current_a,
            "PackSOC": self.soc_pct,
            "PackMode": float(self._command),
            "Counter": self._counter,
            "Checksum": self._checksum(),
        })
        self.bus.send(status)

        limits = self.db.encode("BMS_LimitsStatus", {
            "ContactorClosed": 1.0 if self.contactor_closed else 0.0,
            "FaultFlags": float(self.fault_flags),
            "MaxCellTemp": self.max_cell_temp_c,
            "MaxChargeCurrent": 0.0 if self.fault_flags else self.thresholds.over_current_charge_a,
            "MaxDischargeCurrent": 0.0 if self.fault_flags else self.thresholds.over_current_discharge_a,
        })
        self.bus.send(limits)

    def _checksum(self) -> int:
        return (int(self.pack_voltage_v) + int(self.soc_pct) + self._counter) & 0xFF

    # ---- diagnostics ------------------------------------------------------
    def clear_faults(self) -> None:
        if self.fault_flags:
            log.info("ECU clearing latched faults (was 0x%04X)", self.fault_flags)
        self.fault_flags = 0

    def _on_uds(self, frame: CanFrame) -> None:
        length = frame.data[0] & 0x0F
        body = frame.data[1:1 + length]
        if not body:
            return
        sid = body[0]
        resp: Optional[bytes] = None
        if sid == uds.SID_READ_DATA_BY_ID and len(body) >= 3:
            did = (body[1] << 8) | body[2]
            resp = self._uds_read_did(did)
        elif sid == uds.SID_CLEAR_DTC:
            self.clear_faults()
            resp = bytes([sid + uds.POSITIVE_RESPONSE_OFFSET])
        elif sid == uds.SID_ROUTINE_CONTROL and len(body) >= 4:
            resp = bytes([sid + uds.POSITIVE_RESPONSE_OFFSET, body[1], body[2], body[3]])
        elif sid == uds.SID_ECU_RESET:
            resp = bytes([sid + uds.POSITIVE_RESPONSE_OFFSET, body[1] if len(body) > 1 else 1])

        if resp is None:
            resp = bytes([uds.NEGATIVE_RESPONSE_SID, sid, 0x31])  # requestOutOfRange
        payload = bytes([len(resp)]) + resp
        self.bus.send(CanFrame(0x7E8, payload.ljust(8, b"\x00")))

    def _uds_read_did(self, did: int) -> Optional[bytes]:
        head = bytes([uds.SID_READ_DATA_BY_ID + uds.POSITIVE_RESPONSE_OFFSET,
                      (did >> 8) & 0xFF, did & 0xFF])
        if did == DID_SOC:
            return head + bytes([int(round(self.soc_pct * 2)) & 0xFF])
        if did == DID_FAULT_FLAGS:
            return head + bytes([(self.fault_flags >> 8) & 0xFF, self.fault_flags & 0xFF])
        if did == DID_MAX_CELL_TEMP:
            return head + bytes([int(round(self.max_cell_temp_c + 40)) & 0xFF])
        return None
