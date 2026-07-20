"""Very small UDS (ISO 14229) diagnostic client over CAN.

Implements the request/response half of a handful of common services so tests
can read DIDs (e.g. SOC, fault memory) and trigger routines on the ECU. The
transport is single-frame only (payloads <= 7 bytes), which is sufficient for
the demonstration DIDs; extend with ISO-TP for multi-frame payloads on a real
bench.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .can_interface import CanBus, CanFrame

# Service IDs
SID_DIAGNOSTIC_SESSION_CONTROL = 0x10
SID_ECU_RESET = 0x11
SID_READ_DATA_BY_ID = 0x22
SID_ROUTINE_CONTROL = 0x31
SID_CLEAR_DTC = 0x14
SID_READ_DTC = 0x19

POSITIVE_RESPONSE_OFFSET = 0x40
NEGATIVE_RESPONSE_SID = 0x7F


@dataclass
class UdsResponse:
    positive: bool
    service_id: int
    data: bytes
    nrc: Optional[int] = None  # negative response code


class UdsClient:
    """Tester-side UDS client. Pairs a request id with a response id."""

    def __init__(self, bus: CanBus, request_id: int = 0x7E0,
                 response_id: int = 0x7E8, timeout_s: float = 0.5) -> None:
        self.bus = bus
        self.request_id = request_id
        self.response_id = response_id
        self.timeout_s = timeout_s

    def _request(self, payload: bytes) -> UdsResponse:
        if len(payload) > 7:
            raise ValueError("single-frame UDS payload must be <= 7 bytes")
        # ISO-TP single frame: PCI nibble 0 + length, then data.
        frame_data = bytes([len(payload)]) + payload
        frame_data = frame_data.ljust(8, b"\x00")
        self.bus.send(CanFrame(self.request_id, frame_data))
        resp = self.bus.recv(timeout=self.timeout_s)
        # Drain until we see our response id (ignore unrelated periodic traffic).
        import time as _t
        deadline = _t.perf_counter() + self.timeout_s
        while resp is not None and resp.arbitration_id != self.response_id:
            if _t.perf_counter() > deadline:
                break
            resp = self.bus.recv(timeout=self.timeout_s)
        if resp is None or resp.arbitration_id != self.response_id:
            return UdsResponse(False, payload[0], b"", nrc=0x100)  # timeout marker
        length = resp.data[0] & 0x0F
        body = resp.data[1:1 + length]
        if body and body[0] == NEGATIVE_RESPONSE_SID:
            return UdsResponse(False, body[1] if len(body) > 1 else 0,
                               b"", nrc=body[2] if len(body) > 2 else None)
        return UdsResponse(True, body[0] - POSITIVE_RESPONSE_OFFSET, body[1:])

    def read_data_by_id(self, did: int) -> UdsResponse:
        return self._request(bytes([SID_READ_DATA_BY_ID, (did >> 8) & 0xFF, did & 0xFF]))

    def routine_control(self, sub_function: int, routine_id: int) -> UdsResponse:
        return self._request(bytes([
            SID_ROUTINE_CONTROL, sub_function,
            (routine_id >> 8) & 0xFF, routine_id & 0xFF,
        ]))

    def clear_dtc(self) -> UdsResponse:
        return self._request(bytes([SID_CLEAR_DTC, 0xFF, 0xFF, 0xFF]))

    def ecu_reset(self, reset_type: int = 0x01) -> UdsResponse:
        return self._request(bytes([SID_ECU_RESET, reset_type]))
