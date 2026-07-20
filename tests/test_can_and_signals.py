import pytest

from bms_hil.io.can_interface import CanFrame, VirtualCanBus
from bms_hil.io.signal_db import default_bms_database


@pytest.fixture(autouse=True)
def _clean_channel():
    VirtualCanBus.reset_channel("t")
    yield
    VirtualCanBus.reset_channel("t")


def test_virtual_bus_broadcast_between_two_nodes():
    a = VirtualCanBus("t")
    b = VirtualCanBus("t")
    a.send(CanFrame(0x123, b"\x01\x02"))
    rx = b.recv(timeout=0.1)
    assert rx is not None
    assert rx.arbitration_id == 0x123
    assert rx.data == b"\x01\x02"
    # sender does not hear its own frame
    assert a.recv() is None
    a.shutdown()
    b.shutdown()


def test_frame_rejects_oversized_payload():
    with pytest.raises(ValueError):
        CanFrame(0x1, b"123456789")


def test_signal_roundtrip_pack_status():
    db = default_bms_database()
    frame = db.encode("BMS_PackStatus", {
        "PackVoltage": 48.6, "PackCurrent": 12.5, "PackSOC": 55.0,
        "PackMode": 2, "Counter": 7, "Checksum": 9,
    })
    decoded = db.decode(frame)
    assert abs(decoded["PackVoltage"] - 48.6) < 0.1
    assert abs(decoded["PackCurrent"] - 12.5) < 0.1
    assert abs(decoded["PackSOC"] - 55.0) < 0.5
    assert decoded["PackMode"] == 2


def test_signed_current_via_offset_handles_charge():
    db = default_bms_database()
    frame = db.encode("TESTER_Command", {"RequestedCurrent": -40.0, "Command": 1})
    decoded = db.decode(frame)
    assert abs(decoded["RequestedCurrent"] - (-40.0)) < 0.1
