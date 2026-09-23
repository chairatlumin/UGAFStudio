from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from qa_framework.vision_game_runner import PerceptionState


class AnomalyType(str, Enum):
    POPUP = "popup"
    TEXTURE_GLITCH = "texture_glitch"
    INPUT_LAG = "input_lag"
    SCENE_MISMATCH = "scene_mismatch"
    FPS_DROP = "fps_drop"


@dataclass
class AnomalyInjector:
    """Wraps a perception function to probabilistically inject synthetic anomalies."""
    enabled: bool = True
    injection_rate: float = 0.1
    seed: Optional[int] = None
    _anomalies: dict[AnomalyType, Callable[[], PerceptionState]] = field(default_factory=dict)
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def register_anomaly(
        self, anomaly_type: AnomalyType, factory: Callable[[], PerceptionState]
    ) -> None:
        self._anomalies[anomaly_type] = factory

    def wrap(self, perception_fn: Callable[[], PerceptionState]) -> PerceptionState:
        if not self.enabled or not self._anomalies:
            return perception_fn()
        if self._rng.random() < self.injection_rate:
            anomaly_type = self._rng.choice(list(self._anomalies.keys()))
            return self._anomalies[anomaly_type]()
        return perception_fn()
