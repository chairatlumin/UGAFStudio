from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qa_framework.robot.cli import _artifact_inventory, main


def test_artifact_inventory_hashes_robot_reports_and_screenshots(tmp_path: Path) -> None:
    (tmp_path / "output.xml").write_bytes(b"<robot />")
    (tmp_path / "report.html").write_bytes(b"report")
    screenshot = tmp_path / "screenshots" / "choice.png"
    screenshot.parent.mkdir()
    screenshot.write_bytes(b"frame")
    (tmp_path / "run_manifest.json").write_text("{}", encoding="utf-8")

    artifacts = _artifact_inventory(tmp_path)

    assert [item["path"] for item in artifacts] == [
        "output.xml",
        "report.html",
        "screenshots/choice.png",
    ]
    assert artifacts[0]["type"] == "robot_xml"
    assert artifacts[1]["type"] == "robot_html"
    assert artifacts[2]["type"] == "screenshot"
    assert artifacts[2]["sha256"] == hashlib.sha256(b"frame").hexdigest()
    assert artifacts[2]["size_bytes"] == 5


def test_robot_dry_run_manifest_contains_hashed_outputs(tmp_path: Path) -> None:
    suite = tmp_path / "smoke.robot"
    suite.write_text(
        "*** Test Cases ***\n" "One Test\n" "    Log    validates dry-run output\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "runs"

    assert main([str(suite), "--output-dir", str(output_root), "--dry-run"]) == 0

    run_dir = next(output_root.iterdir())
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    artifacts = {item["path"]: item for item in manifest["artifacts"]}
    assert manifest["status"] == "DRY_RUN"
    assert manifest["qa_status"] == "UNASSERTED"
    for filename in ("output.xml", "log.html", "report.html"):
        assert filename in artifacts
        assert artifacts[filename]["sha256"] == hashlib.sha256(
            (run_dir / filename).read_bytes()
        ).hexdigest()
