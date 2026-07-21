"""autosartool — an open Adaptive AUTOSAR configuration tool.

Configure Adaptive Platform application software components and Basic Software /
platform modules, edit and validate AUTOSAR ARXML, and generate ``ara::com``
C++ skeletons — in the spirit of DaVinci Developer Adaptive, EB corbos Studio
and ISOLAR-A, but dependency-free and scriptable.
"""

from __future__ import annotations

from .model import (
    AdaptiveApplication,
    Argument,
    ArgDirection,
    BswModule,
    Container,
    Event,
    Executable,
    Field,
    Machine,
    Method,
    Parameter,
    ParamType,
    PortDirection,
    PortPrototype,
    PrimitiveType,
    Process,
    Project,
    ServiceInstance,
    ServiceInterface,
    TransportBinding,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AdaptiveApplication",
    "Argument",
    "ArgDirection",
    "BswModule",
    "Container",
    "Event",
    "Executable",
    "Field",
    "Machine",
    "Method",
    "Parameter",
    "ParamType",
    "PortDirection",
    "PortPrototype",
    "PrimitiveType",
    "Process",
    "Project",
    "ServiceInstance",
    "ServiceInterface",
    "TransportBinding",
]
