"""Test-case base class, execution context, and result record."""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import List

from ..core.bench import HilBench
from ..core.logging_setup import get_logger
from .assertions import AssertionFailed, Check

log = get_logger("bms_hil.test")


@dataclass
class TestResult:
    __test__ = False  # not a pytest test class

    name: str
    status: str = "pass"          # pass | fail | error | skip
    message: str = ""
    duration_s: float = 0.0
    category: str = ""
    log: List[str] = field(default_factory=list)


class TestContext:
    """Handed to each test: the bench plus a fresh assertion recorder."""

    __test__ = False  # not a pytest test class

    def __init__(self, bench: HilBench) -> None:
        self.bench = bench
        self.check = Check()

    # convenient shortcuts
    @property
    def plant(self):
        return self.bench.plant

    @property
    def ecu(self):
        return self.bench.ecu

    @property
    def status(self):
        return self.bench.interface.status

    @property
    def logger(self):
        return self.bench.logger

    def run_for(self, duration_s: float) -> None:
        self.bench.run_for(duration_s)


class HilTestCase:
    """Base class for a HIL test. Subclass and implement :meth:`run`.

    Override :attr:`name`/:attr:`category` and, optionally, :meth:`setup` and
    :meth:`teardown`. :meth:`run` performs stimulus + checks via ``ctx.check``.
    """

    name: str = "unnamed_test"
    category: str = "general"

    def setup(self, ctx: TestContext) -> None:  # noqa: D401
        """Optional per-test setup."""

    def run(self, ctx: TestContext) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def teardown(self, ctx: TestContext) -> None:
        """Optional per-test cleanup."""

    def execute(self, ctx: TestContext) -> TestResult:
        result = TestResult(name=self.name, category=self.category)
        start = time.perf_counter()
        try:
            self.setup(ctx)
            self.run(ctx)
            result.status = "pass" if ctx.check.ok else "fail"
            if not ctx.check.ok:
                result.message = "; ".join(ctx.check.failures)
        except AssertionFailed as exc:
            result.status = "fail"
            result.message = f"precondition failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            result.status = "error"
            result.message = f"{type(exc).__name__}: {exc}"
            ctx.check.log.append("TRACEBACK:\n" + traceback.format_exc())
        finally:
            try:
                self.teardown(ctx)
            except Exception as exc:  # noqa: BLE001
                ctx.check.log.append(f"teardown error: {exc}")
            result.duration_s = time.perf_counter() - start
            result.log = list(ctx.check.log)
        return result
