# BMS HIL — Battery Management ECU Hardware-in-the-Loop Test Tool

A modular **Hardware-in-the-Loop (HIL)** test framework in Python for validating
**Battery Management System (BMS) ECUs**. It simulates a battery pack, talks to
the ECU over CAN, injects faults, and runs an automated test suite that produces
JUnit XML + HTML reports.

The whole toolchain runs **with no hardware and no third-party packages** — a
built-in virtual CAN bus and a reference BMS ECU stand in for the bench — so you
can develop and run tests anywhere, then point the same tests at a real ECU by
switching one config line.

## ⚡ Fastest start — one file, zero install

Don't want to install anything? Just run the single-file edition with plain
Python (3.8+, standard library only):

```bash
python run_bms_hil.py            # interactive menu
python run_bms_hil.py selftest   # quick health check
python run_bms_hil.py demo       # charge → discharge → fault, writes a trace
python run_bms_hil.py test       # 16-scenario suite + reports/report.html
```

`run_bms_hil.py` is fully self-contained: pack simulation, reference BMS ECU
(protection, precharge contactor, balancing, SOH/SOX), the 16-test suite, and an
HTML report — all in one copy-and-run file. Tune the pack/ECU by editing the
`CONFIG` dict at the top. `matplotlib`, if installed, adds a PNG trace plot.

The rest of this README describes the full **modular package** (`src/bms_hil`),
which adds the CAN transport, DBC/`cantools` decoding, UDS diagnostics, and a
`pip`-installable `bms-hil` command.

```
   plant (BatteryPack)  ── SIM_CellVoltages ──▶  BMS ECU (device under test)
             ▲                                          │
        load current                       BMS_PackStatus / BMS_LimitsStatus
             │                                          ▼
      tester commands  ◀──────────────  EcuInterface (tester side)  ──▶  reports
```

## Features

- **Battery plant model** — per-cell 2nd-order equivalent-circuit (Thevenin,
  2×RC) electrical model with temperature-dependent resistance and SOH capacity
  fade, plus a lumped thermal model, aggregated into a series/parallel pack
  (`bms_hil.plant`).
- **CAN layer** — dependency-free in-process virtual bus, plus an optional
  [`python-can`](https://python-can.readthedocs.io/) backend for real benches.
  Signals come from a built-in encode/decode database **or** a real Vector
  `.dbc` via [`cantools`](https://cantools.readthedocs.io/) (`bms_hil.io`).
- **Reference BMS ECU** — SOC estimation, SOH/SOX reporting, OV/UV/OT/UT/OC +
  isolation protection, thermal-runaway detection, latching faults, a two-step
  precharge contactor state machine, passive cell balancing, and a small UDS
  diagnostic server (`bms_hil.ecu`). Swap it for real hardware transparently.
- **Fault injection** — sensor bias, open-circuit, temperature, cell-imbalance,
  low-isolation and SOH faults with timed activation windows (`bms_hil.faults`).
- **Test framework** — assertion recorder, per-test isolated bench, runner, and
  JUnit/HTML reporting with an embedded matplotlib signal plot
  (`bms_hil.testing`, `bms_hil.report`).
- **Scenarios** — charge, discharge, SOC tracking, drive-cycle replay,
  OV/UV/OT/OC protection, thermal runaway, isolation monitoring, cell balancing,
  SOH/SOX reporting, precharge and contactor control (`bms_hil.scenarios`).

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

1. `pip install python-can cantools` and connect a supported CAN adapter.
2. In your config set `can.backend: python-can`, the right
   `python_can_interface` / `channel` (e.g. `socketcan` / `can0`), and
   `can.dbc_path` pointing at your ECU's `.dbc` communication matrix.
3. Wire the tester CAN to the ECU. The built-in ECU stub is disabled
   automatically; the same scenarios now exercise your real BMS ECU.

> `config/bms.dbc` is a sample matching the built-in messages. When you supply
> your own DBC, keep the message/signal names the scenarios reference (or adapt
> the scenarios). Without a DBC the built-in `bms_hil/io/signal_db.py` is used.

### Using a DBC in simulation

```bash
bms-hil -c /dev/stdin test <<'YAML'
can: { dbc_path: config/bms.dbc }
YAML
# ...or simply set can.dbc_path in config/hil_config.yaml
```

The DBC path swaps the signal database for a `cantools`-backed one; the plant,
ECU and every scenario run unchanged.

## Project layout

```
src/bms_hil/
  core/       config, logging, fixed-step scheduler, HIL bench orchestrator
  plant/      cell model (2-RC + thermal + SOH) + battery pack plant
  io/         CAN bus (virtual + python-can), signal DB, DBC loader, UDS client
  ecu/        reference BMS ECU stub + tester-side interface
  faults/     fault-injection engine
  testing/    assertions, test case/context, runner
  scenarios/  concrete test scenarios + default suite
  report/     data logger, JUnit + HTML report generators, matplotlib plots
  cli.py      `bms-hil` command-line entry point
config/       example YAML configs (sim + hardware) and sample bms.dbc
examples/     scripted usage example
tests/        pytest unit + end-to-end tests
.github/      CI workflow (pytest matrix + ruff + mypy)
```

## Development

```bash
./setup_env.sh --dev
source .venv/bin/activate
pytest                      # unit + scenario + DBC + UDS + plot tests
ruff check src tests        # lint
mypy                        # type-check
```

A `SessionStart` hook (`.claude/settings.json`) installs the package with dev
extras automatically at the start of a Claude Code session so tests and linters
are ready to run.

## Optional dependencies

| Extra        | Unlocks                                            |
|--------------|----------------------------------------------------|
| `hardware`   | `python-can` backend for real CAN adapters         |
| `dbc`        | `cantools` DBC communication-matrix decoding       |
| `config`     | `pyyaml` YAML config files (JSON works without it)  |
| `analysis`   | `numpy` / `matplotlib` (embedded report plots)     |
| `full`       | all of the above                                   |
| `dev`        | test + lint + type-check tooling                   |

```bash
pip install -e ".[full]"    # everything
```

## License

MIT
