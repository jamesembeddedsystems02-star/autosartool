"""Runs a suite of HIL test cases, each on a fresh bench, and reports results.

Every test gets its own :class:`HilBench` (and therefore a clean plant, ECU and
CAN channel) so tests are independent and order-insensitive.
"""

from __future__ import annotations

import os
from typing import List, Optional

from ..core.bench import HilBench
from ..core.config import Config
from ..core.logging_setup import get_logger
from ..io.can_interface import VirtualCanBus
from ..report.report_generator import write_html_report, write_junit_xml
from .test_case import HilTestCase, TestContext, TestResult

log = get_logger("bms_hil.runner")


class TestRunner:
    __test__ = False  # not a pytest test class

    def __init__(self, config: Config) -> None:
        self.config = config
        self.results: List[TestResult] = []

    def run(self, tests: List[HilTestCase]) -> List[TestResult]:
        self.results = []
        channel = str(self.config.get("can.channel", "hil0"))
        for test in tests:
            # Isolate each test on its own broadcast channel state.
            VirtualCanBus.reset_channel(channel)
            bench = HilBench(self.config)
            ctx = TestContext(bench)
            log.info("RUN  %-32s [%s]", test.name, test.category)
            result = test.execute(ctx)
            level_ok = result.status == "pass"
            log.log(
                20 if level_ok else 30,
                "%-4s %-32s (%.2fs) %s",
                result.status.upper(), test.name, result.duration_s,
                "" if level_ok else "-> " + result.message,
            )
            self.results.append(result)
            bench.shutdown()
            VirtualCanBus.reset_channel(channel)
        return self.results

    # ---- reporting --------------------------------------------------------
    def summary(self) -> dict:
        by_status = {"pass": 0, "fail": 0, "error": 0, "skip": 0}
        for r in self.results:
            by_status[r.status] = by_status.get(r.status, 0) + 1
        by_status["total"] = len(self.results)
        return by_status

    @property
    def passed(self) -> bool:
        return all(r.status == "pass" for r in self.results)

    def write_reports(self, output_dir: Optional[str] = None) -> dict:
        out = output_dir or str(self.config.get("report.output_dir", "reports"))
        os.makedirs(out, exist_ok=True)
        xml = write_junit_xml(self.results, os.path.join(out, "junit.xml"))
        htm = write_html_report(self.results, os.path.join(out, "report.html"))
        return {"junit": xml, "html": htm}
