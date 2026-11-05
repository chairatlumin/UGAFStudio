from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from app.qa.report import ReportGenerator
from app.qa.test_case import TestCase, TestRunner
from qa_framework.adapters.steam import find_game


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QA checks on an installed Steam game")
    parser.add_argument("--app-id", required=True, type=int, help="Steam App ID")
    parser.add_argument("--steam-root", default=None, help="Optional Steam installation path")
    parser.add_argument("--report-dir", default="reports", help="Directory for HTML reports")
    args = parser.parse_args()

    try:
        steam_root = Path(args.steam_root) if args.steam_root else None
        game = find_game(args.app_id, steam_root)
    except (FileNotFoundError, LookupError, OSError) as exc:
        print(f"STEAM QA FAILED TO START: {exc}")
        return 2

    install_path = game.install_path
    tests = [
        TestCase(
            name=f"Steam: {game.name}",
            steps=[
                (
                    "install directory exists",
                    _assert(
                        lambda: install_path.is_dir(),
                        f"Missing install directory: {install_path}",
                    ),
                ),
                (
                    "game executable exists",
                    _assert(
                        lambda: bool(list(install_path.rglob("*.exe"))),
                        f"No .exe found under: {install_path}",
                    ),
                ),
            ],
        )
    ]
    results = TestRunner().run(tests)
    report = ReportGenerator().generate(results, Path(args.report_dir))
    failed = sum(not result.passed for result in results)

    print(f"Game       : {game.name}")
    print(f"App ID     : {game.app_id}")
    print(f"Install    : {game.install_path}")
    print(f"Passed     : {len(results) - failed}")
    print(f"Failed     : {failed}")
    print(f"HTML report: {report}")
    return 0 if failed == 0 else 1


def _assert(check: object, message: str) -> Callable[[], None]:
    def run() -> None:
        if not check():  # type: ignore[operator]
            raise AssertionError(message)

    return run


if __name__ == "__main__":
    raise SystemExit(main())
