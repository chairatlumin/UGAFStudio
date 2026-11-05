from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from qa_framework.gameplay_agent.fmv_coverage import build_fmv_coverage_report
from qa_framework.mcp_tools import export_fmv_coverage_report_tool


def test_coverage_report_audits_left_branch_options_and_timeout_without_claiming_pass() -> None:
    option_scenes = ["Saw", "NailGun", "Gun", "Bhudha", "NoChoice"]
    scenes = {
        "Root": {"outgoing": [{"target": "Left"}, {"target": "Right"}]},
        "Left": {"outgoing": [{"target": scene} for scene in option_scenes]},
        "Right": {"outgoing": [{"target": "MissingScene"}]},
        **{scene: {"outgoing": []} for scene in [*option_scenes, "Disconnected"]},
    }
    testcases = {
        "CASE-LEFT": {"scene_id": "Left", "choice": "Go Left"},
        "CASE-RIGHT": {"scene_id": "Right", "choice": "Go Right"},
        "CASE-SAW": {"scene_id": "Saw", "choice": "Chainsaw"},
        "CASE-NAIL": {"scene_id": "NailGun", "choice": "Nail Gun"},
        "CASE-GUN": {"scene_id": "Gun", "choice": "Shotgun"},
        "CASE-BHUDHA": {"scene_id": "Bhudha", "choice": "Buddha Statue"},
        "CASE-TIMER": {"scene_id": "NoChoice", "choice": "Choose Nothing"},
        "CASE-ORPHAN": {"scene_id": "Disconnected", "choice": ""},
    }

    report = build_fmv_coverage_report(
        profile="fixture", scenes=scenes, testcases=testcases, roots=["Root"]
    )

    assert report["summary"]["scene_count"] == 9
    assert report["summary"]["reachable_scene_count"] == 8
    assert report["summary"]["unreachable_scene_count"] == 1
    assert report["summary"]["source_graph_status"] == "PARTIAL"
    assert report["summary"]["qa_status"] == "UNASSERTED"
    assert report["summary"]["source_active_scene_count"] == 0
    assert report["summary"]["configured_root_source_reachable_count"] == 0
    assert report["summary"]["provenance_status"] == "MISMATCH"
    assert report["root_source_status"] == {"Root": "unowned"}
    points = {point["scene_id"]: point for point in report["choice_points"]}
    assert points["Left"]["option_count"] == 5
    assert {option["candidate_labels"][0] for option in points["Left"]["options"]} == {
        "Chainsaw",
        "Nail Gun",
        "Shotgun",
        "Buddha Statue",
        "Choose Nothing",
    }
    timer = next(option for option in points["Left"]["options"] if option["target"] == "NoChoice")
    assert timer["timeout_candidate"] is True
    assert timer["label_status"] == "candidate_unverified"
    assert timer["execution_status"] == "NOT_RUN"
    assert report["summary"]["missing_target_edge_count"] == 1


def test_coverage_report_requires_known_roots() -> None:
    with pytest.raises(ValueError, match="missing from the profile graph"):
        build_fmv_coverage_report(
            profile="fixture", scenes={"Root": {"outgoing": []}}, testcases={}, roots=["Unknown"]
        )


def test_active_source_subgraph_is_reported_separately_from_unowned_and_stale_rows() -> None:
    report = build_fmv_coverage_report(
        profile="fixture",
        scenes={"A": {"outgoing": [{"target": "B"}]}, "B": {"outgoing": []}, "Old": {"outgoing": []}},
        testcases={},
        roots=["Old"],
        scene_provenance={"A": {"status": "active"}, "B": {"status": "active"}, "Old": {"status": "stale"}},
    )

    assert report["summary"]["source_active_scene_count"] == 2
    assert report["summary"]["source_stale_scene_count"] == 1
    assert report["summary"]["unowned_scene_count"] == 0
    assert report["summary"]["configured_root_source_reachable_count"] == 0
    assert report["summary"]["source_graph_reachable_scene_count"] == 2
    assert report["source_graph_root_candidates"] == ["A"]
    assert report["summary"]["provenance_status"] == "MISMATCH"


def test_export_coverage_report_is_atomic_hashed_and_stays_unasserted(
    tmp_path: Path, monkeypatch
) -> None:
    import qa_framework.mcp_tools as mcp_tools

    payload = {"profile": "fixture", "summary": {"qa_status": "UNASSERTED"}}
    monkeypatch.setattr(mcp_tools, "get_fmv_coverage_report_tool", lambda profile: payload)
    destination = tmp_path / "coverage.json"

    result = export_fmv_coverage_report_tool("fixture", str(destination))

    raw = destination.read_bytes()
    assert json.loads(raw) == payload
    assert result["report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["qa_status"] == "UNASSERTED"
    assert not destination.with_suffix(".json.tmp").exists()
