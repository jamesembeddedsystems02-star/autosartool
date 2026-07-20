"""Optional DBC-backed signal database using the ``cantools`` library.

Real benches ship a Vector ``.dbc`` describing the ECU's communication matrix.
When a DBC path is configured (``can.dbc_path``) and ``cantools`` is installed,
:func:`load_dbc` returns an adapter that exposes the *same* surface as the
built-in :class:`~bms_hil.io.signal_db.SignalDatabase`
(``encode``/``decode``/``by_name``/``by_id``/``message_for``), so nothing else
in the tool needs to change. Without a DBC configured, the built-in database is
used and ``cantools`` is never imported.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .can_interface import CanFrame
from .signal_db import default_bms_database


class CantoolsDatabase:
    """Adapter that makes a ``cantools`` database quack like a SignalDatabase."""

    def __init__(self, db: Any) -> None:
        self._db = db
        self.by_name: Dict[str, Any] = {m.name: m for m in db.messages}
        self.by_id: Dict[int, Any] = {m.frame_id: m for m in db.messages}

    def encode(self, message_name: str, values: Dict[str, float]) -> CanFrame:
        msg = self._db.get_message_by_name(message_name)
        # cantools requires every signal; fill anything the caller omitted.
        full = {s.name: values.get(s.name, 0) for s in msg.signals}
        data = msg.encode(full, padding=True, strict=False)
        return CanFrame(arbitration_id=msg.frame_id, data=bytes(data))

    def decode(self, frame: CanFrame) -> Dict[str, float]:
        msg = self.by_id.get(frame.arbitration_id)
        if msg is None:
            return {}
        decoded = msg.decode(frame.data, decode_choices=False,
                             allow_truncated=True)
        # Normalise values to plain floats for downstream arithmetic.
        return {k: float(v) for k, v in decoded.items()}

    def message_for(self, frame_id: int) -> Any:
        return self.by_id[frame_id]


def load_dbc(path: str) -> CantoolsDatabase:
    """Load *path* into a :class:`CantoolsDatabase` (requires ``cantools``)."""
    try:
        import cantools  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"can.dbc_path={path!r} was set but the 'cantools' package is not "
            "installed. Run: pip install cantools"
        ) from exc
    db = cantools.database.load_file(path)
    return CantoolsDatabase(db)


def load_signal_database(config) -> Any:
    """Return the configured signal database (DBC if set, else built-in)."""
    dbc_path: Optional[str] = config.get("can.dbc_path")
    if dbc_path:
        return load_dbc(dbc_path)
    return default_bms_database()
