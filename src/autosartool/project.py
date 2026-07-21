"""Project persistence helpers (JSON ``.autosarproj`` files)."""

from __future__ import annotations

import json
import os

from .model import Project


def save_project(project: Project, path: str) -> None:
    """Write *project* to *path* as pretty-printed JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(project.to_dict(), fh, indent=2)
        fh.write("\n")


def load_project(path: str) -> Project:
    """Load a project from a JSON ``.autosarproj`` file."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return Project.from_dict(data)


def write_generated(files: dict[str, str], out_dir: str) -> list[str]:
    """Write a ``{relative_path: content}`` map under *out_dir*.

    Returns the list of absolute paths written.
    """
    written = []
    for rel, content in files.items():
        dest = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)
        written.append(dest)
    return written
