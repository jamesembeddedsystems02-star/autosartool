"""Command-line interface for autosartool.

Usage examples::

    autosartool new myproject.autosarproj --example
    autosartool validate myproject.autosarproj
    autosartool generate myproject.autosarproj --out ./generated
    autosartool export-arxml myproject.autosarproj --out project.arxml
    autosartool import-arxml project.arxml --out imported.autosarproj
    autosartool info myproject.autosarproj
    autosartool serve --port 8080
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .arxml import arxml_to_project, project_to_arxml
from .codegen import generate
from .model import Project
from .project import load_project, save_project, write_generated
from .templates import example_project
from .validation import Severity, validate


def _print_report(report) -> None:
    for f in report.findings:
        stream = sys.stderr if f.severity == Severity.ERROR else sys.stdout
        print(str(f), file=stream)
    print(
        f"\n{len(report.errors)} error(s), {len(report.warnings)} warning(s) — "
        f"{'OK' if report.ok else 'FAILED'}"
    )


def cmd_new(args) -> int:
    if args.example:
        project = example_project()
    else:
        project = Project(name=args.name or "New Project", package=args.package or "MyProject")
    save_project(project, args.path)
    print(f"Created project '{project.name}' -> {args.path}")
    return 0


def cmd_validate(args) -> int:
    project = load_project(args.path)
    report = validate(project)
    _print_report(report)
    return 0 if report.ok else 1


def cmd_generate(args) -> int:
    project = load_project(args.path)
    report = validate(project)
    if not report.ok and not args.force:
        _print_report(report)
        print("\nValidation failed; use --force to generate anyway.", file=sys.stderr)
        return 1
    files = generate(project)
    written = write_generated(files, args.out)
    print(f"Generated {len(written)} file(s) under {args.out}:")
    for path in sorted(written):
        print(f"  {path}")
    return 0


def cmd_export_arxml(args) -> int:
    project = load_project(args.path)
    xml = project_to_arxml(project)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(xml)
        print(f"Wrote ARXML -> {args.out}")
    else:
        sys.stdout.write(xml)
    return 0


def cmd_import_arxml(args) -> int:
    with open(args.path, encoding="utf-8") as fh:
        xml = fh.read()
    project = arxml_to_project(xml, project_name=args.name or "Imported")
    save_project(project, args.out)
    print(f"Imported ARXML -> {args.out}")
    return 0


def cmd_info(args) -> int:
    project = load_project(args.path)
    print(f"Project:            {project.name}")
    print(f"Package:            {project.package}")
    print(f"AUTOSAR release:    {project.autosar_release}")
    print(f"Service interfaces: {len(project.service_interfaces)}")
    print(f"Applications:       {len(project.applications)}")
    print(f"Executables:        {len(project.executables)}")
    print(f"Processes:          {len(project.processes)}")
    print(f"Machines:           {len(project.machines)}")
    print(f"Service instances:  {len(project.service_instances)}")
    print(f"BSW modules:        {len(project.bsw_modules)}")
    return 0


def cmd_serve(args) -> int:
    from .webapp import run_server

    run_server(host=args.host, port=args.port, project_path=args.path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autosartool",
        description="Open Adaptive AUTOSAR application & BSW configuration tool.",
    )
    parser.add_argument("--version", action="version", version=f"autosartool {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="Create a new project file")
    p_new.add_argument("path", help="Output .autosarproj path")
    p_new.add_argument("--name", help="Project name")
    p_new.add_argument("--package", help="AUTOSAR package short-name")
    p_new.add_argument("--example", action="store_true", help="Populate with the ADAS demo project")
    p_new.set_defaults(func=cmd_new)

    p_val = sub.add_parser("validate", help="Validate a project")
    p_val.add_argument("path", help=".autosarproj path")
    p_val.set_defaults(func=cmd_validate)

    p_gen = sub.add_parser("generate", help="Generate C++/manifests/CMake")
    p_gen.add_argument("path", help=".autosarproj path")
    p_gen.add_argument("--out", default="./generated", help="Output directory")
    p_gen.add_argument("--force", action="store_true", help="Generate even if validation fails")
    p_gen.set_defaults(func=cmd_generate)

    p_exp = sub.add_parser("export-arxml", help="Export project to ARXML")
    p_exp.add_argument("path", help=".autosarproj path")
    p_exp.add_argument("--out", help="Output .arxml path (stdout if omitted)")
    p_exp.set_defaults(func=cmd_export_arxml)

    p_imp = sub.add_parser("import-arxml", help="Import an ARXML into a project file")
    p_imp.add_argument("path", help="Input .arxml path")
    p_imp.add_argument("--out", required=True, help="Output .autosarproj path")
    p_imp.add_argument("--name", help="Project name")
    p_imp.set_defaults(func=cmd_import_arxml)

    p_info = sub.add_parser("info", help="Print a summary of a project")
    p_info.add_argument("path", help=".autosarproj path")
    p_info.set_defaults(func=cmd_info)

    p_serve = sub.add_parser("serve", help="Launch the web configuration UI")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind host")
    p_serve.add_argument("--port", type=int, default=8080, help="Bind port")
    p_serve.add_argument("--path", help="Project file to load/save (default: in-memory example)")
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
