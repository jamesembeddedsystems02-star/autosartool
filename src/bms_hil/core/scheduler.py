"""Fixed-step scheduler that drives the HIL loop.

The scheduler advances simulated time in fixed steps and invokes registered
callbacks each step. In non-realtime mode it runs as fast as possible (useful
for CI and batch test runs); in realtime mode it paces itself to wall-clock
time so timing-sensitive ECU behaviour can be exercised against a real bench.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List

from .logging_setup import get_logger

log = get_logger("bms_hil.scheduler")

# Callback signature: fn(t_s: float, dt_s: float) -> None
StepCallback = Callable[[float, float], None]


@dataclass
class Scheduler:
    step_ms: float = 10.0
    realtime: bool = False
    _callbacks: List[StepCallback] = field(default_factory=list)
    _sim_time_s: float = 0.0
    _step_count: int = 0

    @property
    def dt_s(self) -> float:
        return self.step_ms / 1000.0

    @property
    def sim_time_s(self) -> float:
        return self._sim_time_s

    @property
    def step_count(self) -> int:
        return self._step_count

    def add_callback(self, cb: StepCallback) -> None:
        self._callbacks.append(cb)

    def reset(self) -> None:
        self._sim_time_s = 0.0
        self._step_count = 0

    def run_for(self, duration_s: float) -> None:
        """Run the loop for *duration_s* simulated seconds."""
        n_steps = max(1, int(round(duration_s / self.dt_s)))
        self.run_steps(n_steps)

    def run_steps(self, n_steps: int) -> None:
        dt = self.dt_s
        wall_start = time.perf_counter()
        for _ in range(n_steps):
            for cb in self._callbacks:
                cb(self._sim_time_s, dt)
            self._sim_time_s += dt
            self._step_count += 1
            if self.realtime:
                target = wall_start + self._step_count * dt
                sleep_for = target - time.perf_counter()
                if sleep_for > 0:
                    time.sleep(sleep_for)
