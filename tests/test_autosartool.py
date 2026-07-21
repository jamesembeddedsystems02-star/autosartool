"""Unit tests for autosartool (standard-library unittest, no dependencies)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from autosartool import (  # noqa: E402
    AdaptiveApplication,
    Argument,
    ArgDirection,
    Executable,
    PortDirection,
    PortPrototype,
    Process,
    Project,
    ServiceInterface,
    Method,
)
from autosartool.arxml import arxml_to_project, project_to_arxml  # noqa: E402
from autosartool.codegen import generate  # noqa: E402
from autosartool.project import load_project, save_project  # noqa: E402
from autosartool.templates import BSW_TEMPLATES, create_bsw_module, example_project  # noqa: E402
from autosartool.validation import Severity, validate  # noqa: E402


class ModelSerializationTests(unittest.TestCase):
    def test_project_roundtrip_dict(self):
        p = example_project()
        d = p.to_dict()
        p2 = Project.from_dict(d)
        self.assertEqual(p.to_dict(), p2.to_dict())

    def test_save_and_load(self):
        p = example_project()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "proj.autosarproj")
            save_project(p, path)
            loaded = load_project(path)
            self.assertEqual(loaded.to_dict(), p.to_dict())


class ValidationTests(unittest.TestCase):
    def test_example_is_valid(self):
        report = validate(example_project())
        self.assertTrue(report.ok, msg="\n".join(str(f) for f in report.errors))

    def test_dangling_port_reference(self):
        p = Project(name="t")
        p.applications.append(
            AdaptiveApplication(name="App", ports=[PortPrototype("P", PortDirection.PROVIDED, "Missing")])
        )
        report = validate(p)
        self.assertFalse(report.ok)
        self.assertTrue(any(f.rule == "REF-001" for f in report.errors))

    def test_invalid_identifier(self):
        p = Project(name="t")
        p.service_interfaces.append(ServiceInterface(name="1bad"))
        report = validate(p)
        self.assertTrue(any(f.rule == "NAMING-001" for f in report.errors))

    def test_duplicate_someip_ids(self):
        from autosartool import ServiceInstance, TransportBinding

        p = Project(name="t")
        p.service_interfaces.append(ServiceInterface(name="Svc", methods=[Method("M")]))
        for i in range(2):
            p.service_instances.append(
                ServiceInstance(
                    name=f"Inst{i}",
                    service_interface="Svc",
                    instance_id=1,
                    binding=TransportBinding.SOMEIP,
                    service_id=100,
                    udp_port=30000,
                )
            )
        report = validate(p)
        self.assertTrue(any(f.rule == "SI-006" for f in report.errors))

    def test_priority_range(self):
        p = Project(name="t")
        p.applications.append(AdaptiveApplication(name="App", ports=[]))
        p.executables.append(Executable("Exe", "App"))
        p.processes.append(Process("Proc", "Exe", "SCHED_FIFO", priority=200))
        report = validate(p)
        self.assertTrue(any(f.rule == "PROC-003" for f in report.errors))


class ArxmlTests(unittest.TestCase):
    def test_export_is_wellformed_xml(self):
        import xml.etree.ElementTree as ET

        xml = project_to_arxml(example_project())
        root = ET.fromstring(xml)
        self.assertTrue(root.tag.endswith("AUTOSAR"))
        self.assertIn("SERVICE-INTERFACE", xml)
        self.assertIn("ADAPTIVE-APPLICATION-SW-COMPONENT-TYPE", xml)

    def test_arxml_roundtrip(self):
        original = example_project()
        xml = project_to_arxml(original)
        imported = arxml_to_project(xml, project_name=original.name)

        self.assertEqual(
            [s.name for s in original.service_interfaces],
            [s.name for s in imported.service_interfaces],
        )
        self.assertEqual(
            [a.name for a in original.applications],
            [a.name for a in imported.applications],
        )
        # Ports survive round-trip with direction + interface intact.
        for a_orig, a_imp in zip(original.applications, imported.applications):
            self.assertEqual(
                [(p.name, p.direction, p.interface) for p in a_orig.ports],
                [(p.name, p.direction, p.interface) for p in a_imp.ports],
            )
        # Service instances keep their SOME/IP identity.
        self.assertEqual(
            [(s.service_interface, s.instance_id, s.service_id) for s in original.service_instances],
            [(s.service_interface, s.instance_id, s.service_id) for s in imported.service_instances],
        )

    def test_method_arguments_roundtrip(self):
        p = Project(name="t")
        p.service_interfaces.append(
            ServiceInterface(
                name="Svc",
                methods=[
                    Method(
                        name="Op",
                        arguments=[
                            Argument("a", "uint32", ArgDirection.IN),
                            Argument("b", "float", ArgDirection.OUT),
                        ],
                    )
                ],
            )
        )
        imported = arxml_to_project(project_to_arxml(p))
        args = imported.service_interfaces[0].methods[0].arguments
        self.assertEqual([(a.name, a.type, a.direction) for a in args],
                         [("a", "uint32", ArgDirection.IN), ("b", "float", ArgDirection.OUT)])


class CodegenTests(unittest.TestCase):
    def test_generates_expected_files(self):
        files = generate(example_project())
        paths = set(files.keys())
        self.assertIn("CMakeLists.txt", paths)
        self.assertTrue(any(p.endswith("_skeleton.h") for p in paths))
        self.assertTrue(any(p.endswith("_proxy.h") for p in paths))
        self.assertTrue(any(p.endswith("_main.cpp") for p in paths))
        self.assertTrue(any("execution_manifest.json" in p for p in paths))

    def test_skeleton_contains_service_methods(self):
        files = generate(example_project())
        skel = next(v for k, v in files.items() if k.endswith("radarservice_skeleton.h"))
        self.assertIn("Calibrate", skel)
        self.assertIn("ServiceSkeleton", skel)
        self.assertIn("OfferService", skel)

    def test_proxy_contains_findservice(self):
        files = generate(example_project())
        proxy = next(v for k, v in files.items() if k.endswith("radarservice_proxy.h"))
        self.assertIn("FindService", proxy)
        self.assertIn("ServiceProxy", proxy)

    def test_manifest_is_valid_json(self):
        import json

        files = generate(example_project())
        manifest = next(v for k, v in files.items() if "execution_manifest.json" in k)
        data = json.loads(manifest)
        self.assertIn("processes", data)
        self.assertTrue(len(data["processes"]) >= 1)


class TemplateTests(unittest.TestCase):
    def test_all_templates_instantiate(self):
        for name in BSW_TEMPLATES:
            mod = create_bsw_module(name)
            self.assertEqual(mod.name, name)
            self.assertTrue(mod.containers)

    def test_unknown_template_returns_empty(self):
        mod = create_bsw_module("Xyz")
        self.assertEqual(mod.name, "Xyz")
        self.assertEqual(mod.containers, [])


if __name__ == "__main__":
    unittest.main()
