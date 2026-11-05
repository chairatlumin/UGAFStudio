from __future__ import annotations

import random
from typing import Any, List

from loguru import logger

from qa_framework.gameplay_agent.actions import Action
from qa_framework.gameplay_agent.base import GameplayAgent


class RandomAgent(GameplayAgent):
    """A configurable-random agent that picks actions from a provided list.

    The RNG is seeded deterministically so tests can reproduce sequences.
    """

    def __init__(
        self,
        *,
        actions: List[Action],
        seed: int | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self._actions = actions
        logger.info("RandomAgent initialised with {} actions (seed={})", len(actions), seed)

    # ------------------------------------------------------------------
    # GameplayAgent
    # ------------------------------------------------------------------

    def observe(self, frame: Any) -> Any:
        """Accept a game frame; RandomAgent does not process pixel data."""
        return frame

    def decide(self, observation: Any) -> Action:
        """Pick a random action from the configured list."""
        action = self._rng.choice(self._actions)
        logger.debug("RandomAgent deciding: {}", action)
        return action

    def learn(self, reward: float, done: bool) -> None:
        """No-op; RandomAgent has no learning."""
        pass
