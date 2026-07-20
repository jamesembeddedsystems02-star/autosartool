from bms_hil.plant.cell_model import CellModel, CellParams, ocv_from_soc


def test_ocv_monotonic_and_bounded():
    prev = -1.0
    for i in range(0, 101):
        v = ocv_from_soc(i / 100.0)
        assert 2.9 <= v <= 4.25
        assert v >= prev - 1e-9
        prev = v


def test_ocv_clamps_out_of_range():
    assert ocv_from_soc(-0.5) == ocv_from_soc(0.0)
    assert ocv_from_soc(1.5) == ocv_from_soc(1.0)


def test_discharge_reduces_soc_and_voltage():
    cell = CellModel(params=CellParams(capacity_ah=10.0), soc=0.8)
    v0 = cell.terminal_voltage
    for _ in range(100):
        cell.step(current_a=5.0, dt_s=0.1)  # discharge
    assert cell.soc < 0.8
    assert cell.terminal_voltage < v0


def test_charge_increases_soc():
    cell = CellModel(params=CellParams(capacity_ah=10.0), soc=0.5)
    for _ in range(100):
        cell.step(current_a=-5.0, dt_s=0.1)  # charge
    assert cell.soc > 0.5


def test_open_circuit_fault_blocks_current():
    cell = CellModel(params=CellParams(capacity_ah=10.0), soc=0.5)
    cell.open_circuit_fault = True
    for _ in range(50):
        cell.step(current_a=20.0, dt_s=0.1)
    assert abs(cell.soc - 0.5) < 1e-9


def test_ohmic_heating_raises_temperature():
    cell = CellModel(params=CellParams(capacity_ah=10.0, r0_ohm=0.05), soc=0.6)
    t0 = cell.temp_c
    for _ in range(500):
        cell.step(current_a=30.0, dt_s=0.1)
    assert cell.temp_c > t0
