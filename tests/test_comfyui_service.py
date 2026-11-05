from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from app.services.comfyui_service import ComfyUIService


def _workflow(path: Path) -> None:
    path.write_text(json.dumps({
        "1": {"class_type": "LoadImage", "inputs": {"image": "placeholder.png"}},
        "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
    }), encoding="utf-8")


def test_comfyui_url_is_local_http_only(tmp_path: Path) -> None:
    service = ComfyUIService(registry_path=tmp_path / "registry.json")
    assert service.base_url == "http://127.0.0.1:8188"
    for url in ("https://127.0.0.1:8188", "http://example.com", "http://127.0.0.1:8188/path"):
        with pytest.raises(ValueError, match="local HTTP"):
            service.base_url = url


def test_missing_loadimage_rejected_before_upload(tmp_path: Path, monkeypatch) -> None:
    workflow = tmp_path / "no-image-node.json"
    workflow.write_text(json.dumps({"1": {"class_type": "SaveImage", "inputs": {}}}))
    image = tmp_path / "screen.png"
    image.write_bytes(b"png")
    service = ComfyUIService(registry_path=tmp_path / "registry.json")
    uploads: list[Path] = []
    monkeypatch.setattr(service, "_upload_image", lambda path: uploads.append(path) or "uploaded.png")

    with pytest.raises(ValueError, match="LoadImage"):
        service.queue_workflow(workflow, image)
    assert uploads == []


def test_registry_pins_reviewed_hash_and_queue_rejects_mutation(tmp_path: Path, monkeypatch) -> None:
    workflow = tmp_path / "workflow.json"
    image = tmp_path / "screen.png"
    _workflow(workflow)
    image.write_bytes(b"png")
    service = ComfyUIService(registry_path=tmp_path / "registry.json")
    registered = service.register_workflow(workflow, "screen_annotation")
    assert registered["purpose"] == "screen_annotation"
    assert registered["node_classes"] == ["LoadImage", "SaveImage"]

    uploads: list[Path] = []
    monkeypatch.setattr(service, "_upload_image", lambda path: uploads.append(path) or "uploaded.png")
    workflow.write_text(workflow.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="Register/review"):
        service.queue_workflow(workflow, image)
    assert uploads == []


def test_registered_workflow_queues_after_local_upload(tmp_path: Path, monkeypatch) -> None:
    workflow = tmp_path / "workflow.json"
    image = tmp_path / "screen.png"
    _workflow(workflow)
    image.write_bytes(b"png")
    service = ComfyUIService(registry_path=tmp_path / "registry.json")
    service.register_workflow(workflow, "visual_review")
    monkeypatch.setattr(service, "_upload_image", lambda _path: "upload/screen.png")

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b'{"prompt_id":"prompt-123"}'

    with patch("app.services.comfyui_service.urllib.request.urlopen", return_value=_Response()) as open_url:
        assert service.queue_workflow(workflow, image) == "prompt-123"
    request = open_url.call_args.args[0]
    prompt = json.loads(request.data)
    assert prompt["prompt"]["1"]["inputs"]["image"] == "upload/screen.png"


def test_invalid_purpose_and_oversized_screenshot_are_rejected(tmp_path: Path, monkeypatch) -> None:
    workflow = tmp_path / "workflow.json"
    image = tmp_path / "screen.png"
    _workflow(workflow)
    image.write_bytes(b"png")
    service = ComfyUIService(registry_path=tmp_path / "registry.json")
    with pytest.raises(ValueError, match="purpose"):
        service.register_workflow(workflow, "arbitrary")
    service.register_workflow(workflow, "ui_mockup")
    monkeypatch.setattr("app.services.comfyui_service.MAX_SCREENSHOT_BYTES", 1)
    uploads: list[Path] = []
    monkeypatch.setattr(service, "_upload_image", lambda path: uploads.append(path) or "x")
    with pytest.raises(ValueError, match="50 MiB"):
        service.queue_workflow(workflow, image)
    assert uploads == []


def test_generated_workflow_images_are_saved_with_hash_and_scoped_path(tmp_path, monkeypatch) -> None:
    service = ComfyUIService(registry_path=tmp_path / "registry.json")
    monkeypatch.setattr(
        "app.services.comfyui_service.writable_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    image_data = cv2.imencode(".png", np.zeros((3, 4, 3), dtype=np.uint8))[1].tobytes()

    class _Response:
        headers = {"Content-Type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int) -> bytes:
            return image_data

    with patch("app.services.comfyui_service.urllib.request.urlopen", return_value=_Response()) as open_url:
        artifacts = service.collect_workflow_output_artifacts(
            "prompt-123",
            {
                "outputs": {
                    "8": {
                        "images": [
                            {"filename": "concept.png", "subfolder": "", "type": "output"},
                            {"filename": "preview.png", "subfolder": "", "type": "temp"},
                        ]
                    }
                }
            },
            "highschoolblood-demo",
        )

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert Path(artifact["path"]).read_bytes() == image_data
    assert Path(artifact["path"]).parts[-5:] == (
        "reports",
        "comfyui",
        "highschoolblood-demo",
        "prompt-123",
        "8_00_concept.png",
    )
    assert artifact["sha256"] == hashlib.sha256(image_data).hexdigest()
    assert artifact["size_bytes"] == len(image_data)
    assert open_url.call_count == 1


def test_workflow_output_path_and_profile_are_validated_before_download(tmp_path) -> None:
    service = ComfyUIService(registry_path=tmp_path / "registry.json")
    entry = {"outputs": {"8": {"images": [{"filename": "../outside.png"}]}}}
    with patch("app.services.comfyui_service.urllib.request.urlopen") as open_url:
        with pytest.raises(ValueError, match="filename"):
            service.collect_workflow_output_artifacts("prompt-123", entry, "demo")
        with pytest.raises(ValueError, match="profile"):
            service.collect_workflow_output_artifacts("prompt-123", {"outputs": {}}, "../demo")
    open_url.assert_not_called()


def test_profile_symlink_cannot_escape_comfyui_evidence_root(tmp_path, monkeypatch) -> None:
    service = ComfyUIService(registry_path=tmp_path / "registry.json")
    monkeypatch.setattr(
        "app.services.comfyui_service.writable_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    evidence_root = tmp_path / "reports" / "comfyui"
    evidence_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(outside, evidence_root / "demo", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Directory symlinks unavailable: {exc}")

    with patch("app.services.comfyui_service.urllib.request.urlopen") as open_url:
        with pytest.raises(ValueError, match="profile directory"):
            service.collect_workflow_output_artifacts(
                "prompt-123",
                {"outputs": {"8": {"images": [{"filename": "concept.png"}]}}},
                "demo",
            )
    open_url.assert_not_called()


def test_oversized_workflow_output_is_rejected(tmp_path, monkeypatch) -> None:
    service = ComfyUIService(registry_path=tmp_path / "registry.json")
    monkeypatch.setattr(
        "app.services.comfyui_service.writable_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    image_data = cv2.imencode(".png", np.zeros((3, 4, 3), dtype=np.uint8))[1].tobytes()

    class _Response:
        headers = {"Content-Type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int) -> bytes:
            return image_data

    monkeypatch.setattr("app.services.comfyui_service.MAX_WORKFLOW_OUTPUT_BYTES", len(image_data) - 1)
    with patch("app.services.comfyui_service.urllib.request.urlopen", return_value=_Response()):
        with pytest.raises(ValueError, match="50 MiB"):
            service.collect_workflow_output_artifacts(
                "prompt-123",
                {"outputs": {"8": {"images": [{"filename": "concept.png"}]}}},
                "demo",
            )
