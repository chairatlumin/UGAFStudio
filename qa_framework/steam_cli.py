from __future__ import annotations

import argparse

from qa_framework.adapters.steam import (
    SteamGame,
    discover_games,
    find_game,
)


def print_game(game: SteamGame) -> None:
    installed = game.install_path.exists()

    print(f"App ID       : {game.app_id}")
    print(f"Name         : {game.name}")
    print(f"Install Path : {game.install_path}")
    print(f"Manifest     : {game.manifest_path}")
    print(f"Installed    : {'YES' if installed else 'NO'}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="UGAF Steam Build Adapter")

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    list_parser = subparsers.add_parser(
        "list",
        help="List installed Steam games",
    )

    list_parser.add_argument(
        "--steam-root",
        default=None,
        help="Optional Steam installation path",
    )

    game_parser = subparsers.add_parser(
        "game",
        help="Inspect one Steam game",
    )

    game_parser.add_argument(
        "--app-id",
        required=True,
        type=int,
    )

    game_parser.add_argument(
        "--steam-root",
        default=None,
        help="Optional Steam installation path",
    )

    args = parser.parse_args()

    if args.command == "list":
        from pathlib import Path

        steam_root = Path(args.steam_root) if args.steam_root else None

        try:
            games = discover_games(steam_root)

        except Exception as exc:
            print(f"STEAM DISCOVERY FAILED: {exc}")
            return 1

        print("=== UGAF STEAM GAMES ===")
        print()

        if not games:
            print("No installed Steam games found.")
            return 0

        for game in games:
            print_game(game)

        print(f"Total Games: {len(games)}")

        return 0

    if args.command == "game":
        from pathlib import Path

        steam_root = Path(args.steam_root) if args.steam_root else None

        try:
            game = find_game(
                args.app_id,
                steam_root,
            )

        except Exception as exc:
            print(f"STEAM GAME LOOKUP FAILED: {exc}")
            return 1

        print("=== UGAF STEAM GAME ===")
        print()
        print_game(game)

        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
