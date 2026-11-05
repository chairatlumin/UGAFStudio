from __future__ import annotations

from pathlib import Path

from app.qa.story_timeline import StoryTimelineService


class StoryTimelineController:
    """Coordinates local story timeline operations for the GUI."""

    def __init__(self, service: StoryTimelineService | None = None) -> None:
        self.service = service or StoryTimelineService()

    def import_patch_note(self, source: str) -> int:
        return self.service.import_patch_note(source)

    def import_localization(self, source: str) -> int:
        return self.service.import_localization(source)

    def save(self, path: Path) -> None:
        self.service.save(path)

    def load(self, path: Path) -> None:
        self.service.load(path)
