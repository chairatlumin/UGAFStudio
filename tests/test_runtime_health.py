from __future__ import annotations

import json
from unittest.mock import patch

from app.services.runtime_health import (
    check_comfyui,
    check_ocr,
    check_vlm,
    check_writable_data,
)


class _Response:
    status = 200

    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self._payload


def test_vlm_requires_requested_model_when_endpoint_lists_models() -> None:
    with patch(
        "app.services.runtime_health.urllib.request.urlopen",
        return_value=_Response({"data": [{"id": "other-model"}]}),
    ):
        result = check_vlm("http://127.0.0.1:1234/v1", "vision-model")
    assert result.status == "MODEL_MISSING"


def test_vlm_ready_when_model_is_listed() -> None:
    with patch(
        "app.services.runtime_health.urllib.request.urlopen",
        return_value=_Response({"data": [{"id": "vision-model"}]}),
    ):
        result = check_vlm("http://127.0.0.1:1234/v1", "vision-model")
    assert result.status == "READY"


def test_vlm_and_comfyui_reject_non_local_urls_without_network() -> None:
    with patch("app.services.runtime_health.urllib.request.urlopen") as urlopen:
        vlm = check_vlm("http://example.com/v1", "vision-model")
        comfy = check_comfyui("http://example.com")
    assert vlm.status == "UNAVAILABLE"
    assert comfy.status == "UNAVAILABLE"
    urlopen.assert_not_called()


def test_comfyui_health_uses_stats_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.runtime_health.ComfyUIService.is_available", lambda _self, timeout: True
    )
    assert check_comfyui().status == "READY"


def test_ocr_health_distinguishes_installed_binary(monkeypatch) -> None:
    monkeypatch.setattr("app.services.runtime_health.OCREngine.available", lambda _self: False)
    with patch.dict("sys.modules", {"pytesseract": object()}):
        assert check_ocr().status == "BINARY_MISSING"


def test_writable_data_health_probes_all_package_directories(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.runtime_health.writable_base", lambda: tmp_path)
    result = check_writable_data()
    assert result.status == "READY"
    assert all((tmp_path / name).is_dir() for name in ("data", "reports", "logs", "screenshots", "config"))
    assert not list(tmp_path.rglob(".ugaf-health-*"))

