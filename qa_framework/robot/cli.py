"""Command line entry point for UGAF Robot Framework suites."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _suite_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _artifact_inventory(run_dir: Path) -> list[dict[str, Any]]:
    """Hash report and evidence files relative to their immutable run folder."""
    artifacts: list[dict[str, Any]] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "run_manifest.json" or path.name.endswith(".tmp"):
            continue
        relative = path.relative_to(run_dir).as_posix()
        if relative.startswith("screenshots/"):
            artifact_type = "screenshot"
        elif path.name == "output.xml":
            artifact_type = "robot_xml"
        elif path.name in {"log.html", "report.html"}:
            artifact_type = "robot_html"
        else:
            artifact_type = "evidence"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts.append(
            {
                "type": artifact_type,
                "path": relative,
                "sha256": digest,
                "size_bytes": path.stat().st_size,
            }
        )
    return artifacts


def _summarize_output(output_xml: Path) -> dict[str, Any]:
    """Read Robot's machine result and return counts without inferring QA assertions."""
    root = ET.parse(output_xml).getroot()
    tests: list[dict[str, str]] = []
    for test in root.findall(".//test"):
        status = test.find("status")
        tags = [str(tag.text or "") for tag in test.findall("./tag")]
        case_id = next(
            (tag.split(":", 1)[1].strip() for tag in tags if tag.casefold().startswith("case:")),
            "",
        )
        tests.append(
            {
                "name": str(test.get("name", "")),
                "status": str(status.get("status", "UNKNOWN")) if status is not None else "UNKNOWN",
                "message": str(status.get("message", "")) if status is not None else "",
                "tags": tags,
                "case_id": case_id,
            }
        )
    passed = sum(test["status"] == "PASS" for test in tests)
    failed = sum(test["status"] == "FAIL" for test in tests)
    skipped = sum(test["status"] == "SKIP" for test in tests)
    suite_status = "PASS" if tests and passed == len(tests) else "FAIL" if failed else "UNASSERTED"
    return {
        "suite_status": suite_status,
        "test_count": len(tests),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "tests": tests,
    }


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ugaf-robot",
        description="Run a Robot Framework suite with UGAF screen QA keywords.",
    )
    parser.add_argument("suite", type=Path, help="Robot Framework .robot suite file or directory")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/robot"),
        help="Root folder for this run's Robot reports and UGAF manifest",
    )
    parser.add_argument(
        "--include",
        "-i",
        dest="include",
        action="append",
        default=[],
        help="Run only tests with this tag (repeatable; supports Robot tag patterns)",
    )
    parser.add_argument(
        "--exclude",
        "-e",
        dest="exclude",
        action="append",
        default=[],
        help="Exclude tests with this tag (repeatable)",
    )
    parser.add_argument(
        "--variable",
        "-v",
        dest="variables",
        action="append",
        default=[],
        help="Pass a Robot variable as NAME:value (repeatable)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate the suite without executing keywords"
    )
    parser.add_argument("--profile", default="", help="UGAF per-game profile key for result sync")
    parser.add_argument("--game-type", default="", help="Game type recorded with this run")
    parser.add_argument("--build-id", default="", help="Game build/version recorded with this run")
    args = parser.parse_args(argv)

    suite = args.suite.expanduser().resolve()
    output_root = args.output_dir.expanduser().resolve()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "run_manifest.json"
    output_xml = run_dir / "output.xml"
    started_at = datetime.now(UTC).isoformat()
    base: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "runner": "Robot Framework",
        "suite": str(suite),
        "suite_sha256": _suite_hash(suite) if suite.is_file() else None,
        "profile": args.profile.strip(),
        "game": args.profile.strip(),
        "game_type": args.game_type.strip(),
        "build_id": args.build_id.strip(),
        "selection": {
            "include_tags": args.include,
            "exclude_tags": args.exclude,
            "variables": args.variables,
            "dry_run": args.dry_run,
        },
        "started_at_utc": started_at,
        "output_xml": str(output_xml),
        "log_html": str(run_dir / "log.html"),
        "report_html": str(run_dir / "report.html"),
        "artifacts": [],
        "qa_status": "UNASSERTED",
        "note": (
            "Robot status is not mapped to UGAF testcase PASS without a requirement/evidence link."
        ),
    }

    if not suite.exists():
        base.update(status="START_FAILED", error=f"Suite path does not exist: {suite}")
        base["finished_at_utc"] = datetime.now(UTC).isoformat()
        _write_manifest(manifest_path, base)
        print(base["error"], file=sys.stderr)
        return 2

    try:
        from robot import run as robot_run
    except ImportError:
        base.update(
            status="START_FAILED",
            error="Robot Framework is not installed. Install with: pip install -e .[robot]",
        )
        base["finished_at_utc"] = datetime.now(UTC).isoformat()
        _write_manifest(manifest_path, base)
        print(base["error"], file=sys.stderr)
        return 2

    try:
        robot_options: dict[str, Any] = {
            "outputdir": str(run_dir),
            "output": "output.xml",
            "log": "log.html",
            "report": "report.html",
            "dryrun": args.dry_run,
        }
        import os

        previous_screenshot_dir = os.environ.get("UGAF_ROBOT_OUTPUT_DIR")
        os.environ["UGAF_ROBOT_OUTPUT_DIR"] = str(run_dir / "screenshots")
        if args.include:
            robot_options["include"] = args.include
        if args.exclude:
            robot_options["exclude"] = args.exclude
        if args.variables:
            robot_options["variable"] = args.variables
        try:
            return_code = int(robot_run(str(suite), **robot_options))
        finally:
            if previous_screenshot_dir is None:
                os.environ.pop("UGAF_ROBOT_OUTPUT_DIR", None)
            else:
                os.environ["UGAF_ROBOT_OUTPUT_DIR"] = previous_screenshot_dir
        summary = (
            _summarize_output(output_xml)
            if output_xml.is_file()
            else {
                "suite_status": "UNASSERTED",
                "test_count": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "tests": [],
            }
        )
        base.update(summary)
        base["status"] = "DRY_RUN" if args.dry_run else summary["suite_status"]
        base["robot_exit_code"] = return_code
        if return_code and summary["suite_status"] == "PASS":
            base["status"] = "RUN_ERROR"
    except Exception as exc:  # Robot can raise for malformed suite/import errors.
        base.update(status="START_FAILED", error=f"{type(exc).__name__}: {exc}")
        return_code = 2

    base["finished_at_utc"] = datetime.now(UTC).isoformat()
    base["artifacts"] = _artifact_inventory(run_dir)
    _write_manifest(manifest_path, base)
    print(f"Robot status : {base['status']}")
    print(f"Run manifest : {manifest_path}")
    print(f"HTML report  : {base['report_html']}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
