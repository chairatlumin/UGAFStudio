from __future__ import annotations

import abc
from typing import Any

from .actions import Action


class GameplayAgent(abc.ABC):
    """Abstract base class for gameplay agents.

    Subclasses implement `observe`/`decide` loop to interact with a game.
    """

    @abc.abstractmethod
    def observe(self, frame: Any) -> Any:
        """Receive a game frame (BGR numpy array) and return an observation."""
        ...

    @abc.abstractmethod
    def decide(self, observation: Any) -> "Action":
        """Convert an observation into an Action."""
        ...

    def learn(self, reward: float, done: bool) -> None:
        """Called after an action executes; default no-op for future RL models."""
        ...
