from __future__ import annotations

from app.capture.capture_service import CaptureService
from app.core.config import Config
from app.core.fps import FPSCounter
from app.core.logger import get_logger
from app.input.mouse_service import MouseService


class ServiceContainer:
    """Application service container."""

    def __init__(self) -> None:
        self.logger = get_logger()

        self.config = Config()
        self.config.load()

        self.capture = CaptureService()

        self.mouse = MouseService()

        self.fps = FPSCounter()
