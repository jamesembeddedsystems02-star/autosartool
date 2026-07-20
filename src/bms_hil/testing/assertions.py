"""Assertion helpers that record pass/fail steps instead of raising by default.

:class:`Check` accumulates named verification steps into a test's log. Each
check returns a bool so a scenario can branch, and the aggregate pass/fail is
available via :attr:`Check.ok`. Use :meth:`Check.require` for hard
preconditions that should abort the test via :class:`AssertionFailed`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


class AssertionFailed(Exception):
    """Raised by :meth:`Check.require` for unrecoverable preconditions."""


@dataclass
class Check:
    log: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def _record(self, passed: bool, desc: str) -> bool:
        mark = "PASS" if passed else "FAIL"
        self.log.append(f"[{mark}] {desc}")
        if not passed:
            self.failures.append(desc)
        return passed

    def that(self, condition: bool, desc: str) -> bool:
        return self._record(bool(condition), desc)

    def equal(self, actual, expected, desc: str) -> bool:
        return self._record(actual == expected, f"{desc} (got {actual!r}, want {expected!r})")

    def true(self, value: bool, desc: str) -> bool:
        return self._record(bool(value), desc)

    def false(self, value: bool, desc: str) -> bool:
        return self._record(not value, desc)

    def close(self, actual: float, expected: float, tol: float, desc: str) -> bool:
        passed = abs(actual - expected) <= tol
        return self._record(passed, f"{desc} (got {actual:.4g}, want {expected:.4g} +/- {tol:g})")

    def greater(self, actual: float, threshold: float, desc: str) -> bool:
        return self._record(actual > threshold, f"{desc} (got {actual:.4g} > {threshold:.4g})")

    def less(self, actual: float, threshold: float, desc: str) -> bool:
        return self._record(actual < threshold, f"{desc} (got {actual:.4g} < {threshold:.4g})")

    def in_range(self, actual: float, lo: float, hi: float, desc: str) -> bool:
        return self._record(lo <= actual <= hi,
                            f"{desc} (got {actual:.4g} in [{lo:.4g}, {hi:.4g}])")

    def require(self, condition: bool, desc: str) -> None:
        if not self._record(bool(condition), "REQUIRE " + desc):
            raise AssertionFailed(desc)
