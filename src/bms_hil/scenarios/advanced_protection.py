"""Advanced protection & reporting scenarios: precharge, thermal runaway,
isolation monitoring, and SOH/SOX reporting."""

from __future__ import annotations

from ..ecu.bms_ecu_stub import (
    CONTACTOR_PRECHARGE,
    FaultBits,
)
from ..testing.test_case import HilTestCase, TestContext

DISCHARGE = 2


class PrechargeSequenceTest(HilTestCase):
    name = "precharge_delays_main_contactor"
    category = "contactor"

    def run(self, ctx: TestContext) -> None:
        ctx.check.false(ctx.status.contactor_closed, "contactor open at power-up")

        # Part-way through precharge the main contactor must not be closed yet.
        ctx.run_for(0.1)  # < precharge_time (0.2 s)
        ctx.check.equal(ctx.ecu.contactor_state, CONTACTOR_PRECHARGE,
                        "ECU in precharge state")
        ctx.check.false(ctx.status.contactor_closed,
                        "main contactor not closed during precharge")

        # After the precharge dwell elapses it closes.
        ctx.run_for(0.25)
        ctx.check.true(ctx.status.contactor_closed,
                       "main contactor closed after precharge dwell")
        ctx.check.equal(ctx.status.fault_flags, 0, "no faults through precharge")


class ThermalRunawayTest(HilTestCase):
    name = "thermal_runaway_trips_and_isolates"
    category = "protection"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        ctx.check.true(ctx.status.contactor_closed, "contactor closed before fault")

        # Drive one cell above the critical temperature (25 + 50 = 75 C > 70 C).
        ctx.plant.cells[0].temp_offset_c = 50.0
        ctx.run_for(0.3)

        ctx.check.true(ctx.status.fault_flags & FaultBits.THERMAL_RUNAWAY,
                       "THERMAL_RUNAWAY fault latched")
        ctx.check.true(ctx.status.fault_flags & FaultBits.OVERTEMP,
                       "OVERTEMP also latched")
        ctx.check.true(ctx.ecu.thermal_runaway, "ECU thermal_runaway flag set")
        ctx.check.false(ctx.status.contactor_closed, "contactor opened")


class IsolationMonitoringTest(HilTestCase):
    name = "low_isolation_opens_contactor"
    category = "protection"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        ctx.check.greater(ctx.status.isolation_kohm,
                          ctx.ecu.thresholds.isolation_min_kohm,
                          "isolation healthy before fault")
        ctx.check.true(ctx.status.contactor_closed, "contactor closed before fault")

        # Insulation degradation: drop HV-to-chassis isolation below the limit.
        ctx.plant.set_isolation_kohm(100.0)
        ctx.run_for(0.3)

        ctx.check.true(ctx.status.fault_flags & FaultBits.ISOLATION,
                       "ISOLATION fault latched")
        ctx.check.false(ctx.status.contactor_closed,
                        "contactor opened on isolation fault")


class SohReportingTest(HilTestCase):
    name = "soh_and_power_limits_reported"
    category = "reporting"

    def run(self, ctx: TestContext) -> None:
        # Aged pack: 82% state of health.
        ctx.plant.set_soh(0.82)
        ctx.bench.settle()

        ctx.check.close(ctx.status.soh_pct, 82.0, tol=1.0,
                        desc="ECU reports pack SOH")
        ctx.check.greater(ctx.status.avail_discharge_power_kw, 0.0,
                          "available discharge power reported (SOX)")
        ctx.check.greater(ctx.status.avail_charge_power_kw, 0.0,
                          "available charge power reported (SOX)")

        # Under a latched fault the available power must collapse to zero.
        ctx.plant.cells[0].voltage_offset_v = 0.6  # force overvoltage
        ctx.run_for(0.2)
        ctx.check.equal(ctx.status.avail_discharge_power_kw, 0.0,
                        "discharge power zeroed under fault")
