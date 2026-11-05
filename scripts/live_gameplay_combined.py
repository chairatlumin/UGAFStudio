"""Run the combined live gameplay QA suite for all three selected games.

Usage (project interpreter only):
    C:/Python314/python.exe scripts/live_gameplay_combined.py
"""

from __future__ import annotations

from pathlib import Path

from qa_framework.gameplay.coordinator import run_combined_suite

COMBINED = "qa_framework/examples/gameplay_combined_live.json"
OUT = Path("reports/live")


def main() -> int:
    results = run_combined_suite(COMBINED, output_dir=OUT)
    print(f"[combined] {len(results)} games")
    for r in results:
        print(
            f"  {r.game_name} (app {r.app_id}): "
            f"started={r.started} cleanup={r.cleanup.status if r.cleanup else 'n/a'} "
            f"assertions={[(a.name, a.passed) for a in r.assertions]} "
            f"report={r.report_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
