"""Report generation + optional plotting tests."""

import pytest

from bms_hil.core.bench import HilBench
from bms_hil.core.config import Config
from bms_hil.io.can_interface import VirtualCanBus
from bms_hil.report import plots
from bms_hil.report.data_logger import DataLogger
from bms_hil.report.report_generator import write_html_report


def _trace_logger() -> DataLogger:
    VirtualCanBus.reset_channel("hil0")
    bench = HilBench(Config.load())
    try:
        bench.settle(0.3)
        bench.command_current(40.0, mode=2)
        bench.run_for(2.0)
        return bench.logger
    finally:
        bench.shutdown()
        VirtualCanBus.reset_channel("hil0")


def test_html_report_without_plot(tmp_path):
    path = write_html_report([], str(tmp_path / "r.html"))
    assert (tmp_path / "r.html").exists()
    html = open(path, encoding="utf-8").read()
    assert "BMS HIL Test Report" in html


def test_plot_datauri_when_matplotlib_available():
    pytest.importorskip("matplotlib")
    logger = _trace_logger()
    uri = plots.plot_logger_datauri(logger)
    assert uri is not None and uri.startswith("data:image/png;base64,")


def test_plot_png_written(tmp_path):
    pytest.importorskip("matplotlib")
    logger = _trace_logger()
    out = plots.plot_logger_png(logger, str(tmp_path / "trace.png"))
    assert out is not None and (tmp_path / "trace.png").exists()


def test_html_report_embeds_trace(tmp_path):
    pytest.importorskip("matplotlib")
    logger = _trace_logger()
    uri = plots.plot_logger_datauri(logger)
    path = write_html_report([], str(tmp_path / "r.html"), trace_datauri=uri)
    html = open(path, encoding="utf-8").read()
    assert "data:image/png;base64," in html


def test_plot_returns_none_on_empty_logger():
    empty = DataLogger()
    # No rows -> no plot regardless of matplotlib availability.
    assert plots.plot_logger_datauri(empty) is None
