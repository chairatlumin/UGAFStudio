from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def test_campaign_stops_and_preserves_manifest_after_step_failure(tmp_path: Path) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell is required for the campaign launcher integration test")

    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "hsb_campaign.ps1"
    fake_python = tmp_path / "fake-python.cmd"
    fake_python.write_text(
        "@echo off\r\necho simulated failure\r\nexit /b 9\r\n", encoding="ascii"
    )
    output_root = tmp_path / "campaign-output"
    env = os.environ.copy()
    env["UGAF_FMV_CAMPAIGN_OUTPUT_DIR"] = str(output_root)

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Python",
            str(fake_python),
            "-Only",
            "english-english-on",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    campaign_manifest_path = next(output_root.glob("*/campaign_manifest.json"))
    campaign_manifest = json.loads(campaign_manifest_path.read_text(encoding="utf-8-sig"))
    run_manifest_path = campaign_manifest_path.parent / "subs-english_choice-english_visual-on" / "run_manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8-sig"))

    assert campaign_manifest["status"] == "FAILED"
    assert campaign_manifest["qa_status"] == "UNASSERTED"
    assert run_manifest["status"] == "FAILED"
    assert len(run_manifest["steps"]) == 1
    assert run_manifest["steps"][0]["exit_code"] == 9
    assert run_manifest["steps"][0]["log"] == "fullscreen.log"
    assert (run_manifest_path.parent / "fullscreen.log").read_text().strip() == "simulated failure"
