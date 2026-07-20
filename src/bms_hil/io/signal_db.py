"""Minimal CAN signal database (encode/decode) for BMS messages.

This is a lightweight, dependency-free stand-in for a full DBC toolchain
(cantools/Vector CANdb). Signals are little-endian, byte-aligned, unsigned
integers with linear ``physical = raw * factor + offset`` scaling, which covers
the demonstration BMS messages below. For production benches with real DBCs,
swap this module for a cantools-backed database exposing the same
``encode``/``decode`` surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .can_interface import CanFrame


@dataclass
class Signal:
    name: str
    start_byte: int
    length_bytes: int
    factor: float = 1.0
    offset: float = 0.0
    is_signed: bool = False
    unit: str = ""

    def encode(self, physical: float) -> bytes:
        raw = int(round((physical - self.offset) / self.factor))
        max_unsigned = (1 << (8 * self.length_bytes)) - 1
        if self.is_signed:
            half = 1 << (8 * self.length_bytes - 1)
            raw = max(-half, min(half - 1, raw))
            if raw < 0:
                raw += (1 << (8 * self.length_bytes))
        else:
            raw = max(0, min(max_unsigned, raw))
        return raw.to_bytes(self.length_bytes, "little")

    def decode(self, data: bytes) -> float:
        chunk = data[self.start_byte:self.start_byte + self.length_bytes]
        raw = int.from_bytes(chunk, "little")
        if self.is_signed:
            half = 1 << (8 * self.length_bytes - 1)
            if raw >= half:
                raw -= (1 << (8 * self.length_bytes))
        return raw * self.factor + self.offset


@dataclass
class Message:
    name: str
    frame_id: int
    length: int = 8
    signals: List[Signal] = field(default_factory=list)

    def encode(self, values: Dict[str, float]) -> CanFrame:
        buf = bytearray(self.length)
        for sig in self.signals:
            if sig.name not in values:
                continue
            raw = sig.encode(values[sig.name])
            buf[sig.start_byte:sig.start_byte + sig.length_bytes] = raw
        return CanFrame(arbitration_id=self.frame_id, data=bytes(buf))

    def decode(self, frame: CanFrame) -> Dict[str, float]:
        return {sig.name: sig.decode(frame.data) for sig in self.signals}


class SignalDatabase:
    """Collection of messages keyed by both name and CAN id."""

    def __init__(self, messages: List[Message]) -> None:
        self.by_name: Dict[str, Message] = {m.name: m for m in messages}
        self.by_id: Dict[int, Message] = {m.frame_id: m for m in messages}

    def encode(self, message_name: str, values: Dict[str, float]) -> CanFrame:
        return self.by_name[message_name].encode(values)

    def decode(self, frame: CanFrame) -> Dict[str, float]:
        msg = self.by_id.get(frame.arbitration_id)
        if msg is None:
            return {}
        return msg.decode(frame)

    def message_for(self, frame_id: int) -> Message:
        return self.by_id[frame_id]


# ---------------------------------------------------------------------------
# Default BMS demonstration database.
#
#   0x100 BMS_PackStatus   : pack V/I, SOC, mode
#   0x101 BMS_LimitsStatus : contactor state, fault flags, max cell T
#   0x200 SIM_CellVoltages : plant->ECU min/max/delta cell voltage
#   0x300 TESTER_Command   : test harness -> ECU requested current & command
# ---------------------------------------------------------------------------
MSG_PACK_STATUS = 0x100
MSG_LIMITS_STATUS = 0x101
MSG_SOH_STATUS = 0x102
MSG_CELL_VOLTAGES = 0x200
MSG_ISOLATION_STATUS = 0x201
MSG_TESTER_COMMAND = 0x300


def default_bms_database() -> SignalDatabase:
    return SignalDatabase([
        Message(
            name="BMS_PackStatus",
            frame_id=MSG_PACK_STATUS,
            signals=[
                Signal("PackVoltage", 0, 2, factor=0.1, unit="V"),
                Signal("PackCurrent", 2, 2, factor=0.1, offset=-3276.8,
                       is_signed=False, unit="A"),
                Signal("PackSOC", 4, 1, factor=0.5, unit="%"),
                Signal("PackMode", 5, 1, unit="enum"),
                Signal("Counter", 6, 1),
                Signal("Checksum", 7, 1),
            ],
        ),
        Message(
            name="BMS_LimitsStatus",
            frame_id=MSG_LIMITS_STATUS,
            signals=[
                Signal("ContactorClosed", 0, 1, unit="bool"),
                Signal("FaultFlags", 1, 2, unit="bitfield"),
                Signal("MaxCellTemp", 3, 1, factor=1.0, offset=-40.0, unit="degC"),
                Signal("MaxChargeCurrent", 4, 2, factor=0.1, unit="A"),
                Signal("MaxDischargeCurrent", 6, 2, factor=0.1, unit="A"),
            ],
        ),
        Message(
            name="BMS_SohStatus",
            frame_id=MSG_SOH_STATUS,
            signals=[
                Signal("SOH", 0, 1, factor=0.5, unit="%"),
                Signal("AvailChargePower", 1, 2, factor=0.01, unit="kW"),
                Signal("AvailDischargePower", 3, 2, factor=0.01, unit="kW"),
                Signal("IsolationResistance", 5, 2, factor=1.0, unit="kOhm"),
            ],
        ),
        Message(
            name="SIM_CellVoltages",
            frame_id=MSG_CELL_VOLTAGES,
            signals=[
                Signal("MinCellVoltage", 0, 2, factor=0.001, unit="V"),
                Signal("MaxCellVoltage", 2, 2, factor=0.001, unit="V"),
                Signal("CellDelta", 4, 2, factor=0.001, unit="V"),
                Signal("MaxCellTemp", 6, 1, factor=1.0, offset=-40.0, unit="degC"),
            ],
        ),
        Message(
            name="SIM_IsolationStatus",
            frame_id=MSG_ISOLATION_STATUS,
            signals=[
                Signal("IsolationResistance", 0, 2, factor=1.0, unit="kOhm"),
            ],
        ),
        Message(
            name="TESTER_Command",
            frame_id=MSG_TESTER_COMMAND,
            signals=[
                # RequestedCurrent: 0.1 A/bit, signed via offset. + = discharge.
                Signal("RequestedCurrent", 0, 2, factor=0.1, offset=-3276.8, unit="A"),
                Signal("Command", 2, 1, unit="enum"),  # 0=idle 1=charge 2=discharge
                Signal("ClearFaults", 3, 1, unit="bool"),
            ],
        ),
    ])
