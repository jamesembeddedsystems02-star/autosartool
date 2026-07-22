"""Standalone example: drive the HIL bench and inject a fault programmatically.

Run from the repo root after installing the package (``pip install -e .``) or
with ``PYTHONPATH=src python examples/run_demo.py``.
"""

from __future__ import annotations

from bms_hil.core.bench import HilBench
from bms_hil.core.config import Config
from bms_hil.core.logging_setup import setup_logging
from bms_hil.faults import CellVoltageOffsetFault, FaultInjector


def main() -> None:
    setup_logging("INFO")
    cfg = Config.load()  # built-in defaults (12S1P demo pack)
    bench = HilBench(cfg)

    # Schedule an overvoltage fault on cell 0 from t=3s to t=5s.
    injector = FaultInjector(bench.plant, [
        CellVoltageOffsetFault(name="OV_cell0", cell_index=0,
                               start_s=3.0, end_s=5.0, offset_v=0.6),
    ])
    bench.scheduler.add_callback(injector.step)

    print("Power-up / contactor close ...")
    bench.settle(0.3)
    print(f"  contactor_closed={bench.interface.status.contactor_closed} "
          f"soc={bench.plant.state.avg_soc*100:.1f}%")

    print("Discharging at 50 A while a timed OV fault fires at t=3s ...")
    bench.command_current(50.0, mode=2)
    bench.run_for(6.0)

    st = bench.interface.status
    print(f"  final: fault_flags=0x{st.fault_flags:04X} "
          f"contactor_closed={st.contactor_closed} "
          f"soc={bench.plant.state.avg_soc*100:.1f}%")

    bench.logger.to_csv("reports/example_trace.csv")
    print(f"  wrote reports/example_trace.csv ({len(bench.logger.rows)} samples)")
    bench.shutdown()


if __name__ == "__main__":
    main()
