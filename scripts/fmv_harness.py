from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.database import QADatabase
from scripts.session_report import build_report as build_session_report


PROFILE_PATH = ROOT / "scripts" / "game_profiles.json"
if getattr(sys, "_MEIPASS", None):
    _bundled = Path(sys._MEIPASS) / "scripts" / "game_profiles.json"
    if _bundled.is_file():
        PROFILE_PATH = _bundled
DEFAULT_PROFILE = "highschoolblood-demo"
if getattr(sys, "frozen", False):
    DEFAULT_OUTPUT = Path(sys.executable).resolve().parent / "reports" / "fmv_harness"
else:
    DEFAULT_OUTPUT = ROOT / "reports" / "fmv_harness"


def _load_profile(name: str) -> dict[str, Any]:
    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile = profiles.get(name)
    if not isinstance(profile, dict):
        raise ValueError(f"Unknown profile {name!r}; available profiles: {', '.join(profiles)}")
    return profile


def _window_titles() -> list[str]:
    if sys.platform != "win32":
        return []
    import ctypes
    import ctypes.wintypes as wt

    titles: list[str] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def callback(hwnd: wt.HWND, _: wt.LPARAM) -> bool:
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        titles.append(buffer.value)
        return True

    ctypes.windll.user32.EnumWindows(callback, 0)
    return titles


def _steam_build_id(executable: Path, app_id: str) -> str | None:
    try:
        manifest = executable.parents[2] / f"appmanifest_{app_id}.acf"
        text = manifest.read_text(encoding="utf-8", errors="replace")
    except (IndexError, OSError):
        return None
    match = re.search(r'"buildid"\s+"(\d+)"', text, re.IGNORECASE)
    return match.group(1) if match else None


def _check_vlm(base_url: str, model: str, timeout: float) -> tuple[bool, str]:
    if not model:
        return False, "No vision model is configured; set VLM_MODEL or pass --model."
    url = f"{base_url.rstrip('/')}/models"
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, ValueError) as exc:
        return False, f"VLM endpoint unavailable at {url}: {exc}"
    model_ids = {
        str(entry.get("id", ""))
        for entry in payload.get("data", [])
        if isinstance(entry, dict)
    }
    if model_ids and model not in model_ids:
        available = ", ".join(sorted(model_ids))
        return False, f"Model {model!r} is not listed by endpoint; available: {available}"
    return True, f"VLM endpoint reachable; requested model={model}"


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_preflight_report(manifest: dict[str, Any]) -> None:
    report_path = Path(manifest["session_report"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    check_rows = "\n".join(
        "<tr><td>{}</td><td class='{}'>{}</td></tr>".format(
            escape(name.replace("_", " ").title()),
            "pass" if result else "blocked",
            "READY" if result else "BLOCKED",
        )
        for name, result in manifest["checks"].items()
    )
    blockers = ", ".join(escape(str(item)) for item in manifest["blockers"]) or "none"
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>FMV QA Preflight</title>
<style>body{{font:16px system-ui;margin:2rem;background:#111820;color:#e8eef2}}
table{{border-collapse:collapse;width:100%;max-width:800px}}th,td{{padding:.7rem;border:1px solid #47545d;text-align:left}}
.pass{{color:#72d6a0}}.blocked{{color:#ff817c}}code{{color:#b8d9ff}}</style></head>
<body><h1>High School Blood Demo · Preflight</h1>
<p>Run: <code>{escape(str(manifest['run_id']))}</code> · Build: <code>{escape(str(manifest.get('steam_build_id') or 'unknown'))}</code></p>
<p>Status: <strong>{escape(str(manifest['status']))}</strong> · Test execution: NOT RUN · QA status: UNASSERTED</p>
<table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>{check_rows}</tbody></table>
<p>Blockers: {blockers}</p><p>VLM: {escape(str(manifest['vlm']['status']))}</p>
</body></html>"""
    report_path.write_text(html, encoding="utf-8")


def _write_trace_summary(trace_path: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    if trace_path.exists():
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    entries.append(record)
    rewards = [float(entry.get("reward", 0.0)) for entry in entries]
    return {
        "trace_entries": len(entries),
        "unique_states": len({entry.get("sig", "") for entry in entries}),
        "visual_change_steps": sum(reward > 0 for reward in rewards),
        "heuristic_reward_sum": sum(rewards),
        "qa_status": "UNASSERTED",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe preflight and bounded run harness for High School Blood Demo."
    )
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--steps", type=int, default=60)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("VLM_BASE_URL", "http://127.0.0.1:1234/v1"),
    )
    parser.add_argument("--model", default=os.environ.get("VLM_MODEL", "qwen/qwen2.5-vl-7b"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--scenario-file", type=Path)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Start the bounded gameplay agent after preflight.",
    )
    parser.add_argument(
        "--eula-cleared",
        action="store_true",
        help="Confirm the user handled the Demo EULA in-game; never accept it in automation.",
    )
    parser.add_argument(
        "--timeout", type=float, default=3.0, help="VLM preflight timeout in seconds."
    )
    return parser


def _resolve_cli_paths(args: argparse.Namespace) -> None:
    """Anchor user paths before frozen workers switch to PyInstaller's temp cwd."""
    args.output_dir = args.output_dir.expanduser().resolve()
    if args.scenario_file is not None:
        args.scenario_file = args.scenario_file.expanduser().resolve()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _resolve_cli_paths(args)
    if args.steps < 1 or args.steps > 600:
        raise SystemExit("--steps must be between 1 and 600.")

    profile = _load_profile(args.profile)
    executable = Path(profile.get("exe_path", ""))
    window_hint = str(profile.get("window_title", ""))
    app_id = str(profile.get("steam_app_id", ""))
    windows = [
        title for title in _window_titles() if window_hint.casefold() in title.casefold()
    ]
    checks = {
        "correct_demo_profile": args.profile == DEFAULT_PROFILE and app_id == "5173380",
        "executable_present": executable.is_file(),
        "demo_window_present": bool(windows),
    }
    vlm_ok, vlm_message = _check_vlm(args.base_url, args.model, args.timeout)
    checks["vlm_ready"] = vlm_ok
    if profile.get("requires_eula_ack"):
        checks["user_cleared_eula"] = args.eula_cleared

    blockers = [name for name, passed in checks.items() if not passed]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = args.output_dir / f"{run_id}_{args.profile}"
    trace_path = run_dir / "trace.jsonl"
    report_path = run_dir / "session_report.html"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "profile": args.profile,
        "game": "High School Blood Demo",
        "steam_app_id": app_id,
        "steam_build_id": _steam_build_id(executable, app_id),
        "executable": str(executable),
        "window_title_hint": window_hint,
        "window_titles": windows,
        "runner": str(ROOT / "scripts" / "live_gameplay_agent.py"),
        "vlm": {"base_url": args.base_url, "model": args.model, "status": vlm_message},
        "max_steps": args.steps,
        "checks": checks,
        "blockers": blockers,
        "status": "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_READY",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "trace": str(trace_path),
        "session_report": str(report_path),
        "qa_status": "UNASSERTED",
    }
    if blockers or not args.execute:
        manifest["finished_at_utc"] = datetime.now(UTC).isoformat()
    if args.scenario_file is not None:
        scenario = json.loads(args.scenario_file.read_text(encoding="utf-8"))
        manifest["testcase_id"] = str(scenario.get("id", scenario.get("case_id", "")))
        manifest["testcase_ids"] = list(scenario.get("case_ids", [manifest["testcase_id"]]))
        manifest["categories"] = list(scenario.get("categories", []))
        manifest["expected"] = scenario.get("expected", [])
    database = QADatabase.for_profile(args.profile)
    manifest["database_path"] = str(database.path)
    manifest_path = run_dir / "run_manifest.json"
    _atomic_json(manifest_path, manifest)
    _write_preflight_report(manifest)
    database.record_run(manifest, manifest_path)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if blockers:
        print(f"Harness blocked; details: {run_dir / 'run_manifest.json'}")
        return 2 if args.execute else 0
    if not args.execute:
        print(f"Preflight ready; pass --execute to start a bounded run. Artifacts: {run_dir}")
        return 0

    if getattr(sys, "frozen", False):
        agent_args = [
            sys.executable,
            "--qa-worker",
            "scripts.live_gameplay_agent",
            "--profile",
            args.profile,
            "--max-steps",
            str(args.steps),
            "--base-url",
            args.base_url,
            "--model",
            args.model,
            "--trace-path",
            str(trace_path),
            "--report-path",
            str(report_path),
        ]
    else:
        agent_args = [
            sys.executable,
            str(ROOT / "scripts" / "live_gameplay_agent.py"),
            "--profile",
            args.profile,
            "--max-steps",
            str(args.steps),
            "--base-url",
            args.base_url,
            "--model",
            args.model,
            "--trace-path",
            str(trace_path),
            "--report-path",
            str(report_path),
        ]
    if args.scenario_file is not None:
        agent_args.extend(["--scenario-file", str(args.scenario_file)])
    manifest["status"] = "RUNNING"
    _atomic_json(run_dir / "run_manifest.json", manifest)
    (run_dir / "stdout.log").write_text("", encoding="utf-8")
    (run_dir / "stderr.log").write_text("", encoding="utf-8")
    start = time.monotonic()
    try:
        child_env = os.environ.copy()
        existing_pythonpath = child_env.get("PYTHONPATH", "")
        child_env["PYTHONPATH"] = (
            str(ROOT)
            if not existing_pythonpath
            else str(ROOT) + os.pathsep + existing_pythonpath
        )
        completed = subprocess.run(
            agent_args,
            cwd=ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        (run_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
        manifest["exit_code"] = completed.returncode
        manifest["status"] = "RUN_COMPLETE_UNASSERTED" if completed.returncode == 0 else "RUN_ERROR"
    except OSError as exc:
        manifest["status"] = "RUN_ERROR"
        manifest["error"] = str(exc)
    manifest["duration_seconds"] = round(time.monotonic() - start, 3)
    manifest["finished_at_utc"] = datetime.now(UTC).isoformat()
    manifest.update(_write_trace_summary(trace_path))
    if trace_path.is_file() and trace_path.stat().st_size:
        try:
            build_session_report(trace_path, report_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            manifest["report_error"] = str(exc)
    _atomic_json(run_dir / "run_manifest.json", manifest)
    database.record_run(manifest, manifest_path)
    print(f"Run finished ({manifest['status']}); review {run_dir / 'run_manifest.json'}")
    return 0 if manifest["status"] == "RUN_COMPLETE_UNASSERTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
