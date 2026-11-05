"""LessonBus — pub/sub fan-out so one agent's resolution reaches all relevant agents."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from qa_framework.lesson_store import LessonStore


@dataclass
class _Subscription:
    agent_id: str
    tags: set[str] = field(default_factory=set)
    callback: Callable[[dict[str, Any]], None] = field(default=lambda _: None)


class LessonBus:
    """Stores each published lesson, then notifies subscribers with overlapping tags."""

    def __init__(self, store: LessonStore) -> None:
        self._store = store
        self._subs: list[_Subscription] = []

    def subscribe(
        self,
        agent_id: str,
        tags: list[str],
        callback: Callable[[dict[str, Any]], None],
    ) -> None:
        self._subs.append(
            _Subscription(agent_id=agent_id, tags={t.lower() for t in tags}, callback=callback)
        )

    def publish(
        self,
        agent_id: str,
        pattern: str,
        solution: str,
        tags: list[str],
        confidence: float = 1.0,
    ) -> int:
        lesson_id = self._store.add_lesson(agent_id, pattern, solution, tags, confidence)
        lesson = self._store.get_lesson(lesson_id)
        assert lesson is not None, f"Lesson vanished: {lesson_id}"
        published = {t.lower() for t in tags}
        for sub in self._subs:
            if published & sub.tags:
                sub.callback(lesson)
        return lesson_id
