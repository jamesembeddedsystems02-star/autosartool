# BMS HIL — Battery Management ECU Hardware-in-the-Loop Test Tool

A modular **Hardware-in-the-Loop (HIL)** test framework in Python for validating
**Battery Management System (BMS) ECUs**. It simulates a battery pack, talks to
the ECU over CAN, injects faults, and runs an automated test suite that produces
JUnit XML + HTML reports.

The whole toolchain runs **with no hardware and no third-party packages** — a
built-in virtual CAN bus and a reference BMS ECU stand in for the bench — so you
can develop and run tests anywhere, then point the same tests at a real ECU by
switching one config line.

```
   plant (BatteryPack)  ── SIM_CellVoltages ──▶  BMS ECU (device under test)
             ▲                                          │
        load current                       BMS_PackStatus / BMS_LimitsStatus
             │                                          ▼
      tester commands  ◀──────────────  EcuInterface (tester side)  ──▶  reports
```

## Features

- **Battery plant model** — per-cell 1st-order equivalent-circuit (Thevenin)
  electrical model + lumped thermal model, aggregated into a series/parallel
  pack (`bms_hil.plant`).
- **CAN layer** — dependency-free in-process virtual bus, plus an optional
  [`python-can`](https://python-can.readthedocs.io/) backend for real benches;
  simple signal encode/decode database (`bms_hil.io`).
- **Reference BMS ECU** — SOC estimation, OV/UV/OT/UT/OC protection, latching
  faults, contactor control, passive cell balancing, and a small UDS
  diagnostic server (`bms_hil.ecu`). Swap it for real hardware transparently.
- **Fault injection** — sensor bias, open-circuit, temperature and cell-imbalance
  faults with timed activation windows (`bms_hil.faults`).
- **Test framework** — assertion recorder, per-test isolated bench, runner, and
  JUnit/HTML reporting (`bms_hil.testing`, `bms_hil.report`).
- **Scenarios** — charge, discharge, SOC tracking, OV/UV/OT/OC protection, cell
  balancing, and contactor control (`bms_hil.scenarios`).

## Quick start

```bash
# 1. Create the Python environment (.venv) and install the package
./setup_env.sh              # add --dev for pytest/numpy/matplotlib
source .venv/bin/activate

# 2. Run
bms-hil selftest            # fast wiring check
bms-hil demo                # charge → discharge → overtemp fault, writes a CSV trace
bms-hil test                # full HIL regression suite → reports/junit.xml + report.html
bms-hil info                # print the resolved configuration
```

No environment needed to try it immediately (stdlib-only core):

```bash
PYTHONPATH=src python -m bms_hil selftest
PYTHONPATH=src python -m bms_hil test
```

## Configuration

All behaviour is driven by layered config: built-in defaults, an optional
YAML/JSON file, then overrides. Pass a file with `-c`:

```bash
bms-hil -c config/hil_config.yaml test
bms-hil -c config/hardware_bench.yaml test   # drives a real ECU via python-can
```

Key sections (see `config/hil_config.yaml`): `pack`, `cell`, `ecu`
(protection thresholds), `can` (backend/channel), `schedule` (step & realtime),
`report`.

### Running against real hardware

1. `pip install python-can` and connect a supported CAN adapter.
2. In your config set `can.backend: python-can` and the right
   `python_can_interface` / `channel` (e.g. `socketcan` / `can0`).
3. Wire the tester CAN to the ECU. The built-in ECU stub is disabled
   automatically; the same scenarios now exercise your real BMS ECU.

> Adapt `bms_hil/io/signal_db.py` (or replace it with a `cantools` DBC loader)
> and the DID/message IDs to match your ECU's communication matrix.

## Project layout

```
src/bms_hil/
  core/       config, logging, fixed-step scheduler, HIL bench orchestrator
  plant/      cell model + battery pack plant
  io/         CAN bus (virtual + python-can), signal DB, UDS client
  ecu/        reference BMS ECU stub + tester-side interface
  faults/     fault-injection engine
  testing/    assertions, test case/context, runner
  scenarios/  concrete test scenarios + default suite
  report/     data logger, JUnit + HTML report generators
  cli.py      `bms-hil` command-line entry point
config/       example YAML configs (sim + hardware)
examples/     scripted usage example
tests/        pytest unit + end-to-end tests
```

## Development

```bash
./setup_env.sh --dev
source .venv/bin/activate
pytest                      # unit + scenario tests
```

## License

MIT
