"""End-to-end scenario tests: run the full suite through the runner."""

import pytest

from bms_hil.core.config import Config
from bms_hil.scenarios import default_suite
from bms_hil.testing.test_runner import TestRunner


@pytest.fixture
def cfg():
    return Config.load()


def test_full_suite_passes(cfg):
    runner = TestRunner(cfg)
    results = runner.run(default_suite())
    failures = [r for r in results if r.status != "pass"]
    assert not failures, "failing scenarios: " + ", ".join(
        f"{r.name}: {r.message}" for r in failures
    )
    assert runner.passed


def test_runner_writes_reports(cfg, tmp_path):
    runner = TestRunner(cfg)
    runner.run(default_suite())
    reports = runner.write_reports(str(tmp_path))
    assert (tmp_path / "junit.xml").exists()
    assert (tmp_path / "report.html").exists()
    assert reports["junit"].endswith("junit.xml")


@pytest.mark.parametrize("name", [t.name for t in default_suite()])
def test_each_scenario_individually(cfg, name):
    test = next(t for t in default_suite() if t.name == name)
    runner = TestRunner(cfg)
    results = runner.run([test])
    assert results[0].status == "pass", results[0].message
