"""MCP tool definitions for UGAFStudio QA framework.

These tools expose QA run capabilities to MCP-compatible agents
(e.g., Hermes, Claude Desktop, VS Code).
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psutil

from qa_framework.metrics import CostTracker

ROOT = Path(__file__).resolve().parents[1]


def _resource_base() -> Path:
    """Read-only bundled data (PyInstaller temp dir when frozen, else repo)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return ROOT


def _writable_base() -> Path:
    """Mutable reports/DB beside the exe when frozen, else repo root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return ROOT


def _resource_path(*parts: str) -> Path:
    base = _resource_base()
    candidate = base.joinpath(*parts)
    if candidate.exists():
        return candidate
    return ROOT.joinpath(*parts)


PROFILE_PATH = _resource_path("scripts", "game_profiles.json")
CATALOG_PATH = _resource_path("qa_framework", "testcases", "catalog.json")
LOCAL_CASES_PATH = _writable_base() / "qa_framework" / "testcases" / "local_cases.json"
LIVE_RUNS_DIR = _writable_base() / "reports" / "live_sessions"
QA_REPORTS_DIR = _writable_base() / "reports" / "qa_reports"
FEEDBACK_PATH = _writable_base() / "reports" / "qa_feedback.jsonl"
_LIVE_RUNS: dict[str, dict[str, Any]] = {}
_LIVE_RUNS_LOCK = threading.Lock()


def run_qa_tool(suite_path: str, enable_verification: bool = True) -> dict[str, Any]:
    """Run a QA suite and return structured results.

    Args:
        suite_path: Path to QA suite JSON file
        enable_verification: If True, use verification layer with checkpoints

    Returns:
        dict with keys: name, tests_total, passed, failed, results, recovery_summary
    """
    from qa_framework.suite import load_suite, run_suite

    suite = load_suite(suite_path)
    results = run_suite(suite, enable_verification=enable_verification)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    recovery_summary: dict[str, Any] = {}
    try:
        from qa_framework.suite import last_recovery_tracker

        if last_recovery_tracker is not None:
            recovery_summary = last_recovery_tracker.summary()
    except Exception:
        pass

    return {
        "name": suite.name,
        "tests_total": len(results),
        "passed": passed,
        "failed": failed,
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "duration_ms": r.duration_ms,
                "steps": [
                    {"name": s.name, "passed": s.passed, "message": s.message} for s in r.steps
                ],
            }
            for r in results
        ],
        "recovery_summary": recovery_summary,
    }


def run_robot_suite_tool(
    suite_path: str,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    variables: list[str] | None = None,
    output_dir: str = "",
    timeout_sec: int = 1800,
    dry_run: bool = False,
    profile: str = "",
    game_type: str = "",
    build_id: str = "",
) -> dict[str, Any]:
    """Run a bounded Robot suite and return report paths for local agent callers."""
    suite = Path(suite_path).expanduser()
    if not suite.is_absolute():
        suite = ROOT / suite
    suite = suite.resolve()
    if not suite.exists():
        raise ValueError(f"Robot suite does not exist: {suite}")
    if timeout_sec < 1 or timeout_sec > 7200:
        raise ValueError("timeout_sec must be between 1 and 7200.")

    run_root = Path(output_dir).expanduser() if output_dir else QA_REPORTS_DIR / "robot"
    if not run_root.is_absolute():
        run_root = ROOT / run_root
    run_root = run_root.resolve() / uuid4().hex
    command = (
        [sys.executable, "--qa-worker", "qa_framework.robot.cli"]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-m", "qa_framework.robot.cli"]
    )
    command.extend([str(suite), "--output-dir", str(run_root)])
    for tag in include_tags or []:
        command.extend(["--include", tag])
    for tag in exclude_tags or []:
        command.extend(["--exclude", tag])
    for variable in variables or []:
        command.extend(["--variable", variable])
    if profile.strip():
        command.extend(["--profile", profile.strip()])
    if game_type.strip():
        command.extend(["--game-type", game_type.strip()])
    if build_id.strip():
        command.extend(["--build-id", build_id.strip()])
    if dry_run:
        command.append("--dry-run")

    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "RUN_TIMEOUT",
            "qa_status": "UNASSERTED",
            "suite": str(suite),
            "timeout_sec": timeout_sec,
            "output_dir": str(run_root),
        }

    manifests = (
        sorted(run_root.glob("*/run_manifest.json"), key=lambda item: item.stat().st_mtime_ns)
        if run_root.exists()
        else []
    )
    if not manifests:
        return {
            "status": "START_FAILED",
            "qa_status": "UNASSERTED",
            "suite": str(suite),
            "output_dir": str(run_root),
            "exit_code": completed.returncode,
            "stderr": completed.stderr[-4000:],
        }
    manifest_path = manifests[-1]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    database_sync: dict[str, Any] = {"status": "SKIPPED", "reason": "No profile selected"}
    if profile.strip() and not dry_run and manifest.get("run_id"):
        from app.database.database import QADatabase

        database = QADatabase.for_profile(profile.strip())
        testcase_sources = database.list_testcase_sources(profile.strip())
        cases_by_key = {case_id.casefold(): case_id for case_id in testcase_sources}
        test_results = list(manifest.get("tests", []))
        mapped: dict[str, list[dict[str, Any]]] = {}
        unmapped: list[str] = []
        for test in test_results:
            requested_case = str(test.get("case_id", "")).strip()
            canonical_case = cases_by_key.get(requested_case.casefold()) if requested_case else None
            if not canonical_case:
                unmapped.append(str(test.get("name", "")))
                continue
            mapped.setdefault(canonical_case, []).append(test)
        if (
            test_results
            and not unmapped
            and all(str(test.get("status", "")).upper() == "PASS" for test in test_results)
        ):
            manifest["qa_status"] = "PASS"
        elif any(str(test.get("status", "")).upper() == "FAIL" for test in test_results):
            manifest["qa_status"] = "FAIL"
        else:
            manifest["qa_status"] = "UNASSERTED"
        manifest["database_sync"] = {
            "status": "SYNCED" if test_results and not unmapped else "PARTIAL",
            "profile": profile.strip(),
            "database_path": str(database.path),
            "mapped_test_count": sum(len(group) for group in mapped.values()),
            "unmapped_tests": unmapped,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        database.record_run(manifest, manifest_path)
        evidence_files = [
            str(path.resolve())
            for path in sorted(manifest_path.parent.glob("screenshots/**/*.png"))
            if path.is_file()
        ]
        for case_id, tests_for_case in mapped.items():
            statuses = [str(test.get("status", "UNKNOWN")).upper() for test in tests_for_case]
            case_status = (
                "FAIL"
                if "FAIL" in statuses
                else "PASS"
                if all(s == "PASS" for s in statuses)
                else "UNASSERTED"
            )
            assertions = [
                {
                    "source": "Robot Framework",
                    "test": str(test.get("name", "")),
                    "status": str(test.get("status", "UNKNOWN")),
                    "message": str(test.get("message", "")),
                    "tags": test.get("tags", []),
                }
                for test in tests_for_case
            ]
            database.record_case_result(
                str(manifest["run_id"]),
                case_id,
                case_status,
                observed="; ".join(f"{item['test']}: {item['status']}" for item in assertions),
                assertions=assertions,
                evidence=[
                    str(manifest_path),
                    str(manifest.get("output_xml", "")),
                    str(manifest.get("log_html", "")),
                    str(manifest.get("report_html", "")),
                    *evidence_files,
                ],
            )
        database_sync = manifest["database_sync"]
    return {
        "status": manifest.get("status", "UNKNOWN"),
        "robot_status": manifest.get("suite_status", "UNKNOWN"),
        "qa_status": manifest.get("qa_status", "UNASSERTED"),
        "run_id": manifest.get("run_id", ""),
        "suite": str(suite),
        "test_count": manifest.get("test_count", 0),
        "passed": manifest.get("passed", 0),
        "failed": manifest.get("failed", 0),
        "skipped": manifest.get("skipped", 0),
        "tests": manifest.get("tests", []),
        "dry_run": dry_run,
        "report_html": manifest.get("report_html", ""),
        "output_xml": manifest.get("output_xml", ""),
        "manifest_path": str(manifest_path.resolve()),
        "profile": profile.strip(),
        "database_sync": database_sync,
        "exit_code": completed.returncode,
        "stderr": completed.stderr[-4000:],
    }


def list_checkpoints_tool(suite_path: str) -> dict[str, Any]:
    """List all checkpoints that would be evaluated for a suite without running it."""
    from qa_framework.suite import load_suite

    suite = load_suite(suite_path)
    checkpoints = []
    for case in suite.cases:
        for step_name, _ in case.steps:
            checkpoints.append({"test": case.name, "checkpoint": step_name})
    return {"suite": suite.name, "checkpoints": checkpoints}


def get_cost_tracker_tool() -> dict[str, Any]:
    """Get current cost tracker summary (if a QA run has been executed)."""
    ct = CostTracker()
    return ct.summary()


def get_recovery_tracker_tool() -> dict[str, Any]:
    """Get recovery tracker summary (if a QA run with recovery has been executed)."""
    try:
        from qa_framework.suite import last_recovery_tracker

        if last_recovery_tracker is not None:
            return last_recovery_tracker.summary()
    except Exception:
        pass
    return {"incidents": 0, "recoveries": 0, "recovery_rate": 1.0, "actions": []}


def _read_profiles() -> dict[str, dict[str, Any]]:
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Game profile file must contain a JSON object.")
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def list_game_profiles_tool() -> dict[str, Any]:
    """Return safe, user-configured game metadata without exposing secrets."""
    profiles = _read_profiles()
    return {
        "profiles": [
            {
                "profile": name,
                "game_type": value.get("game_type", "unknown"),
                "strategy": value.get("strategy", "unknown"),
                "window_title": value.get("window_title", ""),
                "requires_eula_ack": bool(value.get("requires_eula_ack", False)),
            }
            for name, value in sorted(profiles.items())
        ]
    }


def list_testcases_tool(game_type: str | None = None) -> dict[str, Any]:
    """Read and optionally genre-filter the local, editable testcase catalog."""
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    cases = list(payload.get("testcases", []))
    if LOCAL_CASES_PATH.is_file():
        local_payload = json.loads(LOCAL_CASES_PATH.read_text(encoding="utf-8"))
        cases.extend(local_payload.get("testcases", []))
    requested = (game_type or "").strip().casefold()
    aliases = {
        "fmv_visual_novel": {"fmv", "fmv narrative", "visual novel", "narrative adventure"},
        "fmv": {"fmv", "fmv narrative"},
        "visual_novel": {"visual novel", "narrative adventure"},
    }
    requested_types = aliases.get(requested, {requested}) if requested else set()
    if requested:
        cases = [
            case
            for case in cases
            if requested == "all games"
            or any(
                any(
                    wanted in str(applies).casefold() or str(applies).casefold() in wanted
                    for wanted in requested_types
                )
                for applies in case.get("applies_to", [])
            )
        ]
    return {
        "schema_version": payload.get("schema_version"),
        "game_type_filter": game_type,
        "count": len(cases),
        "testcases": cases,
    }


def create_testcase_tool(
    case_id: str,
    title: str,
    game_type: str,
    category: str,
    steps: list[str],
    expected: list[str],
    setup: list[str] | None = None,
    priority: str = "P2",
    profile: str = "highschoolblood-demo",
) -> dict[str, Any]:
    """Save a new personal testcase in the local overlay, never to the website."""
    case_id = case_id.strip()
    if not case_id or not title.strip() or not game_type.strip() or not category.strip():
        raise ValueError("case_id, title, game_type, and category are required.")
    if not steps or not expected:
        raise ValueError("At least one step and one expected result are required.")
    if priority not in {"P0", "P1", "P2", "P3"}:
        raise ValueError("priority must be P0, P1, P2, or P3.")

    LOCAL_CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"schema_version": 1, "testcases": []}
    if LOCAL_CASES_PATH.is_file():
        payload = json.loads(LOCAL_CASES_PATH.read_text(encoding="utf-8"))
    cases = payload.setdefault("testcases", [])
    all_cases = list(json.loads(CATALOG_PATH.read_text(encoding="utf-8")).get("testcases", []))
    if LOCAL_CASES_PATH.is_file():
        all_cases.extend(cases)
    if any(str(case.get("id", "")).casefold() == case_id.casefold() for case in all_cases):
        raise ValueError(f"Testcase ID {case_id!r} already exists.")

    case = {
        "id": case_id,
        "title": title.strip(),
        "category": category.strip(),
        "applies_to": [game_type.strip()],
        "priority": priority,
        "setup": [item.strip() for item in (setup or []) if item.strip()],
        "steps": [item.strip() for item in steps if item.strip()],
        "expected": [item.strip() for item in expected if item.strip()],
        "source": "local_personal_case",
        "status": "DRAFT",
    }
    cases.append(case)
    temp_path = LOCAL_CASES_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(LOCAL_CASES_PATH)
    from app.database.database import QADatabase

    database = QADatabase.for_profile(profile)
    profile_data = _read_profiles().get(profile, {})
    database.register_game(
        profile,
        str(profile_data.get("window_title", profile)),
        game_type,
        str(profile_data.get("steam_app_id", "")),
    )
    database.seed_testcases(profile, [case])
    return {"saved": True, "testcase": case, "path": str(LOCAL_CASES_PATH)}


def _supported_types(game_type: str) -> set[str]:
    aliases = {
        "fmv_visual_novel": {
            "fmv",
            "fmv_visual_novel",
            "fmv narrative",
            "visual novel",
            "narrative adventure",
        },
        "visual_novel": {"visual_novel", "visual novel", "narrative adventure"},
    }
    key = (game_type or "unknown").casefold()
    return aliases.get(key, {key})


def _resolve_cases_for_profile(profile: str, case_ids: list[str]) -> list[dict[str, Any]]:
    """Validate explicit case IDs against the profile's genre; no silent reuse."""
    profiles = _read_profiles()
    selected = profiles.get(profile)
    if selected is None:
        raise ValueError(f"Unknown profile {profile!r}; choose one from list_game_profiles.")
    wanted = [c.strip() for c in case_ids if c.strip()]
    if not wanted:
        raise ValueError("Provide at least one explicit case ID for this campaign/run.")
    catalog = {
        str(c.get("id", "")).casefold(): c for c in list_testcases_tool().get("testcases", [])
    }
    supported = _supported_types(str(selected.get("game_type", "unknown")))
    resolved: list[dict[str, Any]] = []
    for cid in wanted:
        case = catalog.get(cid.casefold())
        if case is None:
            raise ValueError(f"Unknown testcase ID {cid!r}.")
        case_types = {str(v).casefold() for v in case.get("applies_to", [])}
        if "all games" not in case_types and not (supported & case_types):
            raise ValueError(f"Testcase {cid!r} does not apply to profile {profile!r}.")
        resolved.append(case)
    return resolved


def _coverage_note(cases: list[dict[str, Any]]) -> str:
    cats = {str(c.get("category", "")).casefold() for c in cases}
    if cats & {
        "branching",
        "fmv_flow",
        "choice",
        "timeout",
        "subtitle_localization",
        "fmv_playback",
        "minigame",
    }:
        return (
            " Coverage: observe and record ALL visible choices and their exact text; "
            "follow only the case-defined option; when a timeout path is selected, "
            "wait for the timeout without input. Frame change or model claims are "
            "observations only, never PASS."
        )
    return " Frame change or model claims are observations only, never PASS."


def delegate_code_task_tool(task: str, timeout_sec: int = 300) -> dict[str, Any]:
    """Delegate an explicit coding task to the local OpenCode CLI (Hermes only).

    OpenCode agents must never call this tool (recursion). Gameplay uses the
    VLM agent, never this tool.
    """
    if os.environ.get("UGAF_DELEGATE_ACTIVE") == "1":
        raise RuntimeError("Recursion blocked: OpenCode must not call delegate_code_task.")
    if not task or not task.strip():
        raise ValueError("Provide an explicit coding task.")
    timeout = max(30, min(int(timeout_sec), 600))
    from tools.opencode_mcp.opencode_client import send_prompt

    guarded = (
        "You are the OpenCode build agent working in C:\\Users\\Admin\\UGAFStudio. "
        "Do NOT call the delegate_code_task MCP tool (no recursive delegation). "
        "Do NOT start gameplay; make only the requested code change.\n\n" + task.strip()
    )
    env_was_set = "UGAF_DELEGATE_ACTIVE" in os.environ
    os.environ["UGAF_DELEGATE_ACTIVE"] = "1"
    try:
        result = send_prompt(prompt=guarded, title="UGAFStudio delegated task", timeout_sec=timeout)
    finally:
        if not env_was_set:
            os.environ.pop("UGAF_DELEGATE_ACTIVE", None)
    response = str(result.get("response", ""))[:4000]
    stderr = str(result.get("stderr", ""))[:2000]
    exit_code = result.get("exit_code")
    return {
        "ok": exit_code == 0,
        "exit_code": result.get("exit_code", 0),
        "response": response,
        "stderr": stderr,
    }


def describe_qa_selection_tool(profile: str) -> dict[str, Any]:
    """Discovery: profile metadata plus available categories and cases for its genre."""
    profiles = _read_profiles()
    if profile not in profiles:
        raise ValueError(f"Unknown profile {profile!r}; choose one from list_game_profiles.")
    selected = profiles[profile]
    cases = [
        c
        for c in list_testcases_tool().get("testcases", [])
        if "all games" in {str(v).casefold() for v in c.get("applies_to", [])}
        or (
            _supported_types(str(selected.get("game_type", "unknown")))
            & {str(v).casefold() for v in c.get("applies_to", [])}
        )
    ]
    categories = sorted({str(c.get("category", "")) for c in cases if c.get("category")})
    return {
        "profile": profile,
        "game_type": selected.get("game_type", "unknown"),
        "strategy": selected.get("strategy", "unknown"),
        "requires_eula_ack": bool(selected.get("requires_eula_ack", False)),
        "categories": categories,
        "cases": [
            {"id": c.get("id"), "title": c.get("title"), "category": c.get("category")}
            for c in cases
        ],
    }


def start_qa_campaign_tool(
    profile: str,
    case_ids: list[str] | None = None,
    categories: list[str] | None = None,
    max_steps: int = 60,
    confirm_gameplay_input: bool = False,
    confirm_eula_cleared: bool = False,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Laya-style campaign: fresh profile + selected categories/cases, one bounded run.

    Requires an explicit profile and selection every call; never reuses a prior
    selection. Validates cases against the profile genre, then starts a single
    bounded live session guided by the first selected case.
    """
    if not (profile or "").strip():
        raise ValueError("Provide a fresh explicit profile for every campaign request.")
    ids = [c.strip() for c in (case_ids or []) if c.strip()]
    cats = [c.strip().casefold() for c in (categories or []) if c.strip()]
    if not ids and not cats:
        raise ValueError("Select at least one category or case ID explicitly.")
    key = idempotency_key.strip()
    if len(key) > 128:
        raise ValueError("idempotency_key must be at most 128 characters.")
    from app.database.database import QADatabase

    database = QADatabase.for_profile(profile)
    profile_config = _read_profiles().get(profile, {})
    if profile not in {game["profile"] for game in database.list_games()}:
        database.register_game(
            profile,
            str(profile_config.get("window_title", profile)),
            str(profile_config.get("game_type", "unknown")),
            str(profile_config.get("steam_app_id", "")),
        )
    if cats:
        available = describe_qa_selection_tool(profile)["cases"]
        available_categories = {str(c.get("category", "")).casefold() for c in available}
        unknown = sorted(set(cats) - available_categories)
        if unknown:
            raise ValueError(f"Unknown categories for profile {profile!r}: {unknown}.")
        ids.extend(
            str(c["id"]) for c in available if str(c.get("category", "")).casefold() in set(cats)
        )
    resolved = _resolve_cases_for_profile(profile, ids)
    campaign_id = uuid4().hex
    selected_case_ids = [str(c.get("id", "")) for c in resolved]
    selected_categories = sorted({str(c.get("category", "")) for c in resolved})
    _reconcile_campaigns(database, profile, 200)
    if key:
        existing = database.get_qa_campaign(profile=profile, idempotency_key=key)
        if existing is not None:
            same_request = (
                existing["selected_case_ids"] == selected_case_ids
                and existing["selected_categories"] == selected_categories
            )
            if not same_request:
                raise ValueError(
                    "idempotency_key was already used for a different testcase selection."
                )
            return {"campaign": existing, "reused": True}
    created = database.create_qa_campaign(
        campaign_id=campaign_id,
        profile=profile,
        idempotency_key=key,
        status="STARTING",
        selected_case_ids=selected_case_ids,
        selected_categories=selected_categories,
        run_ids=[],
        result={"idempotency_key": key},
    )
    if not created:
        if key:
            existing = database.get_qa_campaign(profile=profile, idempotency_key=key)
            if existing is not None:
                if (
                    existing["selected_case_ids"] != selected_case_ids
                    or existing["selected_categories"] != selected_categories
                ):
                    raise ValueError(
                        "idempotency_key was already used for a different testcase selection."
                    )
                return {"campaign": existing, "reused": True}
        raise RuntimeError(
            "Another campaign for this profile is starting or running; no new worker was started."
        )
    first = str(resolved[0].get("id", ""))
    try:
        run = start_live_session_tool(
            profile=profile,
            max_steps=max_steps,
            confirm_gameplay_input=confirm_gameplay_input,
            confirm_eula_cleared=confirm_eula_cleared,
            testcase_id=first,
            case_ids=selected_case_ids,
        )
    except Exception as exc:
        database.update_qa_campaign(
            campaign_id,
            status="BLOCKED",
            finished_at_utc=datetime.now(UTC).isoformat(),
            result={"error": str(exc), "idempotency_key": key},
        )
        raise
    campaign = {
        "campaign_id": campaign_id,
        "profile": profile,
        "selected_case_ids": selected_case_ids,
        "selected_categories": selected_categories,
        "status": str(run.get("status", "RUNNING")),
        "qa_status": str(run.get("qa_status", "UNASSERTED")),
        "run_ids": [str(run.get("run_id", ""))],
    }
    with _LIVE_RUNS_LOCK:
        internal = _LIVE_RUNS.get(str(run.get("run_id", "")))
        if internal is not None:
            internal["campaign"] = campaign
            _save_live_manifest(internal)
            _sync_live_run_database(internal)
            worker_identity = {
                "run_id": str(run.get("run_id", "")),
                "worker_pid": internal.get("process_id"),
                "worker_created_epoch": internal.get("process_created_epoch"),
                "worker_run_dir": internal.get("run_dir", ""),
            }
        else:
            worker_identity = {"run_id": str(run.get("run_id", ""))}
    database.update_qa_campaign(
        campaign_id,
        status=campaign["status"],
        qa_status=campaign["qa_status"],
        finished_at_utc=(run.get("finished_at_utc") if campaign["status"] != "RUNNING" else None),
        run_ids=campaign["run_ids"],
        result={**worker_identity, "idempotency_key": key},
    )
    run["campaign"] = campaign
    return run


def list_qa_campaigns_tool(profile: str = "", limit: int = 50) -> dict[str, Any]:
    """Read durable campaign state for one profile (or all local game profiles)."""
    from app.database.database import QADatabase

    database = QADatabase.for_profile(profile) if profile.strip() else QADatabase()
    campaigns = _reconcile_campaigns(database, profile, limit)
    return {"profile": profile, "count": len(campaigns), "campaigns": campaigns}


def retry_qa_campaign_tool(
    campaign_id: str,
    retry_key: str,
    max_steps: int = 60,
    confirm_gameplay_input: bool = False,
    confirm_eula_cleared: bool = False,
) -> dict[str, Any]:
    """Start one idempotent retry attempt for a stopped/failed campaign."""
    if not campaign_id.strip():
        raise ValueError("campaign_id is required")
    if not retry_key.strip() or len(retry_key.strip()) > 128:
        raise ValueError("retry_key must contain 1..128 characters")
    if not 1 <= max_steps <= 600:
        raise ValueError("max_steps must be between 1 and 600")
    if not confirm_gameplay_input:
        raise ValueError("Set confirm_gameplay_input=true to authorize retry input")

    from app.database.database import QADatabase

    profile = ""
    for candidate in _read_profiles():
        database = QADatabase.for_profile(candidate)
        existing = database.get_qa_campaign(campaign_id)
        if existing is not None:
            profile = candidate
            break
    if not profile:
        raise KeyError(f"Unknown QA campaign {campaign_id!r}.")
    database = QADatabase.for_profile(profile)
    _reconcile_campaigns(database, profile, 200)
    campaign = database.get_qa_campaign(campaign_id)
    if campaign is None:
        raise KeyError(f"Unknown QA campaign {campaign_id!r}.")
    previous_attempt = next(
        (item for item in campaign.get("attempts", []) if item.get("retry_key") == retry_key.strip()),
        None,
    )
    if previous_attempt is not None:
        return {"campaign": campaign, "attempt": previous_attempt, "reused": True}
    if campaign["status"] not in {"INTERRUPTED", "FAILED", "BLOCKED", "STOPPED"}:
        raise ValueError(f"Campaign status {campaign['status']!r} is not retryable.")
    profile_config = _read_profiles().get(profile, {})
    if profile_config.get("requires_eula_ack") and not confirm_eula_cleared:
        raise ValueError("This profile requires user-handled EULA confirmation before retry.")
    case_ids = [str(case_id) for case_id in campaign["selected_case_ids"]]
    resolved = _resolve_cases_for_profile(profile, case_ids)
    resolved_ids = [str(case.get("id", "")) for case in resolved]
    if resolved_ids != case_ids:
        raise ValueError("The original testcase selection no longer resolves exactly; retry blocked.")

    reservation = database.reserve_qa_campaign_attempt(campaign_id, retry_key)
    if not reservation.get("created"):
        if reservation.get("reused"):
            return {
                "campaign": database.get_qa_campaign(campaign_id),
                "attempt": reservation["attempt"],
                "reused": True,
            }
        raise RuntimeError(str(reservation.get("error", "Could not reserve retry attempt.")))
    attempt = reservation["attempt"]
    attempt_id = str(attempt["attempt_id"])
    try:
        run = start_live_session_tool(
            profile=profile,
            max_steps=max_steps,
            confirm_gameplay_input=confirm_gameplay_input,
            confirm_eula_cleared=confirm_eula_cleared,
            testcase_id=case_ids[0],
            case_ids=case_ids,
        )
    except Exception as exc:
        database.update_qa_campaign_attempt(
            campaign_id,
            attempt_id,
            status="BLOCKED",
            result={"error": str(exc)},
        )
        raise

    run_id = str(run.get("run_id", ""))
    campaign_context = {"campaign_id": campaign_id, "attempt_id": attempt_id}
    worker_identity: dict[str, Any] = {"run_id": run_id}
    with _LIVE_RUNS_LOCK:
        internal = _LIVE_RUNS.get(run_id)
        if internal is not None:
            internal["campaign"] = campaign_context
            _save_live_manifest(internal)
            _sync_live_run_database(internal)
            worker_identity.update({
                "worker_pid": internal.get("process_id"),
                "worker_created_epoch": internal.get("process_created_epoch"),
                "worker_run_dir": internal.get("run_dir", ""),
            })
    database.update_qa_campaign_attempt(
        campaign_id,
        attempt_id,
        status=str(run.get("status", "RUNNING")),
        qa_status=str(run.get("qa_status", "UNASSERTED")),
        run_id=run_id,
        result=worker_identity,
    )
    run["campaign"] = database.get_qa_campaign(campaign_id)
    run["attempt"] = database.get_qa_campaign(campaign_id)["attempts"][-1]
    return run


def _campaign_worker_state(campaign: dict[str, Any]) -> bool | None:
    """Return worker liveness only when its saved PID identity can be verified."""
    result = campaign.get("result")
    if not isinstance(result, dict):
        return None
    pid = result.get("worker_pid")
    created_epoch = result.get("worker_created_epoch")
    run_id = str(result.get("run_id", ""))
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or not run_id:
        return None
    try:
        worker = psutil.Process(pid)
        if created_epoch is None:
            return None
        if abs(worker.create_time() - float(created_epoch)) > 2.0:
            return False
        command_line = " ".join(worker.cmdline()).casefold()
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, OSError, ValueError, TypeError):
        return None
    return run_id.casefold() in command_line


def _reconcile_campaigns(database: Any, profile: str, limit: int) -> list[dict[str, Any]]:
    """Turn dead durable workers into explicit interrupted/recovery states."""
    with _LIVE_RUNS_LOCK:
        for run in _LIVE_RUNS.values():
            if not profile or run.get("profile") == profile:
                _public_run(run)
    campaigns = database.list_qa_campaigns(profile, limit)
    active = {"STARTING", "RUNNING", "RECOVERY_REQUIRED"}
    now = datetime.now(UTC)
    for campaign in campaigns:
        if campaign.get("status") not in active:
            continue
        result = campaign.get("result")
        result = result if isinstance(result, dict) else {}
        state = _campaign_worker_state(campaign)
        if state is True:
            continue
        try:
            started_text = str(campaign.get("started_at_utc", "")).replace("Z", "+00:00")
            started = datetime.fromisoformat(started_text)
            age_seconds = (now - started.astimezone(UTC)).total_seconds()
        except (TypeError, ValueError):
            age_seconds = 61.0
        if state is None and age_seconds < 60.0:
            continue
        status = "RECOVERY_REQUIRED" if state is None else "INTERRUPTED"
        note = (
            "Could not verify the saved worker process identity; inspect the run before retrying."
            if state is None
            else (
                "The saved worker process is no longer running; "
                "this campaign was not resumed automatically."
            )
        )
        database.update_qa_campaign(
            str(campaign["campaign_id"]),
            status=status,
            qa_status="UNASSERTED",
            finished_at_utc=now.isoformat() if state is False else None,
            run_ids=campaign.get("run_ids", []),
            result={**result, "recovery_note": note},
        )
    return database.list_qa_campaigns(profile, limit)


def start_live_session_tool(
    profile: str,
    max_steps: int = 30,
    confirm_gameplay_input: bool = False,
    confirm_eula_cleared: bool = False,
    testcase_id: str = "",
    case_ids: list[str] | None = None,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    """Start one bounded profile-specific session with unique local artifacts."""
    profiles = _read_profiles()
    if profile not in profiles:
        raise ValueError(f"Unknown profile {profile!r}; choose one from list_game_profiles.")
    if (
        not testcase_id.strip()
        and not any(c.strip() for c in (case_ids or []))
        and not any(c.strip() for c in (categories or []))
    ):
        raise ValueError("Select testcase IDs or categories for every live session.")
    if not 1 <= max_steps <= 600:
        raise ValueError("max_steps must be between 1 and 600.")
    if not confirm_gameplay_input:
        raise ValueError("Set confirm_gameplay_input=true to authorize live game input.")

    selected = profiles[profile]
    if selected.get("requires_eula_ack") and not confirm_eula_cleared:
        raise ValueError("This profile requires the user to handle its EULA before a run.")

    with _LIVE_RUNS_LOCK:
        if any(
            run["profile"] == profile and run["process"].poll() is None
            for run in _LIVE_RUNS.values()
        ):
            raise RuntimeError(f"A live session for profile {profile!r} is already running.")

        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
        run_dir = LIVE_RUNS_DIR / f"{run_id}_{profile}"
        run_dir.mkdir(parents=True, exist_ok=False)
        trace_path = run_dir / "trace.jsonl"
        report_path = run_dir / "report.html"
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        scenario_path: Path | None = None
        selected_ids = [c.strip() for c in (case_ids or []) if c.strip()]
        resolved: list[dict[str, Any]] = []
        if testcase_id.strip():
            selected_ids.insert(0, testcase_id.strip())
        if categories:
            cats = {c.strip().casefold() for c in categories if c.strip()}
            available = describe_qa_selection_tool(profile)["cases"]
            available_categories = {str(c.get("category", "")).casefold() for c in available}
            unknown = sorted(cats - available_categories)
            if unknown:
                raise ValueError(f"Unknown categories for profile {profile!r}: {unknown}.")
            selected_ids.extend(
                c["id"]
                for c in available
                if str(c.get("category", "")).casefold() in cats and c["id"] not in selected_ids
            )
        seen: set[str] = set()
        selected_ids = [
            c for c in selected_ids if not (c.casefold() in seen or seen.add(c.casefold()))
        ]  # type: ignore[func-returns-value]
        if selected_ids:
            resolved = _resolve_cases_for_profile(profile, selected_ids)
            combined = {
                "id": resolved[0].get("id"),
                "case_ids": [c.get("id") for c in resolved],
                "categories": sorted({str(c.get("category", "")) for c in resolved}),
                "cases": resolved,
                "expected": [e for c in resolved for e in c.get("expected", [])],
                "guidance": (
                    "Follow only the listed case steps; stop and use noop on ambiguity."
                    + _coverage_note(resolved)
                ),
            }
            scenario_path = run_dir / "scenario.json"
            scenario_path.write_text(
                json.dumps(combined, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        if selected.get("requires_eula_ack"):
            if getattr(sys, "frozen", False):
                command = [
                    sys.executable,
                    "--qa-worker",
                    "scripts.fmv_harness",
                    "--profile",
                    profile,
                    "--steps",
                    str(max_steps),
                    "--execute",
                    "--eula-cleared",
                    "--output-dir",
                    str(run_dir / "harness"),
                ]
            else:
                command = [
                    sys.executable,
                    str(ROOT / "scripts" / "fmv_harness.py"),
                    "--profile",
                    profile,
                    "--steps",
                    str(max_steps),
                    "--execute",
                    "--eula-cleared",
                    "--output-dir",
                    str(run_dir / "harness"),
                ]
            if scenario_path is not None:
                command.extend(["--scenario-file", str(scenario_path)])
        elif getattr(sys, "frozen", False):
            command = [
                sys.executable,
                "--qa-worker",
                "scripts.live_gameplay_agent",
                "--profile",
                profile,
                "--max-steps",
                str(max_steps),
                "--trace-path",
                str(trace_path),
                "--report-path",
                str(report_path),
            ]
            if scenario_path is not None:
                command.extend(["--scenario-file", str(scenario_path)])
        else:
            command = [
                sys.executable,
                str(ROOT / "scripts" / "live_gameplay_agent.py"),
                "--profile",
                profile,
                "--max-steps",
                str(max_steps),
                "--trace-path",
                str(trace_path),
                "--report-path",
                str(report_path),
            ]
            if scenario_path is not None:
                command.extend(["--scenario-file", str(scenario_path)])

        stdout_file = stdout_path.open("w", encoding="utf-8")
        stderr_file = stderr_path.open("w", encoding="utf-8")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=stdout_file,
                stderr=stderr_file,
                creationflags=flags,
            )
        except OSError:
            stdout_file.close()
            stderr_file.close()
            raise
        try:
            process_created_epoch = psutil.Process(process.pid).create_time()
        except (psutil.Error, OSError):
            process_created_epoch = None
        _LIVE_RUNS[run_id] = {
            "run_id": run_id,
            "profile": profile,
            "game_type": selected.get("game_type", "unknown"),
            "testcase_id": (selected_ids[0] if selected_ids else None),
            "testcase_ids": list(selected_ids),
            "qa_status": "UNASSERTED",
            "status": "RUNNING",
            "started_at_utc": datetime.now(UTC).isoformat(),
            "run_dir": str(run_dir),
            "trace": str(trace_path),
            "report": str(report_path),
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "manifest": str(run_dir / "run_manifest.json"),
            "game": str(selected.get("window_title", profile)),
            "steam_app_id": str(selected.get("steam_app_id", "")),
            "process_id": process.pid,
            "process_created_epoch": process_created_epoch,
            "process": process,
            "stdout_file": stdout_file,
            "stderr_file": stderr_file,
        }
        _save_live_manifest(_LIVE_RUNS[run_id])
        _sync_live_run_database(_LIVE_RUNS[run_id], resolved)

    return _public_run(_LIVE_RUNS[run_id])


def _save_live_manifest(run: dict[str, Any]) -> None:
    manifest = {
        key: value
        for key, value in run.items()
        if key not in {"process", "stdout_file", "stderr_file"}
    }
    Path(run["manifest"]).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sync_live_run_database(run: dict[str, Any], cases: list[dict[str, Any]] | None = None) -> None:
    """Persist the parent live session and every selected case to its game DB.

    FMV sessions may launch a nested harness with its own run ID. The parent ID
    is what the Workbench/MCP caller receives, so it must be independently
    reportable as well. No visual observation is promoted to PASS here.
    """
    from app.database.database import QADatabase

    profile = str(run.get("profile", "unknown"))
    database = QADatabase.for_profile(profile)
    previous_results = {
        str(result.get("case_id", "")).casefold(): result
        for result in database.list_testcase_results(str(run["run_id"]))
    }
    manifest = {
        "run_id": str(run["run_id"]),
        "profile": profile,
        "game": str(run.get("game", profile)),
        "game_type": str(run.get("game_type", "unknown")),
        "steam_app_id": str(run.get("steam_app_id", "")),
        "status": str(run.get("status", "RUNNING")),
        "qa_status": "UNASSERTED",
        "started_at_utc": str(run.get("started_at_utc", datetime.now(UTC).isoformat())),
        "finished_at_utc": run.get("finished_at_utc"),
        "trace": str(run.get("trace", "")),
        "session_report": str(run.get("report", "")),
        "testcase_id": str((run.get("testcase_ids") or [""])[0]),
        "testcase_ids": list(run.get("testcase_ids", [])),
        "campaign": run.get("campaign"),
        "expected": [],
        "manifest_path": str(run.get("manifest", "")),
    }
    manifest_path = Path(str(run["manifest"]))
    database.record_run(manifest, manifest_path)
    cases_by_id = {str(case.get("id", "")).casefold(): case for case in cases or []}
    for case_id in run.get("testcase_ids", []):
        case = cases_by_id.get(str(case_id).casefold(), {})
        previous = previous_results.get(str(case_id).casefold(), {})
        database.record_case_result(
            str(run["run_id"]),
            str(case_id),
            "UNASSERTED",
            expected=case.get("expected", previous.get("expected", [])),
            observed=(
                f"Run status: {run.get('status', 'RUNNING')}; "
                "selected testcase assertions are not yet mapped to automated evidence."
            ),
            evidence=[
                str(run.get("manifest", "")),
                str(run.get("trace", "")),
                str(run.get("report", "")),
            ],
        )


def _public_run(run: dict[str, Any]) -> dict[str, Any]:
    process: subprocess.Popen[Any] = run["process"]
    exit_code = process.poll()
    if exit_code is not None and run["status"] == "RUNNING":
        run["status"] = "COMPLETED" if exit_code == 0 else "FAILED"
        run["exit_code"] = exit_code
        run["finished_at_utc"] = datetime.now(UTC).isoformat()
        run["stdout_file"].close()
        run["stderr_file"].close()
        harness_root = Path(run["run_dir"]) / "harness"
        manifests = sorted(harness_root.glob("*/run_manifest.json"))
        if manifests:
            manifest_path = manifests[-1]
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = {}
            run["manifest"] = str(manifest_path)
            if manifest.get("trace"):
                run["trace"] = str(manifest["trace"])
            if manifest.get("session_report"):
                run["report"] = str(manifest["session_report"])
            run["qa_status"] = manifest.get("qa_status", "UNASSERTED")
        _save_live_manifest(run)
        _sync_live_run_database(run)
        campaign = run.get("campaign")
        if isinstance(campaign, dict) and campaign.get("campaign_id"):
            from app.database.database import QADatabase

            db = QADatabase.for_profile(str(run["profile"]))
            attempt_id = str(campaign.get("attempt_id", ""))
            if attempt_id:
                db.update_qa_campaign_attempt(
                    str(campaign["campaign_id"]),
                    attempt_id,
                    status=str(run["status"]),
                    qa_status=str(run.get("qa_status", "UNASSERTED")),
                    run_id=str(run["run_id"]),
                    result={"exit_code": run.get("exit_code")},
                )
            else:
                db.update_qa_campaign(
                    str(campaign["campaign_id"]),
                    status=str(run["status"]),
                    qa_status=str(run.get("qa_status", "UNASSERTED")),
                    finished_at_utc=str(run.get("finished_at_utc", "")) or None,
                    result={"run_id": run["run_id"], "exit_code": run.get("exit_code")},
                )
    return {
        key: value
        for key, value in run.items()
        if key not in {"process", "stdout_file", "stderr_file"}
    }


def list_live_runs_tool() -> dict[str, Any]:
    with _LIVE_RUNS_LOCK:
        runs = [_public_run(run) for run in reversed(list(_LIVE_RUNS.values()))]
    return {"count": len(runs), "runs": runs}


def stop_live_session_tool(run_id: str) -> dict[str, Any]:
    with _LIVE_RUNS_LOCK:
        run = _LIVE_RUNS.get(run_id)
        if run is None:
            raise KeyError(f"Unknown live run {run_id!r}.")
        process: subprocess.Popen[Any] = run["process"]
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.send_signal(signal.SIGINT)
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
            run["status"] = "STOPPED"
            campaign = run.get("campaign")
            if isinstance(campaign, dict) and campaign.get("campaign_id"):
                from app.database.database import QADatabase

                db = QADatabase.for_profile(str(run["profile"]))
                attempt_id = str(campaign.get("attempt_id", ""))
                if attempt_id:
                    db.update_qa_campaign_attempt(
                        str(campaign["campaign_id"]),
                        attempt_id,
                        status="STOPPED",
                        qa_status=str(run.get("qa_status", "UNASSERTED")),
                        run_id=run_id,
                        result={"exit_code": process.poll()},
                    )
                else:
                    db.update_qa_campaign(
                        str(campaign["campaign_id"]),
                        status="STOPPED",
                        finished_at_utc=datetime.now(UTC).isoformat(),
                        result={"run_id": run_id, "exit_code": process.poll()},
                    )
        return _public_run(run)


def record_feedback_tool(
    category: str,
    note: str,
    case_id: str = "",
    run_id: str = "",
    profile: str = "",
) -> dict[str, Any]:
    """Append a review note to UGAF's local feedback log; source website stays read-only."""
    if not category.strip() or not note.strip():
        raise ValueError("Both category and note are required.")
    record = {
        "feedback_id": uuid4().hex,
        "category": category.strip(),
        "note": note.strip(),
        "case_id": case_id.strip(),
        "run_id": run_id.strip(),
        "created_at_utc": datetime.now(UTC).isoformat(),
    }
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    from app.database.database import QADatabase

    db = QADatabase.for_profile(profile) if profile.strip() else QADatabase()
    db.record_feedback(
        feedback_id=record["feedback_id"],
        category=record["category"],
        note=record["note"],
        run_id=record["run_id"],
        case_id=record["case_id"],
    )
    return {"saved": True, "feedback": record, "path": str(FEEDBACK_PATH)}


def get_story_database_summary_tool(profile: str = "highschoolblood-demo") -> dict[str, Any]:
    from app.database.database import QADatabase

    return QADatabase.for_profile(profile).story_summary(profile)


def get_fmv_coverage_report_tool(
    profile: str = "highschoolblood-demo", roots: list[str] | None = None
) -> dict[str, Any]:
    """Audit FMV story graph reachability and choice labels without running the game."""
    from app.database.database import QADatabase
    from qa_framework.gameplay_agent.fmv_coverage import build_fmv_coverage_report

    db = QADatabase.for_profile(profile)
    project = db.load_story_project(profile)
    if project is None:
        raise KeyError(f"No story project is imported for profile {profile!r}")
    scene_provenance = {
        str(row["entity_key"]): row
        for row in db.list_source_entity_provenance(profile)
        if row["entity_type"] == "scene"
    }
    return build_fmv_coverage_report(
        profile=profile,
        scenes=project["scenes"],
        testcases=db.list_testcase_sources(profile),
        scene_provenance=scene_provenance,
        roots=roots,
        source_summary=project.get("source_summary", {}),
    )


def export_fmv_coverage_report_tool(
    profile: str = "highschoolblood-demo", destination: str = ""
) -> dict[str, Any]:
    """Write a timestamped FMV source-coverage JSON snapshot and return its hash."""
    report = get_fmv_coverage_report_tool(profile)
    if destination.strip():
        path = Path(destination).expanduser().resolve()
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        path = QA_REPORTS_DIR / _safe_report_name(profile) / f"fmv_coverage_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(body)
    temporary.replace(path)
    return {
        "profile": profile,
        "report_path": str(path),
        "report_sha256": hashlib.sha256(body).hexdigest(),
        "report_size_bytes": len(body),
        "qa_status": "UNASSERTED",
        "summary": report["summary"],
        "report": report,
    }


def search_game_memory_tool(profile: str, query: str, limit: int = 20) -> dict[str, Any]:
    """Search one game's indexed facts, source rows, story, cases, runs, and feedback."""
    from app.database.database import QADatabase
    from app.qa.game_memory_vault import search_game_memory

    db = QADatabase.for_profile(profile)
    results = search_game_memory(db, profile, query, limit)
    return {"profile": profile, "query": query, "count": len(results), "results": results}


def export_game_vault_tool(profile: str, destination: str = "") -> dict[str, Any]:
    """Export a per-game, read-only Obsidian Markdown projection."""
    from pathlib import Path

    from app.database.database import QADatabase
    from app.qa.game_memory_vault import export_game_vault

    return export_game_vault(
        QADatabase.for_profile(profile),
        profile,
        Path(destination).expanduser() if destination.strip() else None,
    )


def list_game_memory_tool(profile: str, query: str = "", limit: int = 50) -> dict[str, Any]:
    """Read persistent facts for one game; memory never crosses game profiles."""
    from app.database.database import QADatabase

    db = QADatabase.for_profile(profile)
    memory = db.list_game_memory(profile)
    needle = query.strip().casefold()
    if needle:
        memory = [
            item
            for item in memory
            if needle in item["memory_key"].casefold()
            or needle in item["category"].casefold()
            or needle in json.dumps(item["value"], ensure_ascii=False).casefold()
        ]
    return {"profile": profile, "count": len(memory), "memory": memory[: max(1, min(limit, 200))]}


def list_source_sheets_tool(profile: str) -> dict[str, Any]:
    """List every imported sheet/document and hyperlink count for a game."""
    from app.database.database import QADatabase

    sheets = QADatabase.for_profile(profile).list_source_sheets(profile)
    return {
        "profile": profile,
        "count": len(sheets),
        "sheets": [
            {
                "source_id": item["source_id"],
                "source_name": item["source_name"],
                "sheet_name": item["sheet_name"],
                "row_count": item["row_count"],
                "column_count": item["column_count"],
                "hyperlinks": item["hyperlinks"],
            }
            for item in sheets
        ],
    }


def read_source_sheet_tool(profile: str, source_id: str, sheet_name: str) -> dict[str, Any]:
    """Read one archived sheet, including its rows and links, by game profile."""
    from app.database.database import QADatabase

    db = QADatabase.for_profile(profile)
    sheet = next(
        (
            item
            for item in db.list_source_sheets(profile, include_rows=True)
            if item["source_id"] == source_id and item["sheet_name"] == sheet_name
        ),
        None,
    )
    if sheet is None:
        raise KeyError(f"No source sheet {source_id!r}/{sheet_name!r} in profile {profile!r}")
    return sheet


def get_source_revision_tool(
    profile: str, source_id: str, revision_hash: str = ""
) -> dict[str, Any]:
    """Return revision rows, entity citations/status, and localization conflicts."""
    from app.database.database import QADatabase

    db = QADatabase.for_profile(profile)
    selected_hash = revision_hash.strip()
    revisions = db.list_source_revisions(profile, source_id)
    if not selected_hash:
        current = next((item for item in revisions if item["status"] == "current"), None)
        selected_hash = str(current["revision_hash"]) if current else ""
    if not selected_hash:
        raise KeyError(f"No source revision {source_id!r} in profile {profile!r}")
    return {
        "profile": profile,
        "source_id": source_id,
        "revision_hash": selected_hash,
        "revisions": revisions,
        "rows": db.list_source_revision_rows(profile, source_id, selected_hash),
        "entities": db.list_source_entity_provenance(profile, source_id=source_id),
        "localization_candidates": db.list_source_localization_candidates(
            profile, source_id=source_id, revision_hash=selected_hash
        ),
    }


def list_unreal_telemetry_tool(
    profile: str, session_id: str = "", limit: int = 100
) -> dict[str, Any]:
    """Read profile-scoped Unreal bridge events without asserting QA status."""
    from app.database.database import QADatabase

    db = QADatabase.for_profile(profile)
    events = db.list_unreal_telemetry_events(profile, session_id, limit)
    return {
        "profile": profile,
        "session_id": session_id,
        "count": len(events),
        "qa_status": "UNASSERTED",
        "events": events,
    }


def get_unreal_performance_report_tool(
    profile: str, session_id: str = "", limit: int = 1000,
    target_fps: float = 60.0, scenario_id: str = "", baseline_session_id: str = "",
) -> dict[str, Any]:
    """Analyze profile-scoped Unreal performance samples without asserting QA."""
    from app.database.database import QADatabase
    from qa_framework.performance_lab import analyze_performance_events, compare_performance_reports

    db = QADatabase.for_profile(profile)
    events = db.list_unreal_telemetry_events(profile, session_id, limit)
    report = analyze_performance_events(
        events,
        profile=profile,
        session_id=session_id,
        target_fps=target_fps,
        scenario_id=scenario_id,
    )
    if baseline_session_id:
        baseline_events = db.list_unreal_telemetry_events(profile, baseline_session_id, limit)
        baseline = analyze_performance_events(
            baseline_events,
            profile=profile,
            session_id=baseline_session_id,
            target_fps=target_fps,
            scenario_id=scenario_id,
        )
        report["comparison"] = compare_performance_reports(baseline, report)
    return report


def list_database_runs_tool(profile: str = "", limit: int = 25) -> dict[str, Any]:
    from app.database.database import QADatabase

    db = QADatabase.for_profile(profile) if profile.strip() else QADatabase()
    runs = db.list_runs(profile=profile, limit=limit)
    return {"count": len(runs), "runs": runs}


def get_testcase_report_tool(run_id: str, profile: str = "") -> dict[str, Any]:
    from app.database.database import PROFILE_DB_DIR, QADatabase

    candidates: list[QADatabase] = []
    if profile.strip():
        candidates.append(QADatabase.for_profile(profile))
    else:
        candidates.append(QADatabase())
        if PROFILE_DB_DIR.is_dir():
            for child in sorted(PROFILE_DB_DIR.glob("qa_*.sqlite3")):
                try:
                    candidates.append(QADatabase(child))
                except Exception:
                    continue
    for database in candidates:
        runs = [run for run in database.list_runs(limit=200) if run["run_id"] == run_id]
        if runs:
            run = runs[0]
            profile_key = str(run.get("profile", profile))
            testcase_sources = database.list_testcase_sources(profile_key)
            source_provenance = {
                str(item["entity_key"]): item
                for item in database.list_source_entity_provenance(profile_key)
                if item["entity_type"] == "testcase"
            }
            results = database.list_testcase_results(run_id)
            for result in results:
                case_id = str(result.get("case_id", ""))
                result["source"] = testcase_sources.get(case_id, {})
                result["source_provenance"] = source_provenance.get(case_id)
                artifacts = []
                for item in result.get("evidence", []):
                    raw = str(item)
                    candidate = Path(raw).expanduser()
                    try:
                        available = candidate.is_file()
                        resolved = str(candidate.resolve()) if available else ""
                    except (OSError, ValueError):
                        available, resolved = False, ""
                    if available:
                        artifacts.append({"value": raw, "status": "available", "path": resolved})
                    elif raw.startswith(("https://", "http://")):
                        artifacts.append({"value": raw, "status": "external"})
                    else:
                        artifacts.append({"value": raw, "status": "missing"})
                result["evidence_artifacts"] = artifacts
            return {
                "run": run,
                "testcase_results": results,
                "testcase_sources": testcase_sources,
                "feedback": database.list_feedback(run_id),
                "qa_status": str(run.get("qa_status", "UNASSERTED")),
            }
    raise KeyError(f"No QA run found for {run_id!r}.")


def _safe_report_name(value: str) -> str:
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in value.strip())
    return safe[:64] or "run"


def _format_list_field(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def _report_output_path(run: dict[str, Any], extension: str) -> Path:
    from app.database.database import sanitize_profile_key

    profile = sanitize_profile_key(str(run.get("profile", "unknown")))
    directory = QA_REPORTS_DIR / profile
    directory.mkdir(parents=True, exist_ok=True)
    run_id = _safe_report_name(str(run.get("run_id", "run")))
    return directory / f"testcase_report_{run_id}.{extension}"


def export_testcase_report_html_tool(run_id: str, profile: str = "") -> dict[str, Any]:
    """Export an offline HTML report from the same canonical stored run payload."""
    from html import escape

    payload = get_testcase_report_tool(run_id, profile)
    run = payload["run"]
    rows: list[str] = []
    for item in payload["testcase_results"]:
        source = item.get("source") or {}
        citations = []
        if source.get("source_sheet"):
            citations.append(str(source["source_sheet"]))
        if source.get("source_row"):
            citations.append(f"row {source['source_row']}")
        provenance = item.get("source_provenance") or {}
        if provenance.get("revision_hash"):
            citations.append(f"revision {provenance['revision_hash']}")
        evidence = []
        for artifact in item.get("evidence_artifacts", []):
            value = escape(str(artifact["value"]))
            if artifact["status"] == "available":
                href = Path(str(artifact["path"])).as_uri()
                evidence.append(f'<a href="{escape(href, quote=True)}">{value}</a>')
            elif artifact["status"] == "external":
                evidence.append(f"<span>{value} (external)</span>")
            else:
                evidence.append(f"<span class=missing>{value} (missing)</span>")
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('case_id', '')))}</td>"
            f"<td>{escape(str(source.get('title') or source.get('choice') or ''))}</td>"
            f"<td>{escape(str(item.get('status', 'UNASSERTED')))}</td>"
            f"<td>{escape(_format_list_field(item.get('expected')))}</td>"
            f"<td>{escape(str(item.get('observed') or '—'))}</td>"
            f"<td>{escape('; '.join(citations) or '—')}</td>"
            f"<td>{'<br>'.join(evidence) or '—'}</td>"
            "</tr>"
        )
    feedback_rows = (
        "".join(
            "<li>"
            f"{escape(str(item.get('category', '')))}: {escape(str(item.get('note', '')))} "
            f"<small>{escape(str(item.get('case_id', '')))} · {escape(str(item.get('created_at_utc', '')))}</small>"
            "</li>"
            for item in payload.get("feedback", [])
        )
        or "<li>No feedback recorded.</li>"
    )
    report = _report_output_path(run, "html")
    if not rows:
        rows.append("<tr><td colspan='7'>No testcase results were recorded.</td></tr>")
    report.write_text(
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        f"<title>QA report {escape(str(run.get('run_id', run_id)))}</title>"
        "<style>body{font:14px system-ui;margin:2rem;color:#172033}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd2dc;"
        "padding:.55rem;text-align:left;vertical-align:top}th{background:#eef1f6}"
        ".missing{color:#a22}small{color:#596579}</style><body>"
        "<h1>QA Test Report</h1>"
        f"<p>Game: {escape(str(run.get('profile', 'unknown')))} · Build: "
        f"{escape(str(run.get('build_id') or 'unknown'))} · Run: "
        f"{escape(str(run.get('run_id', run_id)))} · Status: "
        f"{escape(str(run.get('status', 'UNKNOWN')))} / QA: "
        f"{escape(str(run.get('qa_status', 'UNASSERTED')))}</p>"
        "<p>UNASSERTED and NEEDS_REVIEW are not PASS. Missing evidence is shown explicitly.</p>"
        "<table><thead><tr><th>Case</th><th>Title</th><th>Status</th><th>Expected</th>"
        "<th>Observed</th><th>Source</th><th>Evidence</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table><h2>Feedback</h2><ul>"
        + feedback_rows
        + "</ul></body></html>",
        encoding="utf-8",
    )
    return {
        "html_path": str(report.resolve()),
        "run_id": run.get("run_id"),
        "profile": run.get("profile"),
        "qa_status": run.get("qa_status", "UNASSERTED"),
        "case_count": len(payload["testcase_results"]),
    }


def export_testcase_report_csv_tool(run_id: str, profile: str = "") -> dict[str, Any]:
    """Export testcase, source, run and evidence status rows as UTF-8 CSV."""
    import csv

    payload = get_testcase_report_tool(run_id, profile)
    run = payload["run"]
    report = _report_output_path(run, "csv")
    fields = [
        "profile",
        "build_id",
        "run_id",
        "run_status",
        "qa_status",
        "case_id",
        "title",
        "case_status",
        "expected",
        "observed",
        "source_sheet",
        "source_row",
        "source_revision",
        "evidence",
        "feedback",
    ]
    feedback_by_case: dict[str, list[str]] = {}
    for item in payload.get("feedback", []):
        feedback_by_case.setdefault(str(item.get("case_id", "")).casefold(), []).append(
            f"{item.get('category', '')}: {item.get('note', '')}"
        )
    run_level_feedback = feedback_by_case.get("", [])
    results = payload["testcase_results"] or [{}]
    with report.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in results:
            source = item.get("source") or {}
            provenance = item.get("source_provenance") or {}
            evidence = item.get("evidence_artifacts", [])
            writer.writerow(
                {
                    "profile": run.get("profile", ""),
                    "build_id": run.get("build_id", ""),
                    "run_id": run.get("run_id", run_id),
                    "run_status": run.get("status", "UNKNOWN"),
                    "qa_status": run.get("qa_status", "UNASSERTED"),
                    "case_id": item.get("case_id", ""),
                    "title": source.get("title") or source.get("choice", ""),
                    "case_status": item.get("status", "UNASSERTED"),
                    "expected": _format_list_field(item.get("expected")),
                    "observed": item.get("observed", ""),
                    "source_sheet": source.get("source_sheet", ""),
                    "source_row": source.get("source_row", ""),
                    "source_revision": provenance.get("revision_hash", ""),
                    "evidence": "; ".join(
                        f"{artifact['value']} [{artifact['status']}]" for artifact in evidence
                    ),
                    "feedback": "; ".join(
                        feedback_by_case.get(str(item.get("case_id", "")).casefold(), [])
                        + run_level_feedback
                    ),
                }
            )
    return {
        "csv_path": str(report.resolve()),
        "run_id": run.get("run_id"),
        "profile": run.get("profile"),
        "qa_status": run.get("qa_status", "UNASSERTED"),
        "case_count": len(payload["testcase_results"]),
    }


def export_testcase_report_docx_tool(run_id: str, profile: str = "") -> dict[str, Any]:
    """Export one stored QA run as an editable Word (.docx) report.

    Gathers the same run/results/evidence as ``get_testcase_report`` and
    writes ``reports/qa_reports/<safe-profile>/testcase_report_<safe-run>.docx``.
    """
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is not installed; install it with "
            "'pip install python-docx' (also listed in pyproject dependencies)."
        ) from exc

    payload = get_testcase_report_tool(run_id=run_id, profile=profile)
    run: dict[str, Any] = payload["run"]
    results: list[dict[str, Any]] = list(payload.get("testcase_results", []))
    run_profile = str(run.get("profile", profile or "unknown"))

    from app.database.database import sanitize_profile_key

    safe_profile = sanitize_profile_key(run_profile)
    out_dir = QA_REPORTS_DIR / safe_profile
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"testcase_report_{_safe_report_name(str(run_id))}.docx"

    titles: dict[str, str] = {}
    for case in list_testcases_tool().get("testcases", []):
        titles[str(case.get("id", "")).casefold()] = str(case.get("title", ""))
    from app.database.database import QADatabase

    for case_id, source in (
        QADatabase.for_profile(run_profile).list_testcase_sources(run_profile).items()
    ):
        titles.setdefault(
            case_id.casefold(),
            str(source.get("title") or source.get("choice") or ""),
        )

    doc = Document()
    from docx.shared import Pt, RGBColor

    doc.styles["Normal"].font.name = "Aptos"
    doc.styles["Normal"].font.size = Pt(10)
    for style_name in ("Title", "Heading 1", "Heading 2"):
        doc.styles[style_name].font.name = "Aptos Display"
        doc.styles[style_name].font.color.rgb = RGBColor(0, 0, 0)
    doc.add_heading("QA Test Report / รายงานผลการทดสอบ", 0)
    game = str(run.get("game", run_profile))
    doc.add_paragraph(f"Game / เกม: {game}  |  Profile: {run_profile}")
    doc.add_paragraph(
        f"Build: {run.get('build_id', '') or 'unknown'}  |  Run: {run.get('run_id', run_id)}"
    )
    doc.add_paragraph(
        f"Run status / สถานะรัน: {run.get('status', 'UNKNOWN')}  |  "
        f"QA status / สถานะ QA: {run.get('qa_status', 'UNASSERTED')}"
    )
    doc.add_paragraph(
        f"Started / เริ่ม: {run.get('started_at_utc', '—')}  |  "
        f"Finished / เสร็จ: {run.get('finished_at_utc') or '—'}"
    )
    # ponytail: truthfulness guard lives in the report so UNASSERTED is never read as PASS.
    doc.add_paragraph(
        "Note / หมายเหตุ: QA status is recorded as-is. UNASSERTED and NEEDS_REVIEW "
        "are not PASS; only an explicit PASS means the case passed. "
        "Missing data is shown as —, never invented."
    )
    if run.get("manifest_path"):
        doc.add_paragraph(f"Manifest: {run.get('manifest_path')}")
    if run.get("trace_path"):
        doc.add_paragraph(f"Trace: {run.get('trace_path')}")
    if run.get("report_path"):
        doc.add_paragraph(f"Report: {run.get('report_path')}")

    if not results:
        doc.add_heading("Cases / เคสทดสอบ", level=1)
        doc.add_paragraph(
            "No testcase results were recorded for this run. / ไม่พบบันทึกผลเคสทดสอบสำหรับรันนี้"
        )
    for item in results:
        case_id = str(item.get("case_id", ""))
        title = titles.get(case_id.casefold(), "")
        source = item.get("source") or {}
        title = title or str(source.get("title") or source.get("choice") or "")
        heading = f"{case_id} — {title}" if title else case_id or "case"
        doc.add_heading(heading, level=2)
        doc.add_paragraph(f"Status / สถานะ: {item.get('status', 'UNASSERTED')}")
        doc.add_paragraph(f"Expected / ที่คาดหวัง: {_format_list_field(item.get('expected'))}")
        doc.add_paragraph(f"Observed / ที่พบ: {item.get('observed') or '—'}")
        doc.add_paragraph(f"Assertions: {_format_list_field(item.get('assertions'))}")
        citation = ", ".join(
            value
            for value in (
                str(source.get("source_sheet", "")),
                f"row {source['source_row']}" if source.get("source_row") else "",
            )
            if value
        )
        provenance = item.get("source_provenance") or {}
        if provenance.get("revision_hash"):
            citation = (
                f"{citation}; revision {provenance['revision_hash']}"
                if citation
                else (f"revision {provenance['revision_hash']}")
            )
        doc.add_paragraph(f"Source / แหล่งที่มา: {citation or '—'}")
        evidence = item.get("evidence") or []
        statuses = {
            str(record["value"]): str(record["status"])
            for record in item.get("evidence_artifacts", [])
        }
        evidence_text = (
            "; ".join(f"{value} [{statuses.get(str(value), 'unverified')}]" for value in evidence)
            if isinstance(evidence, list)
            else str(evidence)
        )
        doc.add_paragraph(f"Evidence / หลักฐาน: {evidence_text or '—'}")

    doc.add_heading("Feedback / ข้อเสนอแนะ", level=1)
    feedback = payload.get("feedback", [])
    if not feedback:
        doc.add_paragraph("No feedback recorded. / ยังไม่มี feedback")
    for item in feedback:
        doc.add_paragraph(
            f"{item.get('category', '')} [{item.get('case_id', '')}]: "
            f"{item.get('note', '')} ({item.get('created_at_utc', '')})",
            style="List Bullet",
        )

    doc.save(out_path)
    return {
        "docx_path": str(out_path.resolve()),
        "run_id": str(run.get("run_id", run_id)),
        "profile": run_profile,
        "run_status": str(run.get("status", "UNKNOWN")),
        "qa_status": str(run.get("qa_status", "UNASSERTED")),
        "case_count": len(results),
    }
