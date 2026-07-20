from bms_hil.core.config import Config
from bms_hil.plant.battery_pack import BatteryPack
from bms_hil.faults import (
    CellVoltageOffsetFault,
    OpenCircuitFault,
    FaultInjector,
)


def _pack():
    return BatteryPack(Config.load())


def test_voltage_offset_fault_window():
    pack = _pack()
    fault = CellVoltageOffsetFault(name="ov", cell_index=0,
                                   start_s=1.0, end_s=2.0, offset_v=0.5)
    inj = FaultInjector(pack, [fault])

    inj.step(0.5, 0.1)
    assert pack.cells[0].voltage_offset_v == 0.0  # before window
    inj.step(1.5, 0.1)
    assert pack.cells[0].voltage_offset_v == 0.5  # inside window
    inj.step(2.5, 0.1)
    assert pack.cells[0].voltage_offset_v == 0.0  # after window


def test_open_circuit_fault_toggles():
    pack = _pack()
    fault = OpenCircuitFault(name="oc", cell_index=2, start_s=0.0, end_s=1.0)
    inj = FaultInjector(pack, [fault])
    inj.step(0.0, 0.1)
    assert pack.cells[2].open_circuit_fault is True
    inj.step(1.0, 0.1)
    assert pack.cells[2].open_circuit_fault is False


def test_clear_reverts_active_faults():
    pack = _pack()
    fault = CellVoltageOffsetFault(name="ov", cell_index=1,
                                   start_s=0.0, end_s=99.0, offset_v=0.3)
    inj = FaultInjector(pack, [fault])
    inj.step(0.1, 0.1)
    assert pack.cells[1].voltage_offset_v == 0.3
    inj.clear()
    assert pack.cells[1].voltage_offset_v == 0.0
    assert inj.faults == []
