"""Time-series signal logger with CSV export.

Records named channels each step so scenarios can assert on trajectories and
so measurements can be exported for offline analysis. Kept intentionally simple
(list-of-rows) to avoid a hard pandas/numpy dependency.
"""

from __future__ import annotations

import csv
import os
from typing import Dict, List, Optional


class DataLogger:
    def __init__(self, channels: Optional[List[str]] = None) -> None:
        self._channels: List[str] = list(channels or [])
        self._rows: List[Dict[str, float]] = []

    def record(self, t_s: float, values: Dict[str, float]) -> None:
        row: Dict[str, float] = {"time_s": t_s}
        for k, v in values.items():
            if k not in self._channels:
                self._channels.append(k)
            row[k] = v
        self._rows.append(row)

    @property
    def channels(self) -> List[str]:
        return ["time_s"] + [c for c in self._channels if c != "time_s"]

    @property
    def rows(self) -> List[Dict[str, float]]:
        return self._rows

    def series(self, channel: str) -> List[float]:
        return [r.get(channel, float("nan")) for r in self._rows]

    def max(self, channel: str) -> float:
        vals = [r[channel] for r in self._rows if channel in r]
        return max(vals) if vals else float("nan")

    def min(self, channel: str) -> float:
        vals = [r[channel] for r in self._rows if channel in r]
        return min(vals) if vals else float("nan")

    def last(self, channel: str) -> float:
        for r in reversed(self._rows):
            if channel in r:
                return r[channel]
        return float("nan")

    def to_csv(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        cols = self.channels
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols)
            writer.writeheader()
            for row in self._rows:
                writer.writerow({c: row.get(c, "") for c in cols})

    def clear(self) -> None:
        self._rows.clear()
