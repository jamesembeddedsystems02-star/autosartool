"""Passive cell-balancing scenario.

Force one cell to a higher state of charge to create a pack imbalance, then
verify the ECU commands balancing and the plant bleeds the high cell down.
"""

from __future__ import annotations

from ..testing.test_case import HilTestCase, TestContext


class CellBalancingTest(HilTestCase):
    name = "balancing_activates_on_imbalance"
    category = "balancing"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()

        # Drive cell 2 well above the rest -> large delta V.
        ctx.plant.set_cell_soc(2, 0.90)
        ctx.run_for(0.2)

        delta = ctx.plant.state.cell_delta_v
        ctx.check.greater(delta, ctx.ecu.thresholds.balancing_start_delta_v,
                          "cell delta exceeds balancing threshold")
        ctx.check.true(ctx.ecu.balancing_active, "ECU reports balancing active")

        soc_high_before = ctx.plant.cells[2].soc
        ctx.run_for(10.0)
        soc_high_after = ctx.plant.cells[2].soc
        ctx.check.less(soc_high_after, soc_high_before,
                       "high cell SOC bled down by balancing")
        ctx.check.equal(ctx.status.fault_flags, 0,
                        "imbalance handled without a latching fault")
