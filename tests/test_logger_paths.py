from __future__ import annotations

from pathlib import Path

from app.core.paths import PROJECT_ROOT, writable_base


def test_source_logs_resolve_from_project_root() -> None:
    assert writable_base() == PROJECT_ROOT


def test_frozen_logs_resolve_beside_executable(tmp_path, monkeypatch) -> None:
    executable = tmp_path / "dist" / "UGAF-QA.exe"
    import app.core.paths as paths

    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(executable))
    assert writable_base() == executable.parent.resolve()


def test_screenshot_default_uses_app_data_root(tmp_path, monkeypatch) -> None:
    import app.capture.screenshot_service as screenshot_module

    monkeypatch.setattr(
        screenshot_module, "writable_path", lambda *parts: tmp_path.joinpath(*parts)
    )
    service = screenshot_module.ScreenshotService()
    assert service.output_dir == tmp_path / "screenshots"
    assert service.output_dir.is_dir()


def test_config_uses_app_data_root(tmp_path, monkeypatch) -> None:
    import app.core.config as config_module

    monkeypatch.setattr(
        config_module, "writable_path", lambda *parts: tmp_path.joinpath(*parts)
    )
    assert config_module.Config().path == tmp_path / "config" / "config.toml"
