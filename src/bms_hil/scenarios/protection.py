"""Protection scenarios: OV / UV / OT / OC and fault clear + recovery.

Faults are injected by mutating the plant directly (sensor bias, forced cell
state) which is the analog of a fault-insertion unit on a real HIL bench.
"""

from __future__ import annotations

from ..ecu.bms_ecu_stub import FaultBits
from ..testing.test_case import HilTestCase, TestContext

DISCHARGE = 2


class OvervoltageProtectionTest(HilTestCase):
    name = "overvoltage_opens_contactor"
    category = "protection"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        ctx.check.true(ctx.status.contactor_closed, "contactor initially closed")

        # Bias cell 0's sensed voltage above the 4.20 V limit.
        ctx.plant.cells[0].voltage_offset_v = 0.5
        ctx.run_for(0.3)

        ctx.check.true(ctx.status.fault_flags & FaultBits.OVERVOLTAGE,
                       "OVERVOLTAGE fault latched")
        ctx.check.false(ctx.status.contactor_closed,
                        "contactor opened on overvoltage")


class UndervoltageProtectionTest(HilTestCase):
    name = "undervoltage_opens_contactor"
    category = "protection"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        ctx.plant.cells[3].voltage_offset_v = -1.2  # push below 2.80 V
        ctx.run_for(0.3)

        ctx.check.true(ctx.status.fault_flags & FaultBits.UNDERVOLTAGE,
                       "UNDERVOLTAGE fault latched")
        ctx.check.false(ctx.status.contactor_closed,
                        "contactor opened on undervoltage")


class OvertemperatureProtectionTest(HilTestCase):
    name = "overtemperature_opens_contactor"
    category = "protection"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        ctx.plant.cells[5].temp_offset_c = 40.0  # 25 + 40 = 65 C > 55 C limit
        ctx.run_for(0.3)

        ctx.check.true(ctx.status.fault_flags & FaultBits.OVERTEMP,
                       "OVERTEMP fault latched")
        ctx.check.false(ctx.status.contactor_closed,
                        "contactor opened on overtemperature")


class OvercurrentProtectionTest(HilTestCase):
    name = "overcurrent_discharge_opens_contactor"
    category = "protection"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        # Command 250 A discharge; limit is 200 A.
        ctx.bench.command_current(250.0, mode=DISCHARGE)
        ctx.run_for(0.3)

        ctx.check.true(ctx.status.fault_flags & FaultBits.OVERCURRENT_DISCHARGE,
                       "OVERCURRENT_DISCHARGE fault latched")
        ctx.check.false(ctx.status.contactor_closed,
                        "contactor opened on overcurrent")


class FaultClearAndRecoverTest(HilTestCase):
    name = "fault_clears_and_contactor_recloses"
    category = "protection"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()

        # Trip overvoltage.
        ctx.plant.cells[0].voltage_offset_v = 0.5
        ctx.run_for(0.3)
        ctx.check.true(ctx.status.fault_flags & FaultBits.OVERVOLTAGE, "OV tripped")
        ctx.check.false(ctx.status.contactor_closed, "contactor open while faulted")

        # Remove the fault condition, then clear latched faults.
        ctx.plant.cells[0].voltage_offset_v = 0.0
        ctx.bench.clear_faults()
        ctx.run_for(0.3)

        ctx.check.equal(ctx.status.fault_flags, 0, "faults cleared")
        ctx.check.true(ctx.status.contactor_closed, "contactor re-closed after recovery")
