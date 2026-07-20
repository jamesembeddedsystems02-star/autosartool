"""Concrete HIL test scenarios and the default suite factory."""

from typing import List

from ..testing.test_case import HilTestCase
from .advanced_protection import (
    IsolationMonitoringTest,
    PrechargeSequenceTest,
    SohReportingTest,
    ThermalRunawayTest,
)
from .cell_balancing import CellBalancingTest
from .charge_discharge import ChargeTest, DischargeTest, SocTrackingTest
from .contactor import ContactorCloseTest, ContactorOpenOnFaultTest
from .drive_cycle import DriveCycle, DriveCycleReplayTest
from .protection import (
    FaultClearAndRecoverTest,
    OvercurrentProtectionTest,
    OvertemperatureProtectionTest,
    OvervoltageProtectionTest,
    UndervoltageProtectionTest,
)


def default_suite() -> List[HilTestCase]:
    """The standard regression suite for the BMS ECU."""
    return [
        ContactorCloseTest(),
        PrechargeSequenceTest(),
        ChargeTest(),
        DischargeTest(),
        SocTrackingTest(),
        DriveCycleReplayTest(),
        OvervoltageProtectionTest(),
        UndervoltageProtectionTest(),
        OvertemperatureProtectionTest(),
        OvercurrentProtectionTest(),
        ThermalRunawayTest(),
        IsolationMonitoringTest(),
        CellBalancingTest(),
        SohReportingTest(),
        ContactorOpenOnFaultTest(),
        FaultClearAndRecoverTest(),
    ]


__all__ = [
    "default_suite",
    "ChargeTest",
    "DischargeTest",
    "SocTrackingTest",
    "DriveCycle",
    "DriveCycleReplayTest",
    "OvervoltageProtectionTest",
    "UndervoltageProtectionTest",
    "OvertemperatureProtectionTest",
    "OvercurrentProtectionTest",
    "FaultClearAndRecoverTest",
    "CellBalancingTest",
    "ContactorCloseTest",
    "ContactorOpenOnFaultTest",
    "PrechargeSequenceTest",
    "ThermalRunawayTest",
    "IsolationMonitoringTest",
    "SohReportingTest",
]
