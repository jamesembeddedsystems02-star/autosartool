"""Optional matplotlib plotting of signal traces for the HTML report.

matplotlib is an optional dependency. Every function degrades gracefully to
``None`` when it is not installed, so reports still generate (just without the
embedded plot). A non-interactive backend is forced so plotting works headless
(CI, servers).
"""

from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover
    from .data_logger import DataLogger

try:
    import matplotlib  # type: ignore

    matplotlib.use("Agg")  # headless backend
    import matplotlib.pyplot as plt  # type: ignore

    _HAVE_MPL = True
except Exception:  # pragma: no cover - exercised only without matplotlib
    _HAVE_MPL = False


def have_matplotlib() -> bool:
    return _HAVE_MPL


def _figure_from_logger(logger: "DataLogger"):
    t = logger.series("time_s")
    fig, axes = plt.subplots(4, 1, figsize=(9, 9), sharex=True)

    ax = axes[0]
    ax.plot(t, logger.series("pack_voltage_v"), color="#1565c0", label="pack V")
    ax.set_ylabel("Pack voltage (V)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)

    ax = axes[1]
    ax.plot(t, logger.series("min_cell_v"), color="#2e7d32", label="min cell")
    ax.plot(t, logger.series("max_cell_v"), color="#c62828", label="max cell")
    ax.set_ylabel("Cell voltage (V)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)

    ax = axes[2]
    ax.plot(t, logger.series("pack_current_a"), color="#ef6c00", label="current")
    ax.axhline(0, color="#999", lw=0.6)
    ax.set_ylabel("Current (A)\n(+dischg / -chg)")
    ax.grid(True, alpha=0.3)

    ax = axes[3]
    ax.plot(t, logger.series("max_temp_c"), color="#6a1b9a", label="max temp")
    ax.set_ylabel("Max temp (°C)")
    ax.set_xlabel("Time (s)")
    ax.grid(True, alpha=0.3)

    fig.suptitle("BMS HIL signal trace", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    return fig


def plot_logger_png(logger: "DataLogger", path: str) -> Optional[str]:
    """Write a PNG plot of the trace to *path*. Returns path or None."""
    if not _HAVE_MPL or not logger.rows:
        return None
    fig = _figure_from_logger(logger)
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def plot_logger_datauri(logger: "DataLogger") -> Optional[str]:
    """Return a ``data:image/png;base64,...`` URI for the trace, or None."""
    if not _HAVE_MPL or not logger.rows:
        return None
    fig = _figure_from_logger(logger)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
