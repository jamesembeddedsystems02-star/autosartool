"""DBC signal-database tests. Skipped entirely when cantools is unavailable."""

import os

import pytest

cantools = pytest.importorskip("cantools")

from bms_hil.core.config import Config
from bms_hil.io.dbc import load_dbc, load_signal_database
from bms_hil.scenarios import default_suite
from bms_hil.testing.test_runner import TestRunner

DBC_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config", "bms.dbc")


@pytest.fixture
def db():
    return load_dbc(DBC_PATH)


def test_dbc_has_expected_messages(db):
    for name in ["BMS_PackStatus", "BMS_LimitsStatus", "BMS_SohStatus",
                 "SIM_CellVoltages", "SIM_IsolationStatus", "TESTER_Command"]:
        assert name in db.by_name


def test_dbc_roundtrip_pack_status(db):
    frame = db.encode("BMS_PackStatus", {
        "PackVoltage": 48.6, "PackCurrent": 12.5, "PackSOC": 55.0,
        "PackMode": 2, "Counter": 7, "Checksum": 9,
    })
    decoded = db.decode(frame)
    assert abs(decoded["PackVoltage"] - 48.6) < 0.1
    assert abs(decoded["PackCurrent"] - 12.5) < 0.1
    assert abs(decoded["PackSOC"] - 55.0) < 0.5


def test_dbc_signed_current_via_offset(db):
    frame = db.encode("TESTER_Command", {"RequestedCurrent": -40.0, "Command": 1})
    assert abs(db.decode(frame)["RequestedCurrent"] - (-40.0)) < 0.1


def test_config_selects_builtin_without_dbc_path():
    db = load_signal_database(Config.load())
    # built-in database exposes the same messages
    assert "BMS_PackStatus" in db.by_name


def test_full_suite_passes_on_dbc_backend():
    cfg = Config.load(overrides={"can": {"dbc_path": DBC_PATH}})
    runner = TestRunner(cfg)
    runner.run(default_suite())
    assert runner.passed, runner.summary()
