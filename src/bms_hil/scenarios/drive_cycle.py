"""Drive-cycle replay: feed a time-varying current profile to the pack.

A :class:`DriveCycle` is a piecewise-linear current-vs-time profile (positive =
discharge / traction, negative = charge / regen). The scenario replays it and
verifies the ECU keeps the pack safe (no faults, contactor closed, temperature
bounded) across the whole cycle while SOC nets down.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from ..testing.test_case import HilTestCase, TestContext

DISCHARGE = 2
CHARGE = 1


@dataclass
class DriveCycle:
    """Piecewise-linear current profile as a list of ``(time_s, current_a)``."""

    points: List[Tuple[float, float]]

    @property
    def duration(self) -> float:
        return self.points[-1][0] if self.points else 0.0

    def current_at(self, t: float) -> float:
        pts = self.points
        if t <= pts[0][0]:
            return pts[0][1]
        if t >= pts[-1][0]:
            return pts[-1][1]
        for (t0, i0), (t1, i1) in zip(pts, pts[1:]):
            if t0 <= t <= t1:
                frac = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                return i0 + frac * (i1 - i0)
        return pts[-1][1]

    @classmethod
    def example(cls) -> "DriveCycle":
        """A short mixed accel / regen / cruise cycle that nets to discharge."""
        return cls([
            (0.0, 0.0),
            (2.0, 120.0),   # hard acceleration (traction)
            (4.0, 40.0),    # cruise
            (5.0, -80.0),   # regenerative braking (charge)
            (7.0, 30.0),    # light cruise
            (9.0, 100.0),   # acceleration
            (11.0, 20.0),   # cruise
            (12.0, -60.0),  # regen
            (14.0, 50.0),   # cruise
            (16.0, 0.0),    # coast to stop
        ])


class DriveCycleReplayTest(HilTestCase):
    name = "drive_cycle_replay_stays_safe"
    category = "drive_cycle"

    def run(self, ctx: TestContext) -> None:
        ctx.bench.settle()
        ctx.check.true(ctx.status.contactor_closed, "contactor closed before cycle")
        ctx.logger.clear()  # only assess the cycle window

        cycle = DriveCycle.example()
        soc_before = ctx.plant.state.avg_soc

        dt = 0.1
        t = 0.0
        while t < cycle.duration:
            i = cycle.current_at(t)
            ctx.bench.command_current(i, mode=DISCHARGE if i >= 0 else CHARGE)
            ctx.run_for(dt)
            t += dt

        soc_after = ctx.plant.state.avg_soc
        assert ctx.bench.ecu is not None  # internal ECU present in virtual mode
        over_temp = ctx.bench.ecu.thresholds.over_temp_c

        ctx.check.equal(ctx.logger.max("fault_flags"), 0.0,
                        "no faults raised during drive cycle")
        ctx.check.equal(ctx.logger.min("contactor_closed"), 1.0,
                        "contactor stayed closed throughout cycle")
        ctx.check.less(ctx.logger.max("max_temp_c"), over_temp,
                       "pack temperature stayed below over-temp limit")
        ctx.check.less(soc_after, soc_before,
                       "net SOC decreased over the (net-discharge) cycle")
