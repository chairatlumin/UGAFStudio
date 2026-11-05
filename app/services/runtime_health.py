from __future__ import annotations

import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.paths import writable_base
from app.services.comfyui_service import ComfyUIService
from app.vision.ocr import OCREngine


@dataclass(frozen=True)
class RuntimeCheck:
    component: str
    status: str
    details: str


def _local_url(value: str, label: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{label} must use a local HTTP URL")
    return value.strip().rstrip("/")


def check_vlm(
    base_url: str | None = None,
    model: str | None = None,
    *,
    timeout: float = 1.5,
) -> RuntimeCheck:
    """Check the configured local OpenAI-compatible endpoint and requested model."""
    url = base_url or os.environ.get("VLM_BASE_URL", "http://127.0.0.1:1234/v1")
    model_id = model or os.environ.get("VLM_MODEL", "qwen/qwen2.5-vl-7b")
    try:
        endpoint = _local_url(url, "VLM endpoint")
        if not model_id.strip():
            return RuntimeCheck("VLM", "NOT_CONFIGURED", "No vision model is configured.")
        request = urllib.request.Request(f"{endpoint}/models")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            import json

            payload: Any = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            return RuntimeCheck("VLM", "ERROR", "The /models response is not a JSON object.")
        model_ids = {
            str(entry.get("id", ""))
            for entry in payload.get("data", [])
            if isinstance(entry, dict)
        }
        if model_ids and model_id not in model_ids:
            return RuntimeCheck(
                "VLM",
                "MODEL_MISSING",
                f"Endpoint is online, but model {model_id!r} is not listed.",
            )
        return RuntimeCheck("VLM", "READY", f"{endpoint} · model {model_id}")
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        return RuntimeCheck("VLM", "UNAVAILABLE", str(exc))


def check_comfyui(base_url: str | None = None, *, timeout: float = 1.5) -> RuntimeCheck:
    """Probe only a local ComfyUI server; never sends images or workflows."""
    url = base_url or os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    try:
        endpoint = _local_url(url, "ComfyUI endpoint")
        service = ComfyUIService(base_url=endpoint)
        if service.is_available(timeout=timeout):
            return RuntimeCheck("ComfyUI", "READY", f"{endpoint} · system_stats responded")
        return RuntimeCheck("ComfyUI", "UNAVAILABLE", f"No response from {endpoint}/system_stats")
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        return RuntimeCheck("ComfyUI", "UNAVAILABLE", str(exc))


def check_ocr() -> RuntimeCheck:
    """Report both the Python wrapper and external Tesseract binary availability."""
    engine = OCREngine()
    if engine.available():
        command = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        return RuntimeCheck("OCR / Tesseract", "READY", f"pytesseract and {command}")
    try:
        import pytesseract  # noqa: F401

        return RuntimeCheck(
            "OCR / Tesseract", "BINARY_MISSING", "pytesseract is installed, but Tesseract was not found."
        )
    except ImportError:
        return RuntimeCheck("OCR / Tesseract", "NOT_INSTALLED", "Install pytesseract and Tesseract OCR.")


def check_writable_data() -> RuntimeCheck:
    """Verify package-local mutable directories using a temporary probe file."""
    root = writable_base()
    folders = [root / name for name in ("data", "reports", "logs", "screenshots", "config")]
    try:
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix=".ugaf-health-", dir=folder, delete=True):
                pass
    except OSError as exc:
        return RuntimeCheck("App data", "NOT_WRITABLE", str(exc))
    return RuntimeCheck("App data", "READY", f"Writable beside app: {root}")


def collect_runtime_health() -> list[RuntimeCheck]:
    """Collect bounded local dependency and package checks for the Health tab."""
    checks = [
        RuntimeCheck(
            "Runtime",
            "READY",
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} · "
            f"{'frozen EXE' if getattr(sys, 'frozen', False) else 'source'}",
        ),
        check_writable_data(),
        check_ocr(),
        check_vlm(),
        check_comfyui(),
    ]
    return checks
