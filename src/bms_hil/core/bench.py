"""The HIL bench: wires plant, CAN bus, ECU and tester into one loop.

A :class:`HilBench` owns every moving part of a Hardware-in-the-Loop run:

    plant (BatteryPack)  --SIM_CellVoltages-->  ECU (device under test)
              ^                                        |
              |                                BMS_PackStatus / Limits
         load current                                 v
     tester commands  <---------  EcuInterface (tester side)

On each control step the bench:
  1. reads the commanded load current (from the last tester command),
  2. advances the battery plant one step,
  3. pushes fresh cell measurements to the ECU and lets the ECU run its logic,
  4. polls the ECU status back to the tester,
  5. logs all channels of interest.

When ``can.backend == "virtual"`` the ECU is the built-in :class:`BmsEcuStub`
running in-process. When pointed at real hardware (``python-can``), the ECU is
external and the bench simply skips stepping the stub.
"""

from __future__ import annotations

from typing import Optional

from ..ecu.bms_ecu_stub import BmsEcuStub, EcuThresholds
from ..ecu.ecu_interface import EcuInterface
from ..io.can_interface import CanBus, VirtualCanBus, create_bus
from ..io.dbc import load_signal_database
from ..plant.battery_pack import BatteryPack
from ..report.data_logger import DataLogger
from .config import Config
from .logging_setup import get_logger
from .scheduler import Scheduler

log = get_logger("bms_hil.bench")


class HilBench:
    def __init__(self, config: Config, use_internal_ecu: Optional[bool] = None) -> None:
        self.config = config

        # Separate bus handles for plant/tester and ECU so a node never hears
        # its own transmissions (matches real two-node CAN behaviour).
        self.tester_bus: CanBus = create_bus(config.section("can"))
        backend = str(config.get("can.backend", "virtual")).lower()
        self._internal_ecu = (
            backend in ("virtual", "builtin", "inproc")
            if use_internal_ecu is None else use_internal_ecu
        )

        # One signal database (built-in, or a DBC when can.dbc_path is set),
        # shared by the tester interface and the internal ECU.
        self.db = load_signal_database(config)

        self.plant = BatteryPack(config)
        self.interface = EcuInterface(self.tester_bus, db=self.db)
        self.logger = DataLogger()

        self.ecu: Optional[BmsEcuStub] = None
        self.ecu_bus: Optional[CanBus] = None
        if self._internal_ecu:
            self.ecu_bus = create_bus(config.section("can"))
            self.ecu = BmsEcuStub(
                bus=self.ecu_bus,
                thresholds=EcuThresholds.from_config_section(config.section("ecu")),
                db=self.db,
            )

        self.scheduler = Scheduler(
            step_ms=float(config.get("schedule.step_ms", 10.0)),
            realtime=bool(config.get("schedule.realtime", False)),
        )
        self._commanded_current_a = 0.0
        self._command_mode = 0
        self.scheduler.add_callback(self._step)

    # ---- tester command surface ------------------------------------------
    def command_current(self, current_a: float, mode: int = 0) -> None:
        """Set the load current the plant will carry (+ discharge, - charge)."""
        self._commanded_current_a = current_a
        self._command_mode = mode
        self.interface.send_command(current_a, command=mode)

    def clear_faults(self) -> None:
        self.interface.send_command(self._commanded_current_a,
                                    command=self._command_mode, clear_faults=True)

    # ---- main step --------------------------------------------------------
    def _step(self, t_s: float, dt_s: float) -> None:
        # 1) contactor gating: open contactor => no current flows.
        status = self.interface.status
        current = self._commanded_current_a
        if self.ecu is not None and not self.ecu.contactor_closed and self.ecu._seen_data:
            current = 0.0

        # 2) advance plant.
        state = self.plant.step(current, dt_s, time_s=t_s)

        # 3) hand measurements to ECU and run its control logic.
        self.interface.publish_cell_measurements(state)
        if self.ecu is not None:
            self.ecu.set_pack_measurements(
                pack_voltage_v=state.pack_voltage_v,
                pack_current_a=state.current_a,
                soc_pct=state.avg_soc * 100.0,
                soh_pct=state.soh * 100.0,
            )
            # apply passive balancing bleed to the plant
            if self.ecu.balancing_active:
                bleed = [
                    self.ecu.thresholds.balancing_current_a
                    if (cv - state.min_cell_v) >= self.ecu.thresholds.balancing_start_delta_v
                    else 0.0
                    for cv in state.cell_voltages_v
                ]
                self.plant.apply_balancing(bleed, dt_s)
            self.ecu.step(dt_s)

        # 4) poll ECU -> tester.
        self.interface.poll()

        # 5) log.
        self.logger.record(t_s, {
            "pack_voltage_v": state.pack_voltage_v,
            "pack_current_a": state.current_a,
            "avg_soc": state.avg_soc,
            "min_cell_v": state.min_cell_v,
            "max_cell_v": state.max_cell_v,
            "cell_delta_v": state.cell_delta_v,
            "max_temp_c": state.max_temp_c,
            "isolation_kohm": state.isolation_kohm,
            "soh_pct": state.soh * 100.0,
            "contactor_closed": 1.0 if status.contactor_closed else 0.0,
            "fault_flags": float(status.fault_flags),
        })

    # ---- lifecycle --------------------------------------------------------
    def run_for(self, duration_s: float) -> None:
        self.scheduler.run_for(duration_s)

    def settle(self, duration_s: float = 0.3) -> None:
        """Run briefly so the ECU sees data and closes the contactor."""
        self.run_for(duration_s)

    def shutdown(self) -> None:
        self.tester_bus.shutdown()
        if self.ecu_bus is not None:
            self.ecu_bus.shutdown()

    def reset_channel(self) -> None:
        VirtualCanBus.reset_channel(str(self.config.get("can.channel", "hil0")))
