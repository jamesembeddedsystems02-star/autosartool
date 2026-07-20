"""UDS diagnostics tests against the reference ECU over the virtual bus."""

import pytest

from bms_hil.core.bench import HilBench
from bms_hil.core.config import Config
from bms_hil.ecu import bms_ecu_stub as ecu
from bms_hil.io.can_interface import VirtualCanBus


@pytest.fixture
def bench():
    VirtualCanBus.reset_channel("hil0")
    b = HilBench(Config.load())
    b.settle(0.3)
    yield b
    b.shutdown()
    VirtualCanBus.reset_channel("hil0")


def test_read_soc_did(bench):
    # send request, then let the ECU service it, then read response
    from bms_hil.io.can_interface import CanFrame
    payload = bytes([0x03, ecu.uds.SID_READ_DATA_BY_ID,
                     (ecu.DID_SOC >> 8) & 0xFF, ecu.DID_SOC & 0xFF]).ljust(8, b"\x00")
    bench.tester_bus.send(CanFrame(0x7E0, payload))
    bench.ecu.step(0.01)
    resp = bench.tester_bus.recv(timeout=0.1)
    assert resp is not None and resp.arbitration_id == 0x7E8
    body = resp.data[1:1 + (resp.data[0] & 0x0F)]
    assert body[0] == ecu.uds.SID_READ_DATA_BY_ID + ecu.uds.POSITIVE_RESPONSE_OFFSET
    soc_pct = body[3] * 0.5
    assert 40.0 < soc_pct < 70.0


def test_read_fault_did_reflects_state(bench):
    from bms_hil.io.can_interface import CanFrame
    # Trip an overvoltage fault first.
    bench.plant.cells[0].voltage_offset_v = 0.6
    bench.run_for(0.2)

    payload = bytes([0x03, ecu.uds.SID_READ_DATA_BY_ID,
                     (ecu.DID_FAULT_FLAGS >> 8) & 0xFF,
                     ecu.DID_FAULT_FLAGS & 0xFF]).ljust(8, b"\x00")
    bench.tester_bus.send(CanFrame(0x7E0, payload))
    bench.ecu.step(0.01)
    resp = bench.tester_bus.recv(timeout=0.1)
    assert resp is not None
    body = resp.data[1:1 + (resp.data[0] & 0x0F)]
    flags = (body[3] << 8) | body[4]
    assert flags & ecu.FaultBits.OVERVOLTAGE


def test_unknown_did_negative_response(bench):
    from bms_hil.io.can_interface import CanFrame
    payload = bytes([0x03, ecu.uds.SID_READ_DATA_BY_ID, 0xAB, 0xCD]).ljust(8, b"\x00")
    bench.tester_bus.send(CanFrame(0x7E0, payload))
    bench.ecu.step(0.01)
    resp = bench.tester_bus.recv(timeout=0.1)
    assert resp is not None
    body = resp.data[1:1 + (resp.data[0] & 0x0F)]
    assert body[0] == ecu.uds.NEGATIVE_RESPONSE_SID
