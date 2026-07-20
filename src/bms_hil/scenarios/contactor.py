"""Contactor control scenarios: safe close on good state, open on fault."""

from __future__ import annotations

from ..ecu.bms_ecu_stub import FaultBits
from ..testing.test_case import HilTestCase, TestContext


class ContactorCloseTest(HilTestCase):
    name = "contactor_closes_when_healthy"
    category = "contactor"

    def run(self, ctx: TestContext) -> None:
        # Contactor must start open and only close after valid, healthy data.
        ctx.check.false(ctx.status.contactor_closed, "contactor open at power-up")
        ctx.bench.settle()
        ctx.check.true(ctx.status.contactor_closed, "contactor closed once healthy")
        ctx.check.equal(ctx.status.fault_flags, 0, "no faults at power-up")


class ContactorOpenOnFaultTest(HilTestCase):
    name = "contactor_opens_and_isolates_load"
    category = "contactor"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        ctx.bench.command_current(30.0, mode=2)  # nominal discharge
        ctx.run_for(1.0)
        ctx.check.true(ctx.status.contactor_closed, "contactor closed under nominal load")

        # Inject overtemperature; contactor must open and load current must
        # be isolated (driven to zero) by the open contactor.
        ctx.plant.cells[0].temp_offset_c = 45.0
        ctx.run_for(0.5)
        ctx.check.true(ctx.status.fault_flags & FaultBits.OVERTEMP, "OT fault raised")
        ctx.check.false(ctx.status.contactor_closed, "contactor opened")

        ctx.run_for(0.2)
        ctx.check.close(ctx.plant.state.current_a, 0.0, tol=1e-6,
                        desc="load current isolated after contactor opens")
