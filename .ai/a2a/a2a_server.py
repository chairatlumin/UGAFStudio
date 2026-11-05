#!/usr/bin/env python3
"""A2A Server: Hermes ↔ OpenCode agents (async dispatch).

Exposes all 55 OpenCode game-studio agents as an A2A service.
- a2a_discover: list agents + capabilities
- a2a_send_protocol_task: dispatch a task to a specific agent via opencode run
- a2a_task_status: poll task status (for long-running tasks)
"""
import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

AGENTS_DIR = Path.home() / ".config" / "opencode" / "agents"
REPO = Path("C:/Users/Admin/UGAFStudio")
TASKS: dict[str, dict[str, Any]] = {}

app = FastAPI(title="OpenCode A2A Server", version="1.1.0")


class A2ATask(BaseModel):
    task_id: str
    agent: str
    goal: str
    context: str = ""
    constraints: str = ""
    validation_commands: list[str] = []


class A2AResponse(BaseModel):
    task_id: str
    agent: str
    status: str
    log_path: str = ""
    output: str = ""


def parse_agent_md(path: Path) -> dict[str, Any]:
    """Parse YAML frontmatter from an agent .md file."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    front = text[3:end].strip()
    result: dict[str, Any] = {}
    for line in front.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


@app.get("/a2a_discover")
def a2a_discover() -> dict[str, Any]:
    """List all available agents and their capabilities."""
    agents = []
    for md in sorted(AGENTS_DIR.glob("*.md")):
        info = parse_agent_md(md)
        if info:
            agents.append(
                {
                    "id": md.stem,
                    "description": info.get("description", ""),
                    "model": info.get("model", "default"),
                    "mode": info.get("mode", "subagent"),
                }
            )
    return {"agents": agents, "count": len(agents)}


@app.post("/a2a_send_protocol_task", response_model=A2AResponse)
def a2a_send_protocol_task(task: A2ATask) -> A2AResponse:
    """Dispatch a task to an OpenCode agent (async, returns immediately)."""
    log_dir = REPO / ".ai" / "a2a" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{task.task_id}.log"

    # Build brief
    brief_lines = [
        f"# {task.task_id}",
        "",
        "## Goal",
        task.goal,
    ]
    if task.context:
        brief_lines.extend(["", "## Context", task.context])
    if task.constraints:
        brief_lines.extend(["", "## Constraints", task.constraints])
    if task.validation_commands:
        brief_lines.extend(["", "## Validation", "Run these yourself:"])
        for cmd in task.validation_commands:
            brief_lines.append(f"  {cmd}")
    brief_lines.extend(
        [
            "",
            "## Report",
            "End with `## A2A REPORT` summarizing what you did.",
        ]
    )
    brief = "\\n".join(brief_lines)

    # Escape quotes for shell
    brief_escaped = brief.replace('"', '\\"')

    # Build command
    cmd = (
        f'opencode run --model opencode/nemotron-3.5-lightning-free '
        f'"@{task.agent} {brief_escaped}"'
    )

    # Start in background (non-blocking)
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=open(log_path, "w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            cwd=str(REPO),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        TASKS[task.task_id] = {
            "proc": proc,
            "log_path": str(log_path),
            "agent": task.agent,
            "status": "running",
            "started_at": datetime.now().isoformat(),
        }
        return A2AResponse(
            task_id=task.task_id,
            agent=task.agent,
            status="running",
            log_path=str(log_path),
            output=f"Task {task.task_id} started. Poll /a2a_task_status/{task.task_id}",
        )
    except Exception as e:
        return A2AResponse(
            task_id=task.task_id,
            agent=task.agent,
            status="error",
            log_path=str(log_path),
            output=str(e),
        )


@app.get("/a2a_task_status/{task_id}")
def a2a_task_status(task_id: str) -> dict[str, Any]:
    """Check task status (poll this for long-running tasks)."""
    if task_id not in TASKS:
        return {"status": "unknown", "error": "task not found"}
    task = TASKS[task_id]
    proc = task["proc"]
    if proc.poll() is None:
        # Still running
        log_path = Path(task["log_path"])
        tail = ""
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            tail = "\\n".join(lines[-10:]) if lines else ""
        return {
            "task_id": task_id,
            "status": "running",
            "agent": task["agent"],
            "started_at": task["started_at"],
            "log_tail": tail,
        }
    else:
        # Finished
        returncode = proc.returncode
        log_path = Path(task["log_path"])
        output = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        task["status"] = "completed" if returncode == 0 else "failed"
        return {
            "task_id": task_id,
            "status": task["status"],
            "returncode": returncode,
            "agent": task["agent"],
            "log_path": task["log_path"],
            "output": output[:3000],
        }


@app.get("/a2a_health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4096
    uvicorn.run(app, host="127.0.0.1", port=port)
