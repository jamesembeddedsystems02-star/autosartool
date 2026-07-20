"""Charge / discharge / SOC-tracking functional scenarios.

Sign convention throughout: **positive current = discharge**, negative = charge.
"""

from __future__ import annotations

from ..testing.test_case import HilTestCase, TestContext

CHARGE = 1
DISCHARGE = 2


class ChargeTest(HilTestCase):
    name = "charge_increases_soc"
    category = "functional"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        ctx.check.true(ctx.status.contactor_closed, "contactor closed before charging")
        soc_before = ctx.plant.state.avg_soc
        v_before = ctx.plant.state.pack_voltage_v

        ctx.bench.command_current(-40.0, mode=CHARGE)  # 40 A charge
        ctx.run_for(15.0)

        soc_after = ctx.plant.state.avg_soc
        v_after = ctx.plant.state.pack_voltage_v
        ctx.check.greater(soc_after, soc_before, "SOC increased under charge")
        ctx.check.greater(v_after, v_before, "pack voltage rose under charge")
        ctx.check.true(ctx.status.contactor_closed, "contactor stayed closed (no fault)")
        ctx.check.equal(ctx.status.fault_flags, 0, "no faults during nominal charge")


class DischargeTest(HilTestCase):
    name = "discharge_decreases_soc"
    category = "functional"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        soc_before = ctx.plant.state.avg_soc

        ctx.bench.command_current(40.0, mode=DISCHARGE)  # 40 A discharge
        ctx.run_for(15.0)

        soc_after = ctx.plant.state.avg_soc
        ctx.check.less(soc_after, soc_before, "SOC decreased under discharge")
        ctx.check.greater(ctx.status.pack_current_a, 0.0,
                          "ECU reports positive (discharge) current")
        ctx.check.equal(ctx.status.fault_flags, 0, "no faults during nominal discharge")


class SocTrackingTest(HilTestCase):
    name = "ecu_soc_tracks_plant"
    category = "functional"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        ctx.bench.command_current(30.0, mode=DISCHARGE)
        ctx.run_for(10.0)

        plant_soc_pct = ctx.plant.state.avg_soc * 100.0
        ecu_soc_pct = ctx.status.soc_pct
        ctx.check.true(ctx.status.valid, "ECU status frames received")
        ctx.check.close(ecu_soc_pct, plant_soc_pct, tol=2.0,
                        desc="ECU-reported SOC tracks plant SOC within 2%")
