# autosartool

An open, dependency-free **Adaptive AUTOSAR** application-component and **Basic
Software / platform-module** configuration tool — a lightweight, scriptable
alternative to commercial tooling such as Vector DaVinci Developer Adaptive,
Elektrobit EB corbos Studio and ETAS ISOLAR-A.

It covers the same core workflow those tools advertise — **model → validate →
generate → export ARXML** — for the Adaptive Platform:

- **Model** service interfaces (`ara::com`), adaptive application software
  components with provided/required ports, executables, processes, machines,
  service-instance (SOME/IP / DDS) bindings, and Basic Software / functional
  cluster module configurations (EcuC-style containers & parameters).
- **Validate** the model against ~30 consistency rules (dangling references,
  duplicate short-names, ID clashes, scheduling/priority ranges, SOME/IP
  identity uniqueness, naming rules, …).
- **Generate** `ara::com` C++ skeleton/proxy headers, an application `main`
  per executable, per-machine Execution-Manifest JSON, a service-instance
  manifest, and a `CMakeLists.txt`.
- **Export / import** AUTOSAR **ARXML** (`AR-PACKAGES` / typed element blocks),
  with a lossless round-trip of this tool's own model.

Everything is implemented on the **Python standard library only** — no `pip
install` required — and ships with a browser-based configuration UI built on
`http.server`.

---

## Requirements

- Python 3.9+ (standard library only). No third-party dependencies.

## Quick start

```bash
# From the repository root — no install needed:
export PYTHONPATH=src

# Create a project pre-filled with the ADAS demo
python -m autosartool.cli new my.autosarproj --example

# Inspect / validate
python -m autosartool.cli info my.autosarproj
python -m autosartool.cli validate my.autosarproj

# Generate C++/manifests/CMake into ./generated
python -m autosartool.cli generate my.autosarproj --out ./generated

# Export / import ARXML
python -m autosartool.cli export-arxml my.autosarproj --out my.arxml
python -m autosartool.cli import-arxml my.arxml --out imported.autosarproj

# Launch the web configuration UI (http://127.0.0.1:8080)
python -m autosartool.cli serve --port 8080 --path my.autosarproj
```

Or install the console script:

```bash
pip install -e .
autosartool serve --path my.autosarproj
```

## Web UI

`autosartool serve` opens an IDE-style single-page editor:

- Left: a category tree (interfaces, applications, executables, processes,
  machines, service instances, BSW modules) with add/delete.
- Center: a typed editor for the selected element (methods/events/fields,
  ports, scheduling, SOME/IP binding, EcuC containers & parameters).
- Toolbar: **Validate**, **Generate** (with a per-file viewer), **Export
  ARXML**, **Load Example**, **Save**.

## Concepts

| Domain | Elements |
| --- | --- |
| Adaptive application | `ServiceInterface` (methods/events/fields), `AdaptiveApplication` (P/R ports), `Executable`, `Process` (EM scheduling), `Machine` (states + functional clusters) |
| Communication | `ServiceInstance` (SOME/IP / DDS / IPC binding, service & instance IDs, ports) |
| Basic Software | `BswModule` → `Container` → `Parameter` (EcuC generic model). Templates for `EM`, `SM`, `CM`, `DM`, `PER` (Adaptive functional clusters) and `Os`, `Com`, `NvM` (Classic BSW). |

## Command reference

| Command | Purpose |
| --- | --- |
| `new PATH [--example] [--name] [--package]` | Create a project file |
| `info PATH` | Summarise a project |
| `validate PATH` | Run validation rules (exit code 1 on error) |
| `generate PATH [--out DIR] [--force]` | Generate code & manifests |
| `export-arxml PATH [--out FILE]` | Export ARXML (stdout if no `--out`) |
| `import-arxml PATH --out FILE [--name]` | Import ARXML into a project file |
| `serve [--host] [--port] [--path]` | Launch the web UI + JSON API |

## Python API

```python
from autosartool import Project, ServiceInterface, Method, Argument, ArgDirection
from autosartool.validation import validate
from autosartool.codegen import generate
from autosartool.arxml import project_to_arxml
from autosartool.templates import example_project

project = example_project()
report = validate(project)
assert report.ok

files = generate(project)          # {relative_path: contents}
arxml = project_to_arxml(project)  # AUTOSAR ARXML string
```

## Project layout

```
src/autosartool/     Python package
  model.py           Data model (dataclasses, to/from dict)
  arxml.py           ARXML export & import (stdlib ElementTree)
  validation.py      Rule-based validator
  codegen.py         ara::com C++ / manifest / CMake generation
  templates.py       BSW module templates + ADAS example project
  project.py         JSON project save/load
  cli.py             Command-line interface
  webapp.py          http.server web UI + JSON API
web/                 Single-page configuration UI (HTML/CSS/JS)
examples/            Ready-made example project
tests/               unittest suite (no pytest required)
```

## Testing

```bash
python -m unittest discover -s tests -v
```

## Scope & disclaimer

This is an independent, educational implementation. It targets the *structure*
and *workflow* of Adaptive AUTOSAR configuration and produces ARXML/`ara::com`
code that mirrors the standard's shapes, but it is **not** a certified AUTOSAR
tool and is not affiliated with AUTOSAR or any commercial vendor. Generated
C++ compiles against a real Adaptive Platform SDK once its include paths are
provided.

## License

MIT — see [LICENSE](LICENSE).
