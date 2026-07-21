"""Model validation for :mod:`autosartool`.

Runs a set of consistency and correctness rules over a
:class:`~autosartool.model.Project` and returns structured findings, mirroring
the "validate before generate" step of commercial AUTOSAR tooling.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum

from .model import (
    FUNCTIONAL_CLUSTERS,
    PortDirection,
    PrimitiveType,
    Project,
    is_valid_identifier,
)


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Finding:
    """A single validation result."""

    severity: Severity
    rule: str
    element: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.severity.value}] {self.rule} ({self.element}): {self.message}"


class ValidationReport:
    """Collection of findings with convenience accessors."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def add(self, severity: Severity, rule: str, element: str, message: str) -> None:
        self.findings.append(Finding(severity, rule, element, message))

    def error(self, rule: str, element: str, message: str) -> None:
        self.add(Severity.ERROR, rule, element, message)

    def warning(self, rule: str, element: str, message: str) -> None:
        self.add(Severity.WARNING, rule, element, message)

    def info(self, rule: str, element: str, message: str) -> None:
        self.add(Severity.INFO, rule, element, message)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [
                {"severity": f.severity.value, "rule": f.rule, "element": f.element, "message": f.message}
                for f in self.findings
            ],
        }


_PRIMITIVES = {p.value for p in PrimitiveType}


def _known_types(project: Project) -> set[str]:
    """All type names usable in a TYPE-TREF: primitives + declared interfaces."""
    types = set(_PRIMITIVES)
    # Interfaces are not data types, but tools often reference user structs by
    # short-name; accept any declared service-interface name plus primitives.
    return types


def _check_unique(report: ValidationReport, rule: str, names: list[str], kind: str) -> None:
    for name, count in Counter(names).items():
        if count > 1:
            report.error(rule, name, f"Duplicate {kind} short-name '{name}' ({count} definitions)")


def _check_identifier(report: ValidationReport, element: str, name: str) -> None:
    if not is_valid_identifier(name):
        report.error(
            "NAMING-001",
            element,
            f"'{name}' is not a valid AUTOSAR short-name "
            "(must start with a letter, contain only [A-Za-z0-9_], max 128 chars)",
        )


def validate(project: Project) -> ValidationReport:
    """Validate *project* and return a :class:`ValidationReport`."""
    report = ValidationReport()

    _validate_project(project, report)
    _validate_interfaces(project, report)
    _validate_applications(project, report)
    _validate_executables(project, report)
    _validate_processes(project, report)
    _validate_service_instances(project, report)
    _validate_machines(project, report)
    _validate_bsw(project, report)

    return report


def _validate_project(project: Project, report: ValidationReport) -> None:
    if not project.name:
        report.error("PROJ-001", "<project>", "Project must have a name")
    _check_identifier(report, "<project.package>", project.package)


def _validate_interfaces(project: Project, report: ValidationReport) -> None:
    _check_unique(report, "IFACE-001", [s.name for s in project.service_interfaces], "service interface")
    known_types = _known_types(project)
    for si in project.service_interfaces:
        _check_identifier(report, f"ServiceInterface {si.name}", si.name)
        if not (si.methods or si.events or si.fields):
            report.warning(
                "IFACE-002", si.name, "Service interface has no methods, events or fields (empty contract)"
            )
        member_names = (
            [m.name for m in si.methods] + [e.name for e in si.events] + [f.name for f in si.fields]
        )
        _check_unique(report, "IFACE-003", member_names, f"member of interface {si.name}")
        for m in si.methods:
            _check_identifier(report, f"{si.name}.{m.name}", m.name)
            for a in m.arguments:
                _check_identifier(report, f"{si.name}.{m.name}.{a.name}", a.name)
                if a.type not in known_types and project.find_service_interface(a.type) is None:
                    report.warning(
                        "TYPE-001",
                        f"{si.name}.{m.name}.{a.name}",
                        f"Argument type '{a.type}' is not a known primitive or declared type",
                    )
        for e in si.events:
            _check_identifier(report, f"{si.name}.{e.name}", e.name)
            if e.type not in known_types and project.find_service_interface(e.type) is None:
                report.warning(
                    "TYPE-001", f"{si.name}.{e.name}", f"Event type '{e.type}' is not a known type"
                )
        for f in si.fields:
            _check_identifier(report, f"{si.name}.{f.name}", f.name)
            if not (f.has_getter or f.has_setter or f.has_notifier):
                report.error(
                    "IFACE-004",
                    f"{si.name}.{f.name}",
                    "Field must expose at least one of getter/setter/notifier",
                )


def _validate_applications(project: Project, report: ValidationReport) -> None:
    _check_unique(report, "APP-001", [a.name for a in project.applications], "application")
    iface_names = {s.name for s in project.service_interfaces}
    for app in project.applications:
        _check_identifier(report, f"Application {app.name}", app.name)
        _check_unique(report, "APP-002", [p.name for p in app.ports], f"port on {app.name}")
        for p in app.ports:
            _check_identifier(report, f"{app.name}.{p.name}", p.name)
            if p.interface not in iface_names:
                report.error(
                    "REF-001",
                    f"{app.name}.{p.name}",
                    f"Port references undefined service interface '{p.interface}'",
                )
        if not app.ports:
            report.warning("APP-003", app.name, "Application component has no ports")


def _validate_executables(project: Project, report: ValidationReport) -> None:
    _check_unique(report, "EXE-001", [e.name for e in project.executables], "executable")
    app_names = {a.name for a in project.applications}
    for ex in project.executables:
        _check_identifier(report, f"Executable {ex.name}", ex.name)
        if ex.root_component not in app_names:
            report.error(
                "REF-002",
                ex.name,
                f"Executable references undefined root component '{ex.root_component}'",
            )


def _validate_processes(project: Project, report: ValidationReport) -> None:
    _check_unique(report, "PROC-001", [p.name for p in project.processes], "process")
    exe_names = {e.name for e in project.executables}
    valid_policies = {"SCHED_FIFO", "SCHED_RR", "SCHED_OTHER"}
    for proc in project.processes:
        _check_identifier(report, f"Process {proc.name}", proc.name)
        if proc.executable not in exe_names:
            report.error(
                "REF-003", proc.name, f"Process references undefined executable '{proc.executable}'"
            )
        if proc.scheduling_policy not in valid_policies:
            report.error(
                "PROC-002",
                proc.name,
                f"Invalid scheduling policy '{proc.scheduling_policy}' (expected one of {sorted(valid_policies)})",
            )
        if proc.scheduling_policy in {"SCHED_FIFO", "SCHED_RR"} and not (1 <= proc.priority <= 99):
            report.error(
                "PROC-003",
                proc.name,
                f"Real-time priority {proc.priority} out of range 1..99 for {proc.scheduling_policy}",
            )
        for core in proc.core_affinity:
            if core < 0:
                report.error("PROC-004", proc.name, f"Negative core id {core} in core affinity")


def _validate_service_instances(project: Project, report: ValidationReport) -> None:
    _check_unique(report, "SI-001", [s.name for s in project.service_instances], "service instance")
    iface_names = {s.name for s in project.service_interfaces}
    # SOME/IP instance identity must be unique per (service_id, instance_id).
    someip_ids: list[tuple] = []
    for si in project.service_instances:
        _check_identifier(report, f"ServiceInstance {si.name}", si.name)
        if si.service_interface not in iface_names:
            report.error(
                "REF-004",
                si.name,
                f"Service instance references undefined interface '{si.service_interface}'",
            )
        if not (0 <= si.instance_id <= 0xFFFF):
            report.error("SI-002", si.name, f"instance_id {si.instance_id} out of 16-bit range")
        if si.binding.value == "SOMEIP":
            if si.service_id is None:
                report.warning("SI-003", si.name, "SOME/IP service instance has no service_id assigned")
            else:
                someip_ids.append((si.service_id, si.instance_id))
            if si.role == PortDirection.PROVIDED and si.udp_port is None and si.tcp_port is None:
                report.warning(
                    "SI-004", si.name, "Provided SOME/IP instance has neither UDP nor TCP port set"
                )
            for port in (si.udp_port, si.tcp_port):
                if port is not None and not (1 <= port <= 65535):
                    report.error("SI-005", si.name, f"Port {port} out of range 1..65535")
    for pair, count in Counter(someip_ids).items():
        if count > 1:
            report.error(
                "SI-006",
                f"service_id={pair[0]},instance_id={pair[1]}",
                f"Duplicate SOME/IP (service_id, instance_id) pair used by {count} instances",
            )


def _validate_machines(project: Project, report: ValidationReport) -> None:
    _check_unique(report, "MACH-001", [m.name for m in project.machines], "machine")
    for m in project.machines:
        _check_identifier(report, f"Machine {m.name}", m.name)
        for fc in m.functional_clusters:
            if fc not in FUNCTIONAL_CLUSTERS:
                report.warning(
                    "MACH-002",
                    m.name,
                    f"Unknown functional cluster '{fc}' (known: {', '.join(FUNCTIONAL_CLUSTERS)})",
                )
        if "EM" not in m.functional_clusters:
            report.warning(
                "MACH-003", m.name, "Machine has no Execution Management (EM) cluster; nothing can start"
            )


def _validate_bsw(project: Project, report: ValidationReport) -> None:
    _check_unique(report, "BSW-001", [b.name for b in project.bsw_modules], "BSW module")
    for mod in project.bsw_modules:
        _check_identifier(report, f"BswModule {mod.name}", mod.name)
        _validate_containers(mod.name, mod.containers, report)


def _validate_containers(scope: str, containers, report: ValidationReport) -> None:
    _check_unique(report, "BSW-002", [c.name for c in containers], f"container in {scope}")
    for c in containers:
        _check_identifier(report, f"{scope}/{c.name}", c.name)
        for p in c.parameters:
            _check_identifier(report, f"{scope}/{c.name}.{p.name}", p.name)
        _validate_containers(f"{scope}/{c.name}", c.sub_containers, report)
