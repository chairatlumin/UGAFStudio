from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SteamGame:
    app_id: int
    name: str
    install_path: Path
    manifest_path: Path


def find_steam_root() -> Path | None:
    candidates = [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ]

    for path in candidates:
        if path.exists():
            return path

    return None


def find_library_folders(steam_root: Path) -> list[Path]:
    libraries: list[Path] = []

    main_library = steam_root / "steamapps"

    if main_library.exists():
        libraries.append(main_library)

    library_file = steam_root / "steamapps" / "libraryfolders.vdf"

    if not library_file.exists():
        return libraries

    text = library_file.read_text(
        encoding="utf-8",
        errors="replace",
    )

    for match in re.finditer(
        r'"path"\s+"([^"]+)"',
        text,
        re.IGNORECASE,
    ):
        library_root = Path(match.group(1).replace("\\\\", "\\"))

        steamapps = library_root / "steamapps"

        if steamapps.exists() and steamapps not in libraries:
            libraries.append(steamapps)

    return libraries


def parse_manifest(
    manifest_path: Path,
) -> SteamGame | None:
    text = manifest_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    app_match = re.search(
        r'"appid"\s+"(\d+)"',
        text,
        re.IGNORECASE,
    )

    name_match = re.search(
        r'"name"\s+"([^"]+)"',
        text,
        re.IGNORECASE,
    )

    install_match = re.search(
        r'"installdir"\s+"([^"]+)"',
        text,
        re.IGNORECASE,
    )

    if not app_match or not install_match:
        return None

    app_id = int(app_match.group(1))
    name = name_match.group(1) if name_match else f"Steam App {app_id}"

    install_dir = manifest_path.parent / "common" / install_match.group(1)

    return SteamGame(
        app_id=app_id,
        name=name,
        install_path=install_dir.resolve(),
        manifest_path=manifest_path.resolve(),
    )


def discover_games(
    steam_root: Path | None = None,
) -> list[SteamGame]:
    root = steam_root or find_steam_root()

    if root is None:
        raise FileNotFoundError("Steam installation was not found.")

    games: list[SteamGame] = []

    for library in find_library_folders(root):
        for manifest in library.glob("appmanifest_*.acf"):
            game = parse_manifest(manifest)

            if game is not None:
                games.append(game)

    games.sort(key=lambda game: game.name.lower())

    return games


def find_game(
    app_id: int,
    steam_root: Path | None = None,
) -> SteamGame:
    games = discover_games(steam_root)

    for game in games:
        if game.app_id == app_id:
            return game

    raise LookupError(f"Steam App ID {app_id} was not found in installed Steam libraries.")
