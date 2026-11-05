from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_qa_team import ROOT, check_runtime, validate_team


def test_repository_qa_team_contract_is_complete() -> None:
    assert validate_team(ROOT) == []


def test_validator_finds_missing_specialist_file(tmp_path: Path) -> None:
    roster = tmp_path / "qa_framework/orchestration/specialists.json"
    roster.parent.mkdir(parents=True)
    data = json.loads(
        (ROOT / "qa_framework/orchestration/specialists.json").read_text(encoding="utf-8")
    )
    data["roles"] = [data["roles"][0]]
    roster.write_text(json.dumps(data), encoding="utf-8")
    orchestrator = tmp_path / ".opencode/agents/fmv-qa-orchestrator.md"
    orchestrator.parent.mkdir(parents=True)
    orchestrator.write_text("---\nmode: primary\n---", encoding="utf-8")
    command = tmp_path / ".opencode/commands/qa-campaign.md"
    command.parent.mkdir(parents=True)
    command.write_text("campaign", encoding="utf-8")
    skill = tmp_path / ".hermes/skills/game-qa-orchestra/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("skill", encoding="utf-8")

    errors = validate_team(tmp_path)
    assert any("Missing OpenCode specialist" in error for error in errors)


def test_runtime_check_is_read_only_and_reports_both_tools() -> None:
    status = check_runtime()
    assert set(status) == {"opencode", "hermes", "opencode_agents", "hermes_skill"}
