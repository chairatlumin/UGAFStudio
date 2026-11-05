"""Supervised live gameplay QA smoke test for one Steam game.

Usage (project interpreter only):
    C:/Python314/python.exe scripts/live_gameplay_smoke.py <app_id> <suite.json> [steam_root]

Launches the real game, captures one frame after startup, runs the declarative
visual assertions from the suite, saves a screenshot as evidence, always
terminates the game, and writes a single-game HTML report. No mouse/keyboard
input is sent to the game.
"""

from __future__ import annotations

import sys
from pathlib import Path

from qa_framework.gameplay.coordinator import run_game_by_app_id


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: live_gameplay_smoke.py <app_id> <suite.json> [steam_root]")
        return 2

    app_id = int(sys.argv[1])
    suite = sys.argv[2]
    steam_root = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    out_dir = Path("reports/live")

    print(f"[live] launching app_id={app_id} suite={suite} steam_root={steam_root}")
    result = run_game_by_app_id(app_id, suite, steam_root=steam_root, output_dir=out_dir)

    print(f"[live] started={result.started} pid={result.pid} exe={result.executable}")
    print(f"[live] cleanup={result.cleanup.status if result.cleanup else 'n/a'}")
    print(f"[live] assertions={[(a.name, a.passed, a.message) for a in result.assertions]}")
    print(f"[live] report={result.report_path}")
    print(f"[live] screenshot={result.screenshot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
