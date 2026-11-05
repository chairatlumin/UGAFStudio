from pathlib import Path

import pytest

from qa_framework.adapters.steam import (
    discover_games,
    find_game,
    find_library_folders,
    parse_manifest,
)


def _write_manifest(library: Path, app_id: int, name: str, install_dir: str) -> Path:
    steamapps = library / "steamapps"
    steamapps.mkdir(parents=True, exist_ok=True)
    manifest = steamapps / f"appmanifest_{app_id}.acf"
    manifest.write_text(
        f'"AppState"\n{{\n\t"appid"\t"{app_id}"\n\t"name"\t"{name}"\n'
        f'\t"installdir"\t"{install_dir}"\n}}',
        encoding="utf-8",
    )
    return manifest


def test_parse_manifest_returns_install_path(tmp_path: Path) -> None:
    game = parse_manifest(_write_manifest(tmp_path, 123, "Demo Game", "Demo"))
    assert game is not None
    assert game.app_id == 123
    assert game.name == "Demo Game"
    assert game.install_path == (tmp_path / "steamapps" / "common" / "Demo").resolve()


def test_discover_games_reads_main_and_secondary_libraries(tmp_path: Path) -> None:
    (tmp_path / "steamapps").mkdir()
    secondary_root = tmp_path / "Library 2"
    secondary_root.mkdir()
    (tmp_path / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"1"\n\t{{\n\t\t"path"\t"{secondary_root.as_posix()}"\n\t}}\n}}',
        encoding="utf-8",
    )
    _write_manifest(tmp_path, 2, "Zulu", "Zulu")
    _write_manifest(secondary_root, 1, "Alpha", "Alpha")
    games = discover_games(tmp_path)
    assert [game.name for game in games] == ["Alpha", "Zulu"]
    assert find_game(1, tmp_path).name == "Alpha"


def test_find_library_folders_ignores_missing_secondary_library(tmp_path: Path) -> None:
    (tmp_path / "steamapps").mkdir()
    (tmp_path / "steamapps" / "libraryfolders.vdf").write_text(
        '"path" "C:\\\\MissingSteamLibrary"', encoding="utf-8"
    )
    assert find_library_folders(tmp_path) == [tmp_path / "steamapps"]


def test_find_game_reports_unknown_app_id(tmp_path: Path) -> None:
    (tmp_path / "steamapps").mkdir()
    with pytest.raises(LookupError, match="123"):
        find_game(123, tmp_path)
