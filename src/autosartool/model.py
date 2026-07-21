"""AUTOSAR configuration data model.

This module defines a pragmatic, tool-friendly object model covering the two
domains a configuration tool such as DaVinci Developer Adaptive / EB corbos
Studio / ISOLAR-A works with:

* **Adaptive Platform** artifacts: service interfaces, adaptive application
  software components with ports, executables, processes and machines.
* **Basic Software / platform modules**: a generic EcuC-style container and
  parameter model (as used by Classic AUTOSAR BSW configuration and by the
  Adaptive functional-cluster manifests).

The model is intentionally serialization-agnostic. Every element can be
converted to/from plain dictionaries (``to_dict`` / ``from_dict``) so a project
can be persisted as JSON, while :mod:`autosartool.arxml` renders the same model
to AUTOSAR ARXML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class PortDirection(str, Enum):
    """Direction of a port prototype on a software component."""

    PROVIDED = "PROVIDED"
    REQUIRED = "REQUIRED"


class ArgDirection(str, Enum):
    """Direction of a service method argument."""

    IN = "IN"
    OUT = "OUT"
    INOUT = "INOUT"


class PrimitiveType(str, Enum):
    """AUTOSAR primitive implementation data types (CppImplementationDataType)."""

    BOOLEAN = "boolean"
    UINT8 = "uint8"
    UINT16 = "uint16"
    UINT32 = "uint32"
    UINT64 = "uint64"
    SINT8 = "sint8"
    SINT16 = "sint16"
    SINT32 = "sint32"
    SINT64 = "sint64"
    FLOAT32 = "float"
    FLOAT64 = "double"
    STRING = "string"


class TransportBinding(str, Enum):
    """Network binding for a service instance (ara::com transport)."""

    SOMEIP = "SOMEIP"
    DDS = "DDS"
    IPC = "IPC"  # intra-machine (shared memory / unix domain)


class ParamType(str, Enum):
    """EcuC parameter value types for Basic Software module configuration."""

    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    BOOLEAN = "BOOLEAN"
    STRING = "STRING"
    ENUM = "ENUM"
    REFERENCE = "REFERENCE"


# The Adaptive Platform functional clusters that behave like "basic software".
FUNCTIONAL_CLUSTERS = [
    "EM",  # Execution Management
    "SM",  # State Management
    "CM",  # Communication Management
    "DM",  # Diagnostic Management
    "PER",  # Persistency
    "TS",  # Time Synchronization
    "NM",  # Network Management
    "CRYPTO",  # Cryptography
    "IAM",  # Identity and Access Management
    "LOG",  # Logging and Tracing
    "UCM",  # Update and Configuration Management
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def is_valid_identifier(name: str) -> bool:
    """Return True if *name* is a valid AUTOSAR short-name identifier."""
    return bool(name) and bool(_IDENT_RE.match(name)) and len(name) <= 128


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


# --------------------------------------------------------------------------- #
# Service interface (ara::com)
# --------------------------------------------------------------------------- #
@dataclass
class Argument:
    """A single argument of a service method."""

    name: str
    type: str  # primitive name or reference to a data type short-name
    direction: ArgDirection = ArgDirection.IN

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type, "direction": _enum_value(self.direction)}

    @classmethod
    def from_dict(cls, d: dict) -> "Argument":
        return cls(name=d["name"], type=d["type"], direction=ArgDirection(d.get("direction", "IN")))


@dataclass
class Method:
    """A callable operation of a service interface."""

    name: str
    arguments: list[Argument] = field(default_factory=list)
    fire_and_forget: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fire_and_forget": self.fire_and_forget,
            "arguments": [a.to_dict() for a in self.arguments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Method":
        return cls(
            name=d["name"],
            fire_and_forget=d.get("fire_and_forget", False),
            arguments=[Argument.from_dict(a) for a in d.get("arguments", [])],
        )


@dataclass
class Event:
    """A one-way notification published by a service interface."""

    name: str
    type: str

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type}

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(name=d["name"], type=d["type"])


@dataclass
class Field:
    """A field (getter/setter/notifier) of a service interface."""

    name: str
    type: str
    has_getter: bool = True
    has_setter: bool = True
    has_notifier: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "has_getter": self.has_getter,
            "has_setter": self.has_setter,
            "has_notifier": self.has_notifier,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Field":
        return cls(
            name=d["name"],
            type=d["type"],
            has_getter=d.get("has_getter", True),
            has_setter=d.get("has_setter", True),
            has_notifier=d.get("has_notifier", True),
        )


@dataclass
class ServiceInterface:
    """An ara::com service interface definition."""

    name: str
    namespace: str = "ara"
    methods: list[Method] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    fields: list[Field] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "methods": [m.to_dict() for m in self.methods],
            "events": [e.to_dict() for e in self.events],
            "fields": [f.to_dict() for f in self.fields],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ServiceInterface":
        return cls(
            name=d["name"],
            namespace=d.get("namespace", "ara"),
            methods=[Method.from_dict(m) for m in d.get("methods", [])],
            events=[Event.from_dict(e) for e in d.get("events", [])],
            fields=[Field.from_dict(f) for f in d.get("fields", [])],
        )


# --------------------------------------------------------------------------- #
# Adaptive application software component
# --------------------------------------------------------------------------- #
@dataclass
class PortPrototype:
    """A provided or required port on an adaptive application component."""

    name: str
    direction: PortDirection
    interface: str  # short-name of a ServiceInterface

    def to_dict(self) -> dict:
        return {"name": self.name, "direction": _enum_value(self.direction), "interface": self.interface}

    @classmethod
    def from_dict(cls, d: dict) -> "PortPrototype":
        return cls(name=d["name"], direction=PortDirection(d["direction"]), interface=d["interface"])


@dataclass
class AdaptiveApplication:
    """An adaptive application software component type."""

    name: str
    ports: list[PortPrototype] = field(default_factory=list)
    description: str = ""

    def provided_ports(self) -> list[PortPrototype]:
        return [p for p in self.ports if p.direction == PortDirection.PROVIDED]

    def required_ports(self) -> list[PortPrototype]:
        return [p for p in self.ports if p.direction == PortDirection.REQUIRED]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "ports": [p.to_dict() for p in self.ports],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AdaptiveApplication":
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            ports=[PortPrototype.from_dict(p) for p in d.get("ports", [])],
        )


@dataclass
class Executable:
    """A deployable binary built from a root adaptive application component."""

    name: str
    root_component: str  # short-name of an AdaptiveApplication
    version: str = "1.0.0"

    def to_dict(self) -> dict:
        return {"name": self.name, "root_component": self.root_component, "version": self.version}

    @classmethod
    def from_dict(cls, d: dict) -> "Executable":
        return cls(name=d["name"], root_component=d["root_component"], version=d.get("version", "1.0.0"))


@dataclass
class Process:
    """A runtime instance of an executable with EM scheduling configuration."""

    name: str
    executable: str  # short-name of an Executable
    scheduling_policy: str = "SCHED_FIFO"  # SCHED_FIFO | SCHED_RR | SCHED_OTHER
    priority: int = 50
    core_affinity: list[int] = field(default_factory=list)
    startup_states: list[str] = field(default_factory=lambda: ["Running"])

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "executable": self.executable,
            "scheduling_policy": self.scheduling_policy,
            "priority": self.priority,
            "core_affinity": list(self.core_affinity),
            "startup_states": list(self.startup_states),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Process":
        return cls(
            name=d["name"],
            executable=d["executable"],
            scheduling_policy=d.get("scheduling_policy", "SCHED_FIFO"),
            priority=d.get("priority", 50),
            core_affinity=list(d.get("core_affinity", [])),
            startup_states=list(d.get("startup_states", ["Running"])),
        )


@dataclass
class Machine:
    """An Adaptive machine (ECU) with machine states and enabled clusters."""

    name: str
    machine_states: list[str] = field(default_factory=lambda: ["Startup", "Running", "Shutdown"])
    functional_clusters: list[str] = field(default_factory=lambda: ["EM", "SM", "CM"])

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "machine_states": list(self.machine_states),
            "functional_clusters": list(self.functional_clusters),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Machine":
        return cls(
            name=d["name"],
            machine_states=list(d.get("machine_states", ["Startup", "Running", "Shutdown"])),
            functional_clusters=list(d.get("functional_clusters", ["EM", "SM", "CM"])),
        )


@dataclass
class ServiceInstance:
    """Maps a provided/required port to a concrete transport binding.

    This is the equivalent of a SOME/IP or DDS service-instance manifest entry.
    """

    name: str
    service_interface: str  # short-name of a ServiceInterface
    instance_id: int
    binding: TransportBinding = TransportBinding.SOMEIP
    role: PortDirection = PortDirection.PROVIDED
    udp_port: int | None = None
    tcp_port: int | None = None
    service_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "service_interface": self.service_interface,
            "instance_id": self.instance_id,
            "binding": _enum_value(self.binding),
            "role": _enum_value(self.role),
            "udp_port": self.udp_port,
            "tcp_port": self.tcp_port,
            "service_id": self.service_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ServiceInstance":
        return cls(
            name=d["name"],
            service_interface=d["service_interface"],
            instance_id=d["instance_id"],
            binding=TransportBinding(d.get("binding", "SOMEIP")),
            role=PortDirection(d.get("role", "PROVIDED")),
            udp_port=d.get("udp_port"),
            tcp_port=d.get("tcp_port"),
            service_id=d.get("service_id"),
        )


# --------------------------------------------------------------------------- #
# Basic Software module configuration (generic EcuC container/parameter model)
# --------------------------------------------------------------------------- #
@dataclass
class Parameter:
    """A single configuration parameter inside a BSW container."""

    name: str
    type: ParamType
    value: Any = None

    def to_dict(self) -> dict:
        return {"name": self.name, "type": _enum_value(self.type), "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> "Parameter":
        return cls(name=d["name"], type=ParamType(d["type"]), value=d.get("value"))


@dataclass
class Container:
    """An EcuC configuration container holding parameters and sub-containers."""

    name: str
    parameters: list[Parameter] = field(default_factory=list)
    sub_containers: list["Container"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "parameters": [p.to_dict() for p in self.parameters],
            "sub_containers": [c.to_dict() for c in self.sub_containers],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Container":
        return cls(
            name=d["name"],
            parameters=[Parameter.from_dict(p) for p in d.get("parameters", [])],
            sub_containers=[Container.from_dict(c) for c in d.get("sub_containers", [])],
        )


@dataclass
class BswModule:
    """A Basic Software / platform module configuration.

    Examples of ``name``: ``Os``, ``Com``, ``PduR``, ``CanIf``, ``Dcm``,
    ``NvM`` (Classic BSW) or ``EM``, ``SM``, ``CM`` (Adaptive functional
    clusters).
    """

    name: str
    vendor: str = "OpenAUTOSAR"
    containers: list[Container] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "vendor": self.vendor,
            "description": self.description,
            "containers": [c.to_dict() for c in self.containers],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BswModule":
        return cls(
            name=d["name"],
            vendor=d.get("vendor", "OpenAUTOSAR"),
            description=d.get("description", ""),
            containers=[Container.from_dict(c) for c in d.get("containers", [])],
        )


# --------------------------------------------------------------------------- #
# Project (root)
# --------------------------------------------------------------------------- #
PROJECT_FORMAT_VERSION = 1


@dataclass
class Project:
    """The root configuration model persisted as an ``.autosarproj`` JSON file."""

    name: str
    package: str = "MyProject"
    autosar_release: str = "R23-11"
    service_interfaces: list[ServiceInterface] = field(default_factory=list)
    applications: list[AdaptiveApplication] = field(default_factory=list)
    executables: list[Executable] = field(default_factory=list)
    processes: list[Process] = field(default_factory=list)
    machines: list[Machine] = field(default_factory=list)
    service_instances: list[ServiceInstance] = field(default_factory=list)
    bsw_modules: list[BswModule] = field(default_factory=list)

    # -- lookups -----------------------------------------------------------
    def find_service_interface(self, name: str) -> ServiceInterface | None:
        return next((s for s in self.service_interfaces if s.name == name), None)

    def find_application(self, name: str) -> AdaptiveApplication | None:
        return next((a for a in self.applications if a.name == name), None)

    def find_executable(self, name: str) -> Executable | None:
        return next((e for e in self.executables if e.name == name), None)

    # -- serialization -----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format_version": PROJECT_FORMAT_VERSION,
            "name": self.name,
            "package": self.package,
            "autosar_release": self.autosar_release,
            "service_interfaces": [s.to_dict() for s in self.service_interfaces],
            "applications": [a.to_dict() for a in self.applications],
            "executables": [e.to_dict() for e in self.executables],
            "processes": [p.to_dict() for p in self.processes],
            "machines": [m.to_dict() for m in self.machines],
            "service_instances": [si.to_dict() for si in self.service_instances],
            "bsw_modules": [b.to_dict() for b in self.bsw_modules],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        return cls(
            name=d["name"],
            package=d.get("package", "MyProject"),
            autosar_release=d.get("autosar_release", "R23-11"),
            service_interfaces=[ServiceInterface.from_dict(s) for s in d.get("service_interfaces", [])],
            applications=[AdaptiveApplication.from_dict(a) for a in d.get("applications", [])],
            executables=[Executable.from_dict(e) for e in d.get("executables", [])],
            processes=[Process.from_dict(p) for p in d.get("processes", [])],
            machines=[Machine.from_dict(m) for m in d.get("machines", [])],
            service_instances=[ServiceInstance.from_dict(si) for si in d.get("service_instances", [])],
            bsw_modules=[BswModule.from_dict(b) for b in d.get("bsw_modules", [])],
        )
