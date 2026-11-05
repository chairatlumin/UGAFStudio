from __future__ import annotations

import argparse
import json
from pathlib import Path

from qa_framework.gameplay.coordinator import (
    run_combined_suite,
    run_game_by_app_id,
    run_local_game,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="UGAF declarative gameplay QA runner")
    parser.add_argument(
        "--suite", required=True, help="Single-game or combined gameplay suite JSON"
    )
    parser.add_argument("--app-id", type=int, help="Run one game from a single-game suite")
    parser.add_argument("--executable", help="Run any local game executable, independent of engine")
    parser.add_argument("--name", help="Optional display name for --executable")
    parser.add_argument("--steam-root", help="Optional Steam installation path")
    parser.add_argument("--output-dir", default="reports/gameplay", help="HTML report directory")
    args = parser.parse_args()

    suite_path = Path(args.suite)
    steam_root = Path(args.steam_root) if args.steam_root else None
    output_dir = Path(args.output_dir)

    try:
        data = json.loads(suite_path.read_text(encoding="utf-8"))
        if args.app_id is not None and args.executable:
            parser.error("Use only one of --app-id or --executable")
        if args.executable:
            result = run_local_game(
                args.executable,
                suite_path,
                name=args.name,
                output_dir=output_dir,
            )
            results = [result]
        elif args.app_id is not None:
            result = run_game_by_app_id(
                args.app_id,
                suite_path,
                steam_root=steam_root,
                output_dir=output_dir,
            )
            results = [result]
        elif isinstance(data, dict) and isinstance(data.get("games"), list):
            results = run_combined_suite(
                suite_path,
                steam_root=steam_root,
                output_dir=output_dir,
            )
        else:
            parser.error("A single-game suite requires --app-id or --executable")
    except (OSError, ValueError, json.JSONDecodeError, LookupError) as exc:
        print(f"GAMEPLAY QA FAILED TO START: {exc}")
        return 2

    passed = sum(result.passed for result in results)
    failed = len(results) - passed
    report = results[0].report_path if results else None
    print(f"Games      : {len(results)}")
    print(f"Passed     : {passed}")
    print(f"Failed     : {failed}")
    print(f"HTML report: {report}")
    for result in results:
        print(
            f"{result.game_name}: started={result.started} "
            f"assertions={sum(a.passed for a in result.assertions)}/{len(result.assertions)} "
            f"cleanup={result.cleanup.status if result.cleanup else 'n/a'}"
        )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
