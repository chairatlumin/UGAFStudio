from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def test_bundled_comfy_workflow_copies_to_writable_storage_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from app.gui.widgets import studio_framework_widget as studio_module

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(studio_module.StudioFrameworkWidget, "_refresh_games", lambda _self: None)
    monkeypatch.setattr(
        studio_module,
        "writable_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    widget = studio_module.StudioFrameworkWidget()

    widget._load_sample_workflow()

    destination = tmp_path / "data" / "comfyui" / "workflows" / "comfyui_sdxl_image_review_api.json"
    assert Path(widget._workflow.text()) == destination
    workflow = json.loads(destination.read_text(encoding="utf-8"))
    assert any(node["class_type"] == "LoadImage" for node in workflow.values())
    assert any(node["class_type"] == "SaveImage" for node in workflow.values())

    destination.write_text('{"user_edit":true}', encoding="utf-8")
    widget._load_sample_workflow()
    assert destination.read_text(encoding="utf-8") == '{"user_edit":true}'
    widget.close()
    app.processEvents()


def test_frozen_workbench_finds_workflow_from_pyinstaller_resource_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from app.gui.widgets import studio_framework_widget as studio_module

    app = QApplication.instance() or QApplication([])
    bundle_root = Path(__file__).resolve().parents[1] / "dist" / "UGAF-QA" / "_internal"
    monkeypatch.setattr(studio_module.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(studio_module.StudioFrameworkWidget, "_refresh_games", lambda _self: None)
    monkeypatch.setattr(
        studio_module,
        "writable_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    widget = studio_module.StudioFrameworkWidget()

    widget._load_sample_workflow()

    bundled = bundle_root / "qa_framework" / "workflows" / "comfyui_sdxl_image_review_api.json"
    copied = Path(widget._workflow.text())
    assert copied.is_file()
    assert copied.read_bytes() == bundled.read_bytes()
    widget.close()
    app.processEvents()


def test_ta_optimize_mockup_workflow_copies_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from app.gui.widgets import studio_framework_widget as studio_module

    app = QApplication.instance() or QApplication([])
    bundle_root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(studio_module.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(studio_module.StudioFrameworkWidget, "_refresh_games", lambda _self: None)
    monkeypatch.setattr(
        studio_module,
        "writable_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    widget = studio_module.StudioFrameworkWidget()

    widget._load_ta_optimize_workflow()

    filename = "ugaf_ta_optimize_mockup_api.json"
    destination = tmp_path / "data" / "comfyui" / "workflows" / filename
    bundled = bundle_root / "qa_framework" / "workflows" / filename
    assert Path(widget._workflow.text()) == destination
    assert destination.read_bytes() == bundled.read_bytes()
    destination.write_text('{"user_edit":true}', encoding="utf-8")
    widget._load_ta_optimize_workflow()
    assert destination.read_text(encoding="utf-8") == '{"user_edit":true}'
    widget.close()
    app.processEvents()
