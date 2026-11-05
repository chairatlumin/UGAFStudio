from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UnrealProject:
    name: str
    path: Path
    engine_association: str | None


def find_uproject(root: Path) -> Path:
    projects = list(root.glob("*.uproject"))

    if not projects:
        raise FileNotFoundError(f"No .uproject file found in: {root}")

    if len(projects) > 1:
        raise RuntimeError(f"Multiple .uproject files found in: {root}")

    return projects[0]


def load_project(project_file: Path) -> UnrealProject:
    data = json.loads(project_file.read_text(encoding="utf-8"))

    return UnrealProject(
        name=project_file.stem,
        path=project_file.resolve(),
        engine_association=data.get("EngineAssociation"),
    )
