from __future__ import annotations

from pathlib import Path

from scripts.fmv_harness import _resolve_cli_paths, build_parser


def test_harness_anchors_relative_artifact_and_scenario_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args(
        ["--output-dir", "reports/run", "--scenario-file", "cases/card.json"]
    )

    _resolve_cli_paths(args)

    assert args.output_dir == (tmp_path / "reports/run").resolve()
    assert args.scenario_file == (tmp_path / "cases/card.json").resolve()


def test_harness_keeps_default_scenario_absent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args(["--output-dir", "reports"])

    _resolve_cli_paths(args)

    assert args.output_dir == (tmp_path / "reports").resolve()
    assert args.scenario_file is None
