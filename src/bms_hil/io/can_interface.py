"""CAN transport abstraction.

Two backends are provided behind a common :class:`CanBus` interface:

* :class:`VirtualCanBus` - a pure-Python in-process broadcast bus. It needs no
  hardware or drivers and is what the self-test/CI path uses. Multiple bus
  handles bound to the same channel name share one broadcast domain, so the
  plant side and the ECU side can talk exactly as they would over real CAN.
* :class:`PythonCanBus` - a thin adapter over the ``python-can`` library for
  driving real HIL benches (Vector, PCAN, SocketCAN, etc.). It is only imported
  when selected, so ``python-can`` stays an optional dependency.

Use :func:`create_bus` to construct the backend named in the configuration.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CanFrame:
    """A single classic CAN frame."""

    arbitration_id: int
    data: bytes
    timestamp: float = 0.0
    is_extended_id: bool = False

    def __post_init__(self) -> None:
        if len(self.data) > 8:
            raise ValueError("Classic CAN data length must be <= 8 bytes")
        if not isinstance(self.data, (bytes, bytearray)):
            self.data = bytes(self.data)
        else:
            self.data = bytes(self.data)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"CanFrame(id=0x{self.arbitration_id:03X}, "
            f"data={self.data.hex(' ')}, t={self.timestamp:.3f})"
        )


class CanBus:
    """Abstract CAN bus. Subclasses implement send/recv/shutdown."""

    def send(self, frame: CanFrame) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def recv(self, timeout: Optional[float] = 0.0) -> Optional[CanFrame]:  # pragma: no cover
        raise NotImplementedError

    def shutdown(self) -> None:  # pragma: no cover - interface
        pass

    def __enter__(self) -> "CanBus":
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()


class _Broadcast:
    """Shared broadcast domain for all virtual bus handles on one channel."""

    _registry: Dict[str, "_Broadcast"] = {}
    _registry_lock = threading.Lock()

    def __init__(self) -> None:
        self._subscribers: List["queue.Queue[CanFrame]"] = []
        self._lock = threading.Lock()

    @classmethod
    def get(cls, channel: str) -> "_Broadcast":
        with cls._registry_lock:
            if channel not in cls._registry:
                cls._registry[channel] = _Broadcast()
            return cls._registry[channel]

    @classmethod
    def reset(cls, channel: Optional[str] = None) -> None:
        with cls._registry_lock:
            if channel is None:
                cls._registry.clear()
            else:
                cls._registry.pop(channel, None)

    def subscribe(self) -> "queue.Queue[CanFrame]":
        q: "queue.Queue[CanFrame]" = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[CanFrame]") -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, frame: CanFrame, sender: "queue.Queue[CanFrame]") -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            if q is sender:
                continue  # a node does not receive its own transmissions
            q.put(frame)


class VirtualCanBus(CanBus):
    """In-process broadcast CAN bus. No hardware required."""

    def __init__(self, channel: str = "hil0") -> None:
        self.channel = channel
        self._domain = _Broadcast.get(channel)
        self._rx = self._domain.subscribe()
        self._closed = False

    def send(self, frame: CanFrame) -> None:
        if self._closed:
            raise RuntimeError("send on closed VirtualCanBus")
        self._domain.publish(frame, sender=self._rx)

    def recv(self, timeout: Optional[float] = 0.0) -> Optional[CanFrame]:
        try:
            if timeout and timeout > 0:
                return self._rx.get(timeout=timeout)
            return self._rx.get_nowait()
        except queue.Empty:
            return None

    def shutdown(self) -> None:
        if not self._closed:
            self._domain.unsubscribe(self._rx)
            self._closed = True

    @staticmethod
    def reset_channel(channel: Optional[str] = None) -> None:
        """Drop broadcast state for a channel (used between test runs)."""
        _Broadcast.reset(channel)


class PythonCanBus(CanBus):  # pragma: no cover - requires python-can + hardware
    """Adapter over the optional ``python-can`` library for real benches."""

    def __init__(self, interface: str = "virtual", channel: str = "hil0",
                 bitrate: int = 500000) -> None:
        try:
            import can  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "backend 'python-can' requested but the 'python-can' package "
                "is not installed. Run: pip install python-can"
            ) from exc
        self._can = can
        self._bus = can.Bus(interface=interface, channel=channel, bitrate=bitrate)

    def send(self, frame: CanFrame) -> None:
        msg = self._can.Message(
            arbitration_id=frame.arbitration_id,
            data=frame.data,
            is_extended_id=frame.is_extended_id,
        )
        self._bus.send(msg)

    def recv(self, timeout: Optional[float] = 0.0) -> Optional[CanFrame]:
        msg = self._bus.recv(timeout=timeout or 0.0)
        if msg is None:
            return None
        return CanFrame(
            arbitration_id=msg.arbitration_id,
            data=bytes(msg.data),
            timestamp=getattr(msg, "timestamp", 0.0) or 0.0,
            is_extended_id=bool(getattr(msg, "is_extended_id", False)),
        )

    def shutdown(self) -> None:
        try:
            self._bus.shutdown()
        except Exception:  # noqa: BLE001
            pass


def create_bus(config_can: Dict) -> CanBus:
    """Factory that builds the CAN backend named in the ``can`` config section."""
    backend = str(config_can.get("backend", "virtual")).lower()
    channel = str(config_can.get("channel", "hil0"))
    if backend in ("virtual", "builtin", "inproc"):
        return VirtualCanBus(channel=channel)
    if backend in ("python-can", "python_can", "hardware"):
        return PythonCanBus(
            interface=str(config_can.get("python_can_interface", "virtual")),
            channel=channel,
            bitrate=int(config_can.get("bitrate", 500000)),
        )
    raise ValueError(f"Unknown CAN backend: {backend!r}")
