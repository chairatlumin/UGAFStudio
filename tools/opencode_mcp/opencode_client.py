import json
import os
import subprocess
import urllib.request
from typing import Any

OPENCODE_URL = "http://127.0.0.1:4096"
OPENCODE_PATH = r"C:\Users\Admin\AppData\Roaming\npm\opencode.cmd"
DEFAULT_TIMEOUT = 60


def health() -> dict[str, Any]:
    """Check the local OpenCode HTTP server health."""

    with urllib.request.urlopen(
        f"{OPENCODE_URL}/global/health",
        timeout=15,
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def send_prompt(
    prompt: str,
    session_id: str | None = None,
    new_session: bool = False,
    title: str = "UGAFStudio MCP Session",
    timeout_sec: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Send a prompt directly to the OpenCode Windows CMD launcher."""

    if not prompt or not prompt.strip():
        raise ValueError("OpenCode prompt cannot be empty")

    cwd = os.getcwd()

    command = [
        OPENCODE_PATH,
        "run",
        prompt,
    ]

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )

    except FileNotFoundError as exc:
        raise RuntimeError(f"OpenCode executable was not found:\n{OPENCODE_PATH}") from exc

    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"OpenCode CLI did not complete within {timeout_sec} seconds") from exc

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()

    if completed.returncode != 0:
        raise RuntimeError(
            "OpenCode CLI failed.\n"
            f"ExitCode: {completed.returncode}\n"
            f"STDOUT:\n{stdout}\n"
            f"STDERR:\n{stderr}"
        )

    lines = stdout.splitlines()
    response_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("> "):
            continue

        if stripped.startswith("build · "):
            continue

        response_lines.append(line)

    response = "\n".join(response_lines).strip()

    return {
        "session_id": session_id,
        "message_id": None,
        "model": "opencode CLI",
        "provider": "opencode",
        "agent": "build",
        "mode": "build",
        "finish": "stop",
        "response": response,
        "stderr": stderr,
        "exit_code": completed.returncode,
    }
