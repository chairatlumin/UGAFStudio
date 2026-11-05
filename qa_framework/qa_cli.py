from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.qa.report import ReportGenerator
from qa_framework.suite import load_suite, run_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="UGAF declarative QA runner")
    parser.add_argument("--suite", required=True, help="Path to a QA suite JSON file")
    parser.add_argument("--report-dir", default="reports", help="Directory for HTML reports")
    args = parser.parse_args()

    try:
        suite = load_suite(args.suite)
        results = run_suite(suite)
        report = ReportGenerator().generate(results, Path(args.report_dir))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"QA FAILED TO START: {exc}")
        return 2

    passed = sum(result.passed for result in results)
    failed = len(results) - passed
    print(f"Suite      : {suite.name}")
    print(f"Tests      : {len(results)}")
    print(f"Passed     : {passed}")
    print(f"Failed     : {failed}")
    print(f"HTML report: {report}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
