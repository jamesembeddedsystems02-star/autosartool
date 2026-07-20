"""Concrete HIL test scenarios and the default suite factory."""

from typing import List

from ..testing.test_case import HilTestCase
from .charge_discharge import ChargeTest, DischargeTest, SocTrackingTest
from .protection import (
    OvervoltageProtectionTest,
    UndervoltageProtectionTest,
    OvertemperatureProtectionTest,
    OvercurrentProtectionTest,
    FaultClearAndRecoverTest,
)
from .cell_balancing import CellBalancingTest
from .contactor import ContactorCloseTest, ContactorOpenOnFaultTest


def default_suite() -> List[HilTestCase]:
    """The standard regression suite for the BMS ECU."""
    return [
        ContactorCloseTest(),
        ChargeTest(),
        DischargeTest(),
        SocTrackingTest(),
        OvervoltageProtectionTest(),
        UndervoltageProtectionTest(),
        OvertemperatureProtectionTest(),
        OvercurrentProtectionTest(),
        CellBalancingTest(),
        ContactorOpenOnFaultTest(),
        FaultClearAndRecoverTest(),
    ]


__all__ = [
    "default_suite",
    "ChargeTest",
    "DischargeTest",
    "SocTrackingTest",
    "OvervoltageProtectionTest",
    "UndervoltageProtectionTest",
    "OvertemperatureProtectionTest",
    "OvercurrentProtectionTest",
    "FaultClearAndRecoverTest",
    "CellBalancingTest",
    "ContactorCloseTest",
    "ContactorOpenOnFaultTest",
]
