"""A dependency-free web UI + JSON API for autosartool.

Built on :mod:`http.server` from the standard library so it runs anywhere
Python does, with no pip install required. Serves the single-page UI from the
packaged ``web/`` directory and exposes a small JSON API the UI drives:

    GET  /api/project          -> current project as JSON
    PUT  /api/project          -> replace current project (body = project JSON)
    POST /api/validate         -> validation report
    POST /api/generate         -> {path: content} generated files
    GET  /api/arxml            -> ARXML export (text/xml)
    POST /api/example          -> load the built-in ADAS example
    GET  /api/templates        -> available BSW module template names
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .arxml import project_to_arxml
from .codegen import generate
from .model import Project
from .project import load_project, save_project
from .templates import BSW_TEMPLATES, create_bsw_module, example_project
from .validation import validate

def _resolve_web_dir() -> str:
    """Locate the static ``web/`` directory across run/install layouts."""
    candidates = [
        os.environ.get("AUTOSARTOOL_WEB_DIR", ""),
        os.path.join(os.path.dirname(__file__), "web"),  # packaged inside the module
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web"),  # repo root
        os.path.join(os.getcwd(), "web"),
    ]
    for c in candidates:
        if c and os.path.isdir(c) and os.path.isfile(os.path.join(c, "index.html")):
            return c
    # Fall back to repo-root guess so error messages point somewhere sensible.
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web")


_WEB_DIR = _resolve_web_dir()


class _State:
    """Server-wide mutable state: the current project and its file path."""

    def __init__(self, project: Project, path: str | None) -> None:
        self.project = project
        self.path = path

    def persist(self) -> None:
        if self.path:
            save_project(self.project, self.path)


def _make_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        server_version = "autosartool/0.1"

        def log_message(self, fmt, *args):  # pragma: no cover - quiet by default
            pass

        # -- helpers -------------------------------------------------------
        def _send_json(self, obj, status=200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, text, content_type="text/plain", status=200):
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def _serve_static(self, path):
            if path in ("/", ""):
                path = "/index.html"
            # prevent path traversal
            safe = os.path.normpath(path).lstrip("/\\")
            full = os.path.join(_WEB_DIR, safe)
            if not full.startswith(_WEB_DIR) or not os.path.isfile(full):
                self._send_text("Not found", status=404)
                return
            ctype = {
                ".html": "text/html",
                ".css": "text/css",
                ".js": "application/javascript",
                ".svg": "image/svg+xml",
            }.get(os.path.splitext(full)[1], "application/octet-stream")
            with open(full, "rb") as fh:
                body = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # -- routing -------------------------------------------------------
        def do_GET(self):
            parsed = urlparse(self.path)
            route = parsed.path
            if route == "/api/project":
                self._send_json(state.project.to_dict())
            elif route == "/api/arxml":
                self._send_text(project_to_arxml(state.project), content_type="text/xml")
            elif route == "/api/templates":
                self._send_json({"bsw_templates": sorted(BSW_TEMPLATES.keys())})
            elif route.startswith("/api/"):
                self._send_json({"error": "unknown endpoint"}, status=404)
            else:
                self._serve_static(route)

        def do_PUT(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/project":
                try:
                    data = self._read_body()
                    state.project = Project.from_dict(data)
                    state.persist()
                    self._send_json({"ok": True})
                except (KeyError, ValueError, TypeError) as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=400)
            else:
                self._send_json({"error": "unknown endpoint"}, status=404)

        def do_POST(self):
            parsed = urlparse(self.path)
            route = parsed.path
            if route == "/api/validate":
                report = validate(state.project)
                self._send_json(report.to_dict())
            elif route == "/api/generate":
                report = validate(state.project)
                if not report.ok:
                    self._send_json(
                        {"ok": False, "report": report.to_dict(), "files": {}}, status=200
                    )
                    return
                files = generate(state.project)
                self._send_json({"ok": True, "report": report.to_dict(), "files": files})
            elif route == "/api/example":
                state.project = example_project()
                state.persist()
                self._send_json(state.project.to_dict())
            elif route == "/api/bsw-template":
                try:
                    body = self._read_body()
                    module = create_bsw_module(body["name"])
                    self._send_json(module.to_dict())
                except (KeyError, ValueError) as exc:
                    self._send_json({"error": str(exc)}, status=400)
            else:
                self._send_json({"error": "unknown endpoint"}, status=404)

    return Handler


def run_server(host: str = "127.0.0.1", port: int = 8080, project_path: str | None = None) -> None:
    """Start the blocking web server."""
    if project_path and os.path.isfile(project_path):
        project = load_project(project_path)
    else:
        project = example_project()
    state = _State(project, project_path)
    handler = _make_handler(state)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"autosartool web UI running at http://{host}:{port}  (Ctrl-C to stop)")
    if project_path:
        print(f"Editing project file: {project_path}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        print("\nShutting down.")
        httpd.shutdown()
