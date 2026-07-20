"""Command-line interface for the BMS HIL test tool.

Subcommands:

    bms-hil test        Run the HIL regression suite and write reports.
    bms-hil demo        Run a short charge/discharge/fault demo with a live log.
    bms-hil selftest    Fast internal check that the toolchain is wired up.
    bms-hil info        Print the resolved configuration.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .core.config import Config
from .core.logging_setup import get_logger, setup_logging

log = get_logger("bms_hil.cli")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bms-hil",
                                description="Battery Management ECU HIL test tool")
    p.add_argument("-c", "--config", help="Path to YAML/JSON config file")
    p.add_argument("-v", "--verbose", action="store_true", help="DEBUG logging")
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("test", help="Run the HIL regression suite")
    t.add_argument("-o", "--output-dir", default=None, help="Report output directory")
    t.add_argument("-k", "--filter", default=None,
                   help="Only run tests whose name/category contains this text")

    sub.add_parser("demo", help="Run a short interactive demo scenario")
    sub.add_parser("selftest", help="Quick wiring check (fast, for CI smoke test)")
    sub.add_parser("info", help="Print resolved configuration")
    return p


def _load_config(args: argparse.Namespace) -> Config:
    cfg = Config.load(path=args.config)
    if args.verbose:
        cfg.data.setdefault("logging", {})["level"] = "DEBUG"
    setup_logging(cfg.get("logging.level", "INFO"))
    return cfg


def _capture_trace(cfg: Config):
    """Run a short charge/discharge/fault sequence to embed in the report."""
    from .core.bench import HilBench
    from .scenarios.drive_cycle import DriveCycle

    bench = HilBench(cfg)
    try:
        bench.settle(0.3)
        cycle = DriveCycle.example()
        t = 0.0
        while t < cycle.duration:
            i = cycle.current_at(t)
            bench.command_current(i, mode=2 if i >= 0 else 1)
            bench.run_for(0.1)
            t += 0.1
        # end with an overtemperature fault to show a protection event
        bench.plant.cells[0].temp_offset_c = 50.0
        bench.run_for(0.5)
        return bench.logger
    finally:
        bench.shutdown()


def cmd_test(cfg: Config, args: argparse.Namespace) -> int:
    from .scenarios import default_suite
    from .testing.test_runner import TestRunner

    tests = default_suite()
    if args.filter:
        needle = args.filter.lower()
        tests = [t for t in tests
                 if needle in t.name.lower() or needle in t.category.lower()]
        if not tests:
            log.error("No tests match filter %r", args.filter)
            return 2

    runner = TestRunner(cfg)
    runner.run(tests)
    summary = runner.summary()
    trace = _capture_trace(cfg)
    reports = runner.write_reports(args.output_dir, trace_logger=trace)

    log.info("-" * 60)
    log.info("RESULTS: %(total)d total | %(pass)d pass | %(fail)d fail | "
             "%(error)d error | %(skip)d skip", summary)
    log.info("Reports: %s", ", ".join(reports.values()))
    return 0 if runner.passed else 1


def cmd_demo(cfg: Config, args: argparse.Namespace) -> int:
    from .core.bench import HilBench

    log.info("=== BMS HIL demo: 12S pack, charge -> discharge -> overtemp fault ===")
    bench = HilBench(cfg)
    try:
        bench.settle(0.3)
        log.info("power-up: contactor_closed=%s soc=%.1f%%",
                 bench.interface.status.contactor_closed,
                 bench.plant.state.avg_soc * 100)

        log.info("-> charging at 40 A for 8 s")
        bench.command_current(-40.0, mode=1)
        bench.run_for(8.0)
        log.info("   soc=%.2f%%  pack_v=%.1f V  max_cell=%.3f V",
                 bench.plant.state.avg_soc * 100, bench.plant.state.pack_voltage_v,
                 bench.plant.state.max_cell_v)

        log.info("-> discharging at 60 A for 8 s")
        bench.command_current(60.0, mode=2)
        bench.run_for(8.0)
        log.info("   soc=%.2f%%  pack_v=%.1f V  max_temp=%.1f C",
                 bench.plant.state.avg_soc * 100, bench.plant.state.pack_voltage_v,
                 bench.plant.state.max_temp_c)

        log.info("-> injecting overtemperature on cell 4")
        bench.plant.cells[4].temp_offset_c = 45.0
        bench.run_for(0.5)
        st = bench.interface.status
        log.info("   fault_flags=0x%04X contactor_closed=%s",
                 st.fault_flags, st.contactor_closed)

        out = cfg.get("report.output_dir", "reports")
        import os
        os.makedirs(out, exist_ok=True)
        csv_path = os.path.join(out, "demo_trace.csv")
        bench.logger.to_csv(csv_path)
        log.info("Signal trace written to %s (%d samples)",
                 csv_path, len(bench.logger.rows))

        from .report.plots import have_matplotlib, plot_logger_png
        if have_matplotlib():
            png = plot_logger_png(bench.logger, os.path.join(out, "demo_trace.png"))
            log.info("Trace plot written to %s", png)
        else:
            log.info("Install matplotlib to also render a PNG trace plot")
    finally:
        bench.shutdown()
    return 0


def cmd_selftest(cfg: Config, args: argparse.Namespace) -> int:
    from .core.bench import HilBench

    ok = True
    bench = HilBench(cfg)
    try:
        bench.settle(0.3)
        st = bench.interface.status
        checks = [
            ("ECU status received", st.valid),
            ("contactor closed when healthy", st.contactor_closed),
            ("no spurious faults", st.fault_flags == 0),
            ("pack voltage plausible", 30.0 < st.pack_voltage_v < 55.0),
        ]
        for desc, passed in checks:
            log.info("[%s] %s", "PASS" if passed else "FAIL", desc)
            ok = ok and passed
    finally:
        bench.shutdown()
    log.info("selftest %s", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def cmd_info(cfg: Config, args: argparse.Namespace) -> int:
    import json
    print(json.dumps(cfg.data, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cfg = _load_config(args)

    dispatch = {
        "test": cmd_test,
        "demo": cmd_demo,
        "selftest": cmd_selftest,
        "info": cmd_info,
    }
    handler = dispatch[args.command]
    return handler(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
