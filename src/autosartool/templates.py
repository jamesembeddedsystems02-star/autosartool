"""Prebuilt module and interface templates.

Provides ready-made Basic Software / functional-cluster module configurations
and example service interfaces, equivalent to the module catalog a commercial
configuration tool ships with. Users instantiate these and then tune the
parameter values.
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
    Process,
    Project,
    ServiceInstance,
    ServiceInterface,
    TransportBinding,
)


def _p(name: str, ptype: ParamType, value) -> Parameter:
    return Parameter(name=name, type=ptype, value=value)


# --------------------------------------------------------------------------- #
# Adaptive functional-cluster modules
# --------------------------------------------------------------------------- #
def execution_management() -> BswModule:
    """Execution Management (EM) configuration."""
    return BswModule(
        name="EM",
        vendor="OpenAUTOSAR",
        description="Execution Management functional cluster",
        containers=[
            Container(
                name="EmGeneral",
                parameters=[
                    _p("EmDefaultSchedulingPolicy", ParamType.ENUM, "SCHED_OTHER"),
                    _p("EmWatchdogSupervisionEnabled", ParamType.BOOLEAN, True),
                    _p("EmStartupTimeoutMs", ParamType.INTEGER, 5000),
                ],
            )
        ],
    )


def state_management() -> BswModule:
    """State Management (SM) configuration."""
    return BswModule(
        name="SM",
        vendor="OpenAUTOSAR",
        description="State Management functional cluster",
        containers=[
            Container(
                name="SmFunctionGroups",
                sub_containers=[
                    Container(
                        name="MachineState",
                        parameters=[
                            _p("SmInitialState", ParamType.STRING, "Startup"),
                            _p("SmStates", ParamType.STRING, "Startup,Running,Shutdown"),
                        ],
                    )
                ],
            )
        ],
    )


def communication_management() -> BswModule:
    """Communication Management (CM) configuration."""
    return BswModule(
        name="CM",
        vendor="OpenAUTOSAR",
        description="Communication Management functional cluster",
        containers=[
            Container(
                name="CmGeneral",
                parameters=[
                    _p("CmDefaultBinding", ParamType.ENUM, "SOMEIP"),
                    _p("CmServiceDiscoveryEnabled", ParamType.BOOLEAN, True),
                    _p("CmSdMulticastAddress", ParamType.STRING, "239.192.0.1"),
                    _p("CmSdPort", ParamType.INTEGER, 30490),
                ],
            )
        ],
    )


def diagnostic_management() -> BswModule:
    """Diagnostic Management (DM) configuration."""
    return BswModule(
        name="DM",
        vendor="OpenAUTOSAR",
        description="Diagnostic Management functional cluster",
        containers=[
            Container(
                name="DmGeneral",
                parameters=[
                    _p("DmDiagnosticProtocol", ParamType.ENUM, "UDS"),
                    _p("DmSessionTimeoutMs", ParamType.INTEGER, 5000),
                ],
            )
        ],
    )


def persistency() -> BswModule:
    """Persistency (PER) configuration."""
    return BswModule(
        name="PER",
        vendor="OpenAUTOSAR",
        description="Persistency functional cluster",
        containers=[
            Container(
                name="PerGeneral",
                parameters=[
                    _p("PerStorageRoot", ParamType.STRING, "/opt/persistency"),
                    _p("PerRedundancy", ParamType.ENUM, "NONE"),
                ],
            )
        ],
    )


# --------------------------------------------------------------------------- #
# Classic BSW modules (generic EcuC configuration)
# --------------------------------------------------------------------------- #
def os_module() -> BswModule:
    """Classic AUTOSAR OS module skeleton."""
    return BswModule(
        name="Os",
        description="AUTOSAR Operating System",
        containers=[
            Container(
                name="OsOS",
                parameters=[
                    _p("OsScalabilityClass", ParamType.ENUM, "SC1"),
                    _p("OsStatus", ParamType.ENUM, "EXTENDED"),
                    _p("OsUseGetServiceId", ParamType.BOOLEAN, False),
                ],
            ),
            Container(
                name="OsTask",
                parameters=[
                    _p("OsTaskPriority", ParamType.INTEGER, 1),
                    _p("OsTaskSchedule", ParamType.ENUM, "FULL"),
                    _p("OsTaskActivation", ParamType.INTEGER, 1),
                ],
            ),
        ],
    )


def com_module() -> BswModule:
    """Classic AUTOSAR COM module skeleton."""
    return BswModule(
        name="Com",
        description="AUTOSAR Communication",
        containers=[
            Container(
                name="ComGeneral",
                parameters=[
                    _p("ComConfigurationUseDet", ParamType.BOOLEAN, True),
                    _p("ComVersionInfoApi", ParamType.BOOLEAN, False),
                ],
            )
        ],
    )


def nvm_module() -> BswModule:
    """Classic AUTOSAR NvM module skeleton."""
    return BswModule(
        name="NvM",
        description="AUTOSAR Non-Volatile Memory Manager",
        containers=[
            Container(
                name="NvMCommon",
                parameters=[
                    _p("NvMDynamicConfiguration", ParamType.BOOLEAN, True),
                    _p("NvMCrcNumOfBytes", ParamType.INTEGER, 64),
                ],
            )
        ],
    )


BSW_TEMPLATES = {
    "EM": execution_management,
    "SM": state_management,
    "CM": communication_management,
    "DM": diagnostic_management,
    "PER": persistency,
    "Os": os_module,
    "Com": com_module,
    "NvM": nvm_module,
}


def create_bsw_module(name: str) -> BswModule:
    """Instantiate a BSW module from a template, or an empty one if unknown."""
    factory = BSW_TEMPLATES.get(name)
    if factory:
        return factory()
    return BswModule(name=name, description=f"{name} module (empty configuration)")


# --------------------------------------------------------------------------- #
# Example project
# --------------------------------------------------------------------------- #
def example_project() -> Project:
    """A complete, valid demonstration project.

    Models a small ADAS-style setup: a radar sensor service produced by one
    application and consumed by a brake controller, deployed on one machine.
    """
    radar_iface = ServiceInterface(
        name="RadarService",
        namespace="adas",
        methods=[
            Method(
                name="Calibrate",
                arguments=[
                    Argument("azimuthOffset", "float", ArgDirection.IN),
                    Argument("success", "boolean", ArgDirection.OUT),
                ],
            ),
            Method(name="Reset", fire_and_forget=True),
        ],
        events=[Event(name="ObjectList", type="uint32")],
        fields=[Field(name="OperatingMode", type="uint8")],
    )

    brake_iface = ServiceInterface(
        name="BrakeService",
        namespace="adas",
        methods=[
            Method(
                name="RequestBraking",
                arguments=[
                    Argument("decel", "float", ArgDirection.IN),
                    Argument("accepted", "boolean", ArgDirection.OUT),
                ],
            )
        ],
        events=[Event(name="BrakeStatus", type="uint8")],
    )

    radar_app = AdaptiveApplication(
        name="RadarSensorApp",
        description="Front radar sensor fusion component",
        ports=[
            PortPrototype("RadarProvider", PortDirection.PROVIDED, "RadarService"),
        ],
    )
    brake_app = AdaptiveApplication(
        name="BrakeControllerApp",
        description="Automatic emergency braking controller",
        ports=[
            PortPrototype("RadarConsumer", PortDirection.REQUIRED, "RadarService"),
            PortPrototype("BrakeProvider", PortDirection.PROVIDED, "BrakeService"),
        ],
    )

    project = Project(
        name="ADAS Demo",
        package="AdasDemo",
        autosar_release="R23-11",
        service_interfaces=[radar_iface, brake_iface],
        applications=[radar_app, brake_app],
        executables=[
            Executable("RadarSensorExe", "RadarSensorApp", "1.2.0"),
            Executable("BrakeControllerExe", "BrakeControllerApp", "1.0.0"),
        ],
        processes=[
            Process("RadarSensorProc", "RadarSensorExe", "SCHED_FIFO", 60, [0]),
            Process("BrakeControllerProc", "BrakeControllerExe", "SCHED_FIFO", 80, [1]),
        ],
        machines=[
            Machine(
                name="AdasEcu",
                functional_clusters=["EM", "SM", "CM", "DM", "PER", "LOG"],
            )
        ],
        service_instances=[
            ServiceInstance(
                name="RadarServiceInstance",
                service_interface="RadarService",
                instance_id=1,
                binding=TransportBinding.SOMEIP,
                role=PortDirection.PROVIDED,
                service_id=0x1234,
                udp_port=30501,
            ),
            ServiceInstance(
                name="BrakeServiceInstance",
                service_interface="BrakeService",
                instance_id=1,
                binding=TransportBinding.SOMEIP,
                role=PortDirection.PROVIDED,
                service_id=0x1235,
                udp_port=30502,
            ),
        ],
        bsw_modules=[
            execution_management(),
            state_management(),
            communication_management(),
        ],
    )
    return project
