from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEAM_FILE = ROOT / "qa_framework" / "orchestration" / "specialists.json"


def validate_team(root: Path = ROOT) -> list[str]:
    """Validate role contracts and their OpenCode/Hermes entry points."""
    errors: list[str] = []
    team_path = root / "qa_framework" / "orchestration" / "specialists.json"
    try:
        team: dict[str, Any] = json.loads(team_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Cannot load specialist roster: {exc}"]

    roles = team.get("roles")
    if not isinstance(roles, list) or not roles:
        return ["Specialist roster must contain at least one role."]

    ids: set[str] = set()
    for role in roles:
        if not isinstance(role, dict):
            errors.append("Every role must be an object.")
            continue
        role_id = role.get("id")
        if not isinstance(role_id, str) or not re.fullmatch(r"[a-z0-9-]+", role_id):
            errors.append(f"Invalid role id: {role_id!r}")
            continue
        if role_id in ids:
            errors.append(f"Duplicate role id: {role_id}")
        ids.add(role_id)
        agent_name = role.get("agent", f"specialists/{role_id}")
        valid_agent_name = isinstance(agent_name, str) and re.fullmatch(
            r"[a-z0-9-]+(/[a-z0-9-]+)*", agent_name
        )
        if not valid_agent_name:
            errors.append(f"Invalid OpenCode agent name for {role_id}: {agent_name!r}")
            continue
        agent_file = root / ".opencode" / "agents" / f"{agent_name}.md"
        if not agent_file.is_file():
            errors.append(f"Missing OpenCode specialist definition: {agent_file.relative_to(root)}")
        elif "mode: subagent" not in agent_file.read_text(encoding="utf-8"):
            errors.append(f"Specialist must be a subagent: {agent_file.relative_to(root)}")
        if not role.get("output") or not role.get("input"):
            errors.append(f"Role {role_id} must define inputs and an output contract.")

    orchestrator = root / ".opencode" / "agents" / "fmv-qa-orchestrator.md"
    if not orchestrator.is_file():
        errors.append("Missing .opencode/agents/fmv-qa-orchestrator.md")
    command = root / ".opencode" / "commands" / "qa-campaign.md"
    if not command.is_file():
        errors.append("Missing .opencode/commands/qa-campaign.md")
    skill = root / ".hermes" / "skills" / "game-qa-orchestra" / "SKILL.md"
    if not skill.is_file():
        errors.append("Missing project-local Hermes game-qa-orchestra skill.")
    return errors


def check_runtime() -> dict[str, str]:
    """Report installed agent CLIs without starting a session or a game."""
    results: dict[str, str] = {}
    for name, args in (("opencode", ["--version"]), ("hermes", ["--version"])):
        executable = shutil.which(name)
        if not executable:
            results[name] = "MISSING"
            continue
        try:
            proc = subprocess.run(
                [executable, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            results[name] = f"ERROR: {exc}"
            continue
        output = (proc.stdout or proc.stderr).strip().splitlines()
        results[name] = (
            output[0] if proc.returncode == 0 and output else f"ERROR: exit {proc.returncode}"
        )
    opencode = shutil.which("opencode")
    if opencode:
        try:
            proc = subprocess.run(
                [opencode, "agent", "list"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
                cwd=ROOT,
            )
            configured = (proc.stdout or "") + (proc.stderr or "")
            expected_agents = [
                role.get("agent", f"specialists/{role['id']}")
                for role in json.loads(TEAM_FILE.read_text(encoding="utf-8"))["roles"]
            ] + ["fmv-qa-orchestrator"]
            missing = [name for name in expected_agents if name not in configured]
            results["opencode_agents"] = (
                f"ERROR: missing {', '.join(missing)}"
                if proc.returncode != 0 or missing
                else f"OK: {len(expected_agents)} configured agents"
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            results["opencode_agents"] = f"ERROR: {exc}"
    else:
        results["opencode_agents"] = "MISSING: opencode CLI"
    hermes = shutil.which("hermes")
    if hermes:
        try:
            proc = subprocess.run(
                [hermes, "skills", "list", "--source", "local"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
                cwd=ROOT,
            )
            results["hermes_skill"] = (
                "OK: game-qa-orchestra"
                if proc.returncode == 0
                and "game-qa-orchestra" in ((proc.stdout or "") + (proc.stderr or ""))
                else "ERROR: project skill is not visible to Hermes"
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            results["hermes_skill"] = f"ERROR: {exc}"
    else:
        results["hermes_skill"] = "MISSING: hermes CLI"
    return results


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        description="Validate UGAF OpenCode/Hermes QA specialist setup."
    )
    parser.add_argument(
        "--check-runtime", action="store_true", help="Also read local CLI versions."
    )
    args = parser.parse_args(argv)
    errors = validate_team()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    role_count = len(json.loads(TEAM_FILE.read_text(encoding="utf-8"))["roles"])
    print(f"OK: {role_count} specialist roles and both entry points are present.")
    if args.check_runtime:
        runtime = check_runtime()
        for name, status in runtime.items():
            print(f"{name}: {status}")
        return (
            0
            if all(not status.startswith(("MISSING", "ERROR")) for status in runtime.values())
            else 2
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
