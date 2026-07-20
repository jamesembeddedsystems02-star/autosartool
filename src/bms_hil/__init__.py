"""bms_hil - Battery Management System (BMS) ECU Hardware-in-the-Loop test tool.

A modular Hardware-in-the-Loop (HIL) test framework for validating Battery
Management System ECUs. It provides:

* A real-time battery-pack plant model (electrical + thermal) that acts as the
  simulated environment the ECU "sees".
* A CAN communication layer (virtual bus built in; optional python-can backend
  for real hardware benches).
* A simulated BMS ECU (device-under-test stand-in) so the whole toolchain runs
  end-to-end with no hardware attached.
* A fault-injection engine (sensor faults, cell faults, bus faults).
* A test framework with scenarios (charge/discharge, protection, balancing,
  contactor control) plus a runner that emits JUnit XML and HTML reports.

The runnable/self-test path depends only on the Python standard library. numpy
and python-can are optional accelerators/hardware backends.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
