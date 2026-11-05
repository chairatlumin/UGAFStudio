from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.core.paths import writable_path
from app.vision.ocr import OCREngine

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = writable_path("data", "comfyui", "workflow_registry.json")
WORKFLOW_PURPOSES = frozenset({"ui_mockup", "screen_annotation", "visual_review"})
MAX_SCREENSHOT_BYTES = 50 * 1024 * 1024
MAX_WORKFLOW_OUTPUT_BYTES = 50 * 1024 * 1024


class ComfyUIService:
    """Local ComfyUI API adapter plus deterministic screenshot text analysis."""

    def __init__(
        self, base_url: str = "http://127.0.0.1:8188", registry_path: Path = DEFAULT_REGISTRY
    ) -> None:
        self._base_url = ""
        self.registry_path = Path(registry_path)
        self.base_url = base_url

    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, value: str) -> None:
        parsed = urllib.parse.urlsplit(value.strip())
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("ComfyUI must use a local HTTP URL (127.0.0.1/localhost/::1)")
        self._base_url = value.strip().rstrip("/")

    def is_available(self, timeout: float = 2.0) -> bool:
        try:
            request = urllib.request.Request(f"{self.base_url}/system_stats")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError, ValueError):
            return False

    def analyze_image(self, image_path: Path, expected_text: str = "") -> dict[str, Any]:
        frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"Cannot read image: {image_path}")
        ocr = OCREngine()
        detected = ocr.read(frame)
        expected = expected_text.strip()
        found = bool(expected and expected.casefold() in detected.casefold())
        return {
            "method": "tesseract_ocr",
            "image_size": {"width": int(frame.shape[1]), "height": int(frame.shape[0])},
            "detected_text": detected.strip(),
            "expected_text": expected,
            "expected_text_found": found if expected else None,
            "ocr_available": ocr.available(),
            "comfyui_available": self.is_available(),
        }

    def queue_workflow(self, workflow_path: Path, image_path: Path) -> str:
        """Queue a registered, unchanged API workflow after validating local inputs."""
        workflow_path = Path(workflow_path).resolve()
        image_path = Path(image_path).resolve()
        info = self.inspect_workflow(workflow_path)
        registered = self.get_registered_workflow(workflow_path)
        if not registered or registered["sha256"] != info["sha256"]:
            raise ValueError("Register/review this workflow before use; its file may have changed.")
        if not image_path.is_file():
            raise ValueError(f"Screenshot does not exist: {image_path}")
        if image_path.stat().st_size > MAX_SCREENSHOT_BYTES:
            raise ValueError("Screenshot exceeds the 50 MiB local upload limit.")
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        load_nodes = [node for node in workflow.values() if node["class_type"] == "LoadImage"]
        # All workflow/image validation finishes before any screenshot is uploaded.
        filename = self._upload_image(image_path)
        for node in load_nodes:
            node.setdefault("inputs", {})["image"] = filename
        payload = json.dumps({"prompt": workflow, "client_id": uuid.uuid4().hex}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        prompt_id = str(result.get("prompt_id", ""))
        if not prompt_id:
            raise RuntimeError(f"ComfyUI rejected workflow: {result}")
        return prompt_id

    def inspect_workflow(self, workflow_path: Path) -> dict[str, Any]:
        """Validate API-format shape and required image input without network calls."""
        path = Path(workflow_path).expanduser().resolve()
        try:
            raw = path.read_bytes()
            workflow = json.loads(raw.decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read ComfyUI workflow JSON: {exc}") from exc
        if not isinstance(workflow, dict) or not 1 <= len(workflow) <= 500:
            raise ValueError("Workflow must contain 1..500 API-format nodes.")
        classes: list[str] = []
        for node_id, node in workflow.items():
            if (
                not isinstance(node, dict)
                or not isinstance(node.get("class_type"), str)
                or not node["class_type"].strip()
                or not isinstance(node.get("inputs", {}), dict)
            ):
                raise ValueError(f"Workflow node {node_id!r} is malformed.")
            classes.append(node["class_type"])
        if "LoadImage" not in classes:
            raise ValueError("Workflow needs a LoadImage node to accept the screenshot.")
        return {
            "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "node_count": len(workflow),
            "node_classes": sorted(set(classes)),
        }

    def register_workflow(self, workflow_path: Path, purpose: str) -> dict[str, Any]:
        """Explicitly register a reviewed workflow and pin its content hash."""
        if purpose not in WORKFLOW_PURPOSES:
            raise ValueError(f"purpose must be one of: {', '.join(sorted(WORKFLOW_PURPOSES))}")
        info = self.inspect_workflow(workflow_path)
        registry = self._read_registry()
        record = {
            **info,
            "workflow_id": hashlib.sha256(info["path"].encode()).hexdigest()[:16],
            "purpose": purpose,
            "registered_at_utc": datetime.now(UTC).isoformat(),
        }
        registry[record["workflow_id"]] = record
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.registry_path.with_suffix(self.registry_path.suffix + ".tmp")
        temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.registry_path)
        return record

    def get_registered_workflow(self, workflow_path: Path) -> dict[str, Any] | None:
        target = str(Path(workflow_path).expanduser().resolve())
        return next(
            (item for item in self._read_registry().values() if item.get("path") == target),
            None,
        )

    def _read_registry(self) -> dict[str, dict[str, Any]]:
        if not self.registry_path.is_file():
            return {}
        try:
            value = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read ComfyUI workflow registry: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError("ComfyUI workflow registry must be a JSON object.")
        return {str(key): item for key, item in value.items() if isinstance(item, dict)}

    def wait_for_workflow(self, prompt_id: str, timeout: float = 600.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            url = f"{self.base_url}/history/{urllib.parse.quote(prompt_id)}"
            with urllib.request.urlopen(url, timeout=10) as response:
                history = json.loads(response.read().decode("utf-8"))
            entry = history.get(prompt_id)
            if entry:
                return entry
            time.sleep(1)
        raise TimeoutError(f"ComfyUI workflow {prompt_id} did not finish in {timeout:g}s")

    def collect_workflow_output_artifacts(
        self, prompt_id: str, history_entry: dict[str, Any], profile: str
    ) -> list[dict[str, Any]]:
        """Download generated image outputs into a profile-scoped evidence folder."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", prompt_id):
            raise ValueError("Invalid ComfyUI prompt ID")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", profile):
            raise ValueError("Invalid game profile for ComfyUI evidence")
        outputs = history_entry.get("outputs", {})
        if not isinstance(outputs, dict):
            raise ValueError("ComfyUI workflow outputs must be an object")

        artifacts: list[dict[str, Any]] = []
        output_base = Path(writable_path("reports", "comfyui")).resolve()
        output_root = output_base / profile / prompt_id

        def ensure_scoped_output_root() -> Path:
            resolved = output_root.resolve()
            if (
                output_base not in resolved.parents
                or os.path.normcase(str(resolved)) != os.path.normcase(str(output_root))
            ):
                raise ValueError("ComfyUI evidence folder escapes its profile directory")
            return resolved

        ensure_scoped_output_root()
        for node_id, node_output in outputs.items():
            if not isinstance(node_output, dict):
                continue
            images = node_output.get("images", [])
            if not isinstance(images, list):
                continue
            for index, image in enumerate(images):
                if not isinstance(image, dict):
                    continue
                filename = image.get("filename")
                if (
                    not isinstance(filename, str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,180}", filename)
                    or filename in {".", ".."}
                    or Path(filename).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
                ):
                    raise ValueError("ComfyUI output filename is invalid")
                subfolder = image.get("subfolder", "")
                if (
                    not isinstance(subfolder, str)
                    or "\\" in subfolder
                    or Path(subfolder).is_absolute()
                    or any(part in {".", ".."} for part in subfolder.split("/") if part)
                ):
                    raise ValueError("ComfyUI output subfolder is invalid")
                image_type = image.get("type", "output")
                if image_type != "output":
                    continue

                query = urllib.parse.urlencode(
                    {"filename": filename, "subfolder": subfolder, "type": image_type}
                )
                request = urllib.request.Request(f"{self.base_url}/view?{query}")
                with urllib.request.urlopen(request, timeout=30) as response:
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip()
                    if not content_type.startswith("image/"):
                        raise ValueError("ComfyUI output response is not an image")
                    data = response.read(MAX_WORKFLOW_OUTPUT_BYTES + 1)
                if not data or len(data) > MAX_WORKFLOW_OUTPUT_BYTES:
                    raise ValueError("ComfyUI output is empty or exceeds the 50 MiB limit")
                decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                if decoded is None:
                    raise ValueError("ComfyUI returned an invalid image")

                safe_node_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(node_id))[:40] or "node"
                artifact_name = f"{safe_node_id}_{index:02d}_{filename}"
                output_root.mkdir(parents=True, exist_ok=True)
                resolved_root = ensure_scoped_output_root()
                destination = resolved_root / artifact_name
                if destination.exists():
                    raise FileExistsError(f"ComfyUI evidence already exists: {destination}")
                temporary = destination.with_suffix(destination.suffix + ".tmp")
                temporary.write_bytes(data)
                os.replace(temporary, destination)
                artifacts.append(
                    {
                        "path": str(destination),
                        "filename": filename,
                        "node_id": str(node_id),
                        "content_type": content_type,
                        "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
        return artifacts

    def _upload_image(self, image_path: Path) -> str:
        boundary = f"----UGAF{uuid.uuid4().hex}"
        data = image_path.read_bytes()
        body = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
                f'filename="{image_path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
            ).encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode()
        )
        request = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
        name = str(result.get("name", ""))
        if not name:
            raise RuntimeError(f"ComfyUI image upload failed: {result}")
        return name
