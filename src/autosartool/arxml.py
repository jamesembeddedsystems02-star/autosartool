"""ARXML export and import for the :mod:`autosartool` model.

Renders a :class:`~autosartool.model.Project` into AUTOSAR ARXML using only the
Python standard library (``xml.etree.ElementTree``) and parses a subset of
ARXML back into the model. The output validates against the AUTOSAR
``AUTOSAR_00051`` schema family structurally (AR-PACKAGES / ELEMENTS / typed
element blocks); it is intended for round-tripping this tool's own model rather
than importing arbitrary third-party ARXML.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom import minidom

from .model import (
    AdaptiveApplication,
    Argument,
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
    Process,
    Project,
    ServiceInstance,
    ServiceInterface,
    TransportBinding,
)

AUTOSAR_NS = "http://autosar.org/schema/r4.0"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = "http://autosar.org/schema/r4.0 AUTOSAR_00051.xsd"

_NS = {"ar": AUTOSAR_NS}


# --------------------------------------------------------------------------- #
# Small element helpers
# --------------------------------------------------------------------------- #
def _el(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    e = ET.SubElement(parent, f"{{{AUTOSAR_NS}}}{tag}")
    if text is not None:
        e.text = str(text)
    for k, v in attrs.items():
        e.set(k, v)
    return e


def _short_name(parent: ET.Element, name: str) -> None:
    _el(parent, "SHORT-NAME", name)


def _ref(parent: ET.Element, tag: str, dest: str, path: str) -> ET.Element:
    return _el(parent, tag, path, **{"DEST": dest})


def _find(el: ET.Element, path: str) -> ET.Element | None:
    return el.find(path, _NS)


def _findall(el: ET.Element, path: str) -> list[ET.Element]:
    return el.findall(path, _NS)


def _text(el: ET.Element | None, default: str = "") -> str:
    if el is None or el.text is None:
        return default
    return el.text


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def project_to_arxml(project: Project) -> str:
    """Serialize *project* to an ARXML document string (pretty-printed)."""
    root = ET.Element(
        f"{{{AUTOSAR_NS}}}AUTOSAR",
        {
            f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOCATION,
        },
    )
    packages = _el(root, "AR-PACKAGES")

    _build_interfaces_package(packages, project)
    _build_application_package(packages, project)
    _build_deployment_package(packages, project)
    _build_machine_package(packages, project)
    _build_bsw_package(packages, project)

    ET.register_namespace("", AUTOSAR_NS)
    ET.register_namespace("xsi", XSI_NS)
    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    # minidom emits a bare declaration; normalise to AUTOSAR convention.
    lines = [ln for ln in pretty.splitlines() if ln.strip()]
    if lines and lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    return "\n".join(lines) + "\n"


def _new_package(packages: ET.Element, name: str) -> ET.Element:
    pkg = _el(packages, "AR-PACKAGE")
    _short_name(pkg, name)
    return _el(pkg, "ELEMENTS")


def _build_interfaces_package(packages: ET.Element, project: Project) -> None:
    if not project.service_interfaces:
        return
    elements = _new_package(packages, "ServiceInterfaces")
    for si in project.service_interfaces:
        node = _el(elements, "SERVICE-INTERFACE")
        _short_name(node, si.name)
        _el(node, "NAMESPACE", si.namespace)
        if si.methods:
            methods = _el(node, "METHODS")
            for m in si.methods:
                mnode = _el(methods, "CLIENT-SERVER-OPERATION")
                _short_name(mnode, m.name)
                _el(mnode, "FIRE-AND-FORGET", "true" if m.fire_and_forget else "false")
                if m.arguments:
                    args = _el(mnode, "ARGUMENTS")
                    for a in m.arguments:
                        anode = _el(args, "ARGUMENT-DATA-PROTOTYPE")
                        _short_name(anode, a.name)
                        _el(anode, "TYPE-TREF", a.type)
                        _el(anode, "DIRECTION", a.direction.value)
        if si.events:
            events = _el(node, "EVENTS")
            for e in si.events:
                enode = _el(events, "VARIABLE-DATA-PROTOTYPE")
                _short_name(enode, e.name)
                _el(enode, "TYPE-TREF", e.type)
        if si.fields:
            fields = _el(node, "FIELDS")
            for f in si.fields:
                fnode = _el(fields, "FIELD")
                _short_name(fnode, f.name)
                _el(fnode, "TYPE-TREF", f.type)
                _el(fnode, "HAS-GETTER", "true" if f.has_getter else "false")
                _el(fnode, "HAS-SETTER", "true" if f.has_setter else "false")
                _el(fnode, "HAS-NOTIFIER", "true" if f.has_notifier else "false")


def _build_application_package(packages: ET.Element, project: Project) -> None:
    if not (project.applications or project.executables):
        return
    elements = _new_package(packages, "Applications")
    for app in project.applications:
        node = _el(elements, "ADAPTIVE-APPLICATION-SW-COMPONENT-TYPE")
        _short_name(node, app.name)
        if app.description:
            _el(node, "DESC", app.description)
        if app.ports:
            ports = _el(node, "PORTS")
            for p in app.ports:
                tag = "P-PORT-PROTOTYPE" if p.direction == PortDirection.PROVIDED else "R-PORT-PROTOTYPE"
                pnode = _el(ports, tag)
                _short_name(pnode, p.name)
                ref_tag = (
                    "PROVIDED-INTERFACE-TREF"
                    if p.direction == PortDirection.PROVIDED
                    else "REQUIRED-INTERFACE-TREF"
                )
                _ref(
                    pnode,
                    ref_tag,
                    "SERVICE-INTERFACE",
                    f"/ServiceInterfaces/{p.interface}",
                )
    for ex in project.executables:
        node = _el(elements, "EXECUTABLE")
        _short_name(node, ex.name)
        _el(node, "VERSION", ex.version)
        _ref(
            node,
            "ROOT-SW-COMPONENT-TREF",
            "ADAPTIVE-APPLICATION-SW-COMPONENT-TYPE",
            f"/Applications/{ex.root_component}",
        )


def _build_deployment_package(packages: ET.Element, project: Project) -> None:
    if not (project.processes or project.service_instances):
        return
    elements = _new_package(packages, "Deployment")
    for proc in project.processes:
        node = _el(elements, "PROCESS")
        _short_name(node, proc.name)
        _ref(node, "EXECUTABLE-REF", "EXECUTABLE", f"/Applications/{proc.executable}")
        sched = _el(node, "PROCESS-STATE-MACHINE")
        _el(sched, "SCHEDULING-POLICY", proc.scheduling_policy)
        _el(sched, "SCHEDULING-PRIORITY", str(proc.priority))
        if proc.core_affinity:
            cores = _el(sched, "CORE-AFFINITY")
            for c in proc.core_affinity:
                _el(cores, "CORE-ID", str(c))
        states = _el(node, "STATE-DEPENDENT-STARTUP-CONFIGS")
        for st in proc.startup_states:
            snode = _el(states, "STATE-DEPENDENT-STARTUP-CONFIG")
            _el(snode, "FUNCTION-GROUP-STATE-IREF", st)
    for si in project.service_instances:
        tag = {
            TransportBinding.SOMEIP: "SOMEIP-SERVICE-INSTANCE",
            TransportBinding.DDS: "DDS-SERVICE-INSTANCE",
            TransportBinding.IPC: "USER-DEFINED-SERVICE-INSTANCE",
        }[si.binding]
        node = _el(elements, tag)
        _short_name(node, si.name)
        _ref(node, "SERVICE-INTERFACE-REF", "SERVICE-INTERFACE", f"/ServiceInterfaces/{si.service_interface}")
        _el(node, "SERVICE-INSTANCE-ID", str(si.instance_id))
        _el(node, "ROLE", si.role.value)
        if si.service_id is not None:
            _el(node, "SERVICE-ID", str(si.service_id))
        if si.udp_port is not None:
            _el(node, "UDP-PORT", str(si.udp_port))
        if si.tcp_port is not None:
            _el(node, "TCP-PORT", str(si.tcp_port))


def _build_machine_package(packages: ET.Element, project: Project) -> None:
    if not project.machines:
        return
    elements = _new_package(packages, "Machines")
    for m in project.machines:
        node = _el(elements, "MACHINE")
        _short_name(node, m.name)
        states = _el(node, "MACHINE-STATES")
        for st in m.machine_states:
            snode = _el(states, "MODE-DECLARATION")
            _short_name(snode, st)
        clusters = _el(node, "FUNCTIONAL-CLUSTERS")
        for fc in m.functional_clusters:
            _el(clusters, "FUNCTIONAL-CLUSTER-REF", fc)


def _build_bsw_package(packages: ET.Element, project: Project) -> None:
    if not project.bsw_modules:
        return
    elements = _new_package(packages, "EcucModuleConfiguration")
    for mod in project.bsw_modules:
        node = _el(elements, "ECUC-MODULE-CONFIGURATION-VALUES")
        _short_name(node, mod.name)
        if mod.description:
            _el(node, "DESC", mod.description)
        _ref(node, "DEFINITION-REF", "ECUC-MODULE-DEF", f"/AUTOSAR/EcucDefs/{mod.name}")
        _el(node, "VENDOR", mod.vendor)
        containers = _el(node, "CONTAINERS")
        for c in mod.containers:
            _build_container(containers, c)


def _build_container(parent: ET.Element, container: Container) -> None:
    node = _el(parent, "ECUC-CONTAINER-VALUE")
    _short_name(node, container.name)
    _ref(node, "DEFINITION-REF", "ECUC-PARAM-CONF-CONTAINER-DEF", container.name)
    if container.parameters:
        params = _el(node, "PARAMETER-VALUES")
        for p in container.parameters:
            _build_parameter(params, p)
    if container.sub_containers:
        subs = _el(node, "SUB-CONTAINERS")
        for sub in container.sub_containers:
            _build_container(subs, sub)


_PARAM_TAG = {
    ParamType.INTEGER: ("ECUC-NUMERICAL-PARAM-VALUE", "VALUE"),
    ParamType.FLOAT: ("ECUC-NUMERICAL-PARAM-VALUE", "VALUE"),
    ParamType.BOOLEAN: ("ECUC-NUMERICAL-PARAM-VALUE", "VALUE"),
    ParamType.STRING: ("ECUC-TEXTUAL-PARAM-VALUE", "VALUE"),
    ParamType.ENUM: ("ECUC-TEXTUAL-PARAM-VALUE", "VALUE"),
    ParamType.REFERENCE: ("ECUC-REFERENCE-VALUE", "VALUE-REF"),
}


def _build_parameter(parent: ET.Element, param: Parameter) -> None:
    tag, value_tag = _PARAM_TAG[param.type]
    node = _el(parent, tag)
    _ref(node, "DEFINITION-REF", "ECUC-PARAMETER-DEF", param.name)
    if param.type == ParamType.BOOLEAN:
        value = "1" if param.value else "0"
    else:
        value = "" if param.value is None else str(param.value)
    _el(node, value_tag, value)


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #
def arxml_to_project(xml_text: str, project_name: str = "Imported") -> Project:
    """Parse ARXML produced by :func:`project_to_arxml` back into a Project."""
    root = ET.fromstring(xml_text)
    project = Project(name=project_name)

    for pkg in _findall(root, ".//ar:AR-PACKAGE"):
        pkg_name = _text(_find(pkg, "ar:SHORT-NAME"))
        elements = _find(pkg, "ar:ELEMENTS")
        if elements is None:
            continue
        if pkg_name == "ServiceInterfaces":
            _parse_interfaces(elements, project)
        elif pkg_name == "Applications":
            _parse_applications(elements, project)
        elif pkg_name == "Deployment":
            _parse_deployment(elements, project)
        elif pkg_name == "Machines":
            _parse_machines(elements, project)
        elif pkg_name == "EcucModuleConfiguration":
            _parse_bsw(elements, project)
    return project


def _parse_interfaces(elements: ET.Element, project: Project) -> None:
    for node in _findall(elements, "ar:SERVICE-INTERFACE"):
        si = ServiceInterface(
            name=_text(_find(node, "ar:SHORT-NAME")),
            namespace=_text(_find(node, "ar:NAMESPACE"), "ara"),
        )
        for m in _findall(node, "ar:METHODS/ar:CLIENT-SERVER-OPERATION"):
            method = Method(
                name=_text(_find(m, "ar:SHORT-NAME")),
                fire_and_forget=_text(_find(m, "ar:FIRE-AND-FORGET")) == "true",
            )
            for a in _findall(m, "ar:ARGUMENTS/ar:ARGUMENT-DATA-PROTOTYPE"):
                from .model import ArgDirection

                method.arguments.append(
                    Argument(
                        name=_text(_find(a, "ar:SHORT-NAME")),
                        type=_text(_find(a, "ar:TYPE-TREF")),
                        direction=ArgDirection(_text(_find(a, "ar:DIRECTION"), "IN")),
                    )
                )
            si.methods.append(method)
        for e in _findall(node, "ar:EVENTS/ar:VARIABLE-DATA-PROTOTYPE"):
            si.events.append(
                Event(name=_text(_find(e, "ar:SHORT-NAME")), type=_text(_find(e, "ar:TYPE-TREF")))
            )
        for f in _findall(node, "ar:FIELDS/ar:FIELD"):
            si.fields.append(
                Field(
                    name=_text(_find(f, "ar:SHORT-NAME")),
                    type=_text(_find(f, "ar:TYPE-TREF")),
                    has_getter=_text(_find(f, "ar:HAS-GETTER"), "true") == "true",
                    has_setter=_text(_find(f, "ar:HAS-SETTER"), "true") == "true",
                    has_notifier=_text(_find(f, "ar:HAS-NOTIFIER"), "true") == "true",
                )
            )
        project.service_interfaces.append(si)


def _tref_leaf(path: str) -> str:
    return path.rsplit("/", 1)[-1] if path else path


def _parse_applications(elements: ET.Element, project: Project) -> None:
    for node in _findall(elements, "ar:ADAPTIVE-APPLICATION-SW-COMPONENT-TYPE"):
        app = AdaptiveApplication(
            name=_text(_find(node, "ar:SHORT-NAME")),
            description=_text(_find(node, "ar:DESC")),
        )
        ports = _find(node, "ar:PORTS")
        if ports is not None:
            # Iterate children in document order so port ordering round-trips.
            for p in list(ports):
                tag = p.tag.split("}", 1)[-1]
                if tag == "P-PORT-PROTOTYPE":
                    app.ports.append(
                        PortPrototype(
                            name=_text(_find(p, "ar:SHORT-NAME")),
                            direction=PortDirection.PROVIDED,
                            interface=_tref_leaf(_text(_find(p, "ar:PROVIDED-INTERFACE-TREF"))),
                        )
                    )
                elif tag == "R-PORT-PROTOTYPE":
                    app.ports.append(
                        PortPrototype(
                            name=_text(_find(p, "ar:SHORT-NAME")),
                            direction=PortDirection.REQUIRED,
                            interface=_tref_leaf(_text(_find(p, "ar:REQUIRED-INTERFACE-TREF"))),
                        )
                    )
        project.applications.append(app)
    for node in _findall(elements, "ar:EXECUTABLE"):
        project.executables.append(
            Executable(
                name=_text(_find(node, "ar:SHORT-NAME")),
                version=_text(_find(node, "ar:VERSION"), "1.0.0"),
                root_component=_tref_leaf(_text(_find(node, "ar:ROOT-SW-COMPONENT-TREF"))),
            )
        )


def _parse_deployment(elements: ET.Element, project: Project) -> None:
    for node in _findall(elements, "ar:PROCESS"):
        sched = _find(node, "ar:PROCESS-STATE-MACHINE")
        proc = Process(
            name=_text(_find(node, "ar:SHORT-NAME")),
            executable=_tref_leaf(_text(_find(node, "ar:EXECUTABLE-REF"))),
        )
        if sched is not None:
            proc.scheduling_policy = _text(_find(sched, "ar:SCHEDULING-POLICY"), "SCHED_FIFO")
            prio = _text(_find(sched, "ar:SCHEDULING-PRIORITY"), "50")
            proc.priority = int(prio) if prio.lstrip("-").isdigit() else 50
            proc.core_affinity = [
                int(c.text) for c in _findall(sched, "ar:CORE-AFFINITY/ar:CORE-ID") if c.text and c.text.isdigit()
            ]
        states = [
            _text(s) for s in _findall(node, "ar:STATE-DEPENDENT-STARTUP-CONFIGS/ar:STATE-DEPENDENT-STARTUP-CONFIG/ar:FUNCTION-GROUP-STATE-IREF")
        ]
        if states:
            proc.startup_states = states
        project.processes.append(proc)

    binding_by_tag = {
        "SOMEIP-SERVICE-INSTANCE": TransportBinding.SOMEIP,
        "DDS-SERVICE-INSTANCE": TransportBinding.DDS,
        "USER-DEFINED-SERVICE-INSTANCE": TransportBinding.IPC,
    }
    for tag, binding in binding_by_tag.items():
        for node in _findall(elements, f"ar:{tag}"):
            def _int_or_none(el: ET.Element | None) -> int | None:
                t = _text(el)
                return int(t) if t.lstrip("-").isdigit() else None

            project.service_instances.append(
                ServiceInstance(
                    name=_text(_find(node, "ar:SHORT-NAME")),
                    service_interface=_tref_leaf(_text(_find(node, "ar:SERVICE-INTERFACE-REF"))),
                    instance_id=_int_or_none(_find(node, "ar:SERVICE-INSTANCE-ID")) or 0,
                    binding=binding,
                    role=PortDirection(_text(_find(node, "ar:ROLE"), "PROVIDED")),
                    service_id=_int_or_none(_find(node, "ar:SERVICE-ID")),
                    udp_port=_int_or_none(_find(node, "ar:UDP-PORT")),
                    tcp_port=_int_or_none(_find(node, "ar:TCP-PORT")),
                )
            )


def _parse_machines(elements: ET.Element, project: Project) -> None:
    for node in _findall(elements, "ar:MACHINE"):
        project.machines.append(
            Machine(
                name=_text(_find(node, "ar:SHORT-NAME")),
                machine_states=[
                    _text(_find(s, "ar:SHORT-NAME"))
                    for s in _findall(node, "ar:MACHINE-STATES/ar:MODE-DECLARATION")
                ],
                functional_clusters=[
                    _text(c) for c in _findall(node, "ar:FUNCTIONAL-CLUSTERS/ar:FUNCTIONAL-CLUSTER-REF")
                ],
            )
        )


_TAG_TO_PARAMTYPE = {
    "ECUC-NUMERICAL-PARAM-VALUE": ParamType.INTEGER,
    "ECUC-TEXTUAL-PARAM-VALUE": ParamType.STRING,
    "ECUC-REFERENCE-VALUE": ParamType.REFERENCE,
}


def _parse_bsw(elements: ET.Element, project: Project) -> None:
    for node in _findall(elements, "ar:ECUC-MODULE-CONFIGURATION-VALUES"):
        mod = BswModule(
            name=_text(_find(node, "ar:SHORT-NAME")),
            vendor=_text(_find(node, "ar:VENDOR"), "OpenAUTOSAR"),
            description=_text(_find(node, "ar:DESC")),
        )
        containers = _find(node, "ar:CONTAINERS")
        if containers is not None:
            for c in _findall(containers, "ar:ECUC-CONTAINER-VALUE"):
                mod.containers.append(_parse_container(c))
        project.bsw_modules.append(mod)


def _parse_container(node: ET.Element) -> Container:
    container = Container(name=_text(_find(node, "ar:SHORT-NAME")))
    params = _find(node, "ar:PARAMETER-VALUES")
    if params is not None:
        for child in list(params):
            tag = child.tag.split("}", 1)[-1]
            ptype = _TAG_TO_PARAMTYPE.get(tag, ParamType.STRING)
            def_ref = _find(child, "ar:DEFINITION-REF")
            value_el = _find(child, "ar:VALUE") or _find(child, "ar:VALUE-REF")
            container.parameters.append(
                Parameter(
                    name=_tref_leaf(_text(def_ref)),
                    type=ptype,
                    value=_text(value_el),
                )
            )
    subs = _find(node, "ar:SUB-CONTAINERS")
    if subs is not None:
        for sub in _findall(subs, "ar:ECUC-CONTAINER-VALUE"):
            container.sub_containers.append(_parse_container(sub))
    return container
