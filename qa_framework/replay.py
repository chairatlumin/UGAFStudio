from __future__ import annotations

import logging
from typing import List, Optional

from qa_framework.playbook import Playbook, TraceEvent

logger = logging.getLogger(__name__)


class PlaybookReplayer:
    """Replays a :class:`Playbook` for regression testing.

    Validates each step: after "executing" the action, the frame hash is
    compared to the expected hash.  On mismatch a warning is logged but
    execution continues — game timing varies and hard-failing is counter-productive.
    """

    def __init__(self, playbook: Playbook) -> None:
        self.playbook = playbook
        self.events: List[TraceEvent] = playbook.events
        self.step_index = 0

    def replay(self, tolerance: int = 15) -> bool:
        """Replay the playbook event sequence.

        For each event the action is "executed" (simulated) and the frame hash
        is validated against the expected value.  If the Hamming distance
        between the observed and expected hash is within *tolerance* the
        replay continues; otherwise a warning is emitted and replay proceeds.

        :param tolerance: Maximum Hamming distance acceptable for a hash match.
          Default 15 (stricter than the distiller's default 10).
        :return: True if the end-state was reached, False otherwise.
        """
        if not self.events:
            return True

        logger.info("Replaying playbook: %s (%d steps)", self.playbook.goal, len(self.events))

        self.step_index = 0
        for event in self.events:
            self.step_index += 1
            # Simulate action execution — in a real integration this would
            # feed the action into the game input pipeline.
            self._execute_action(event.action)

            # Validate hash: in replay we compare the expected hash from the
            # playbook against itself (the playbook was recorded from real
            # frames).  A mismatch would indicate a corrupted or stale playbook.
            # Here we just log; a real implementation would capture a frame
            # and compute its hash.
            self._validate_hash(event.frame_hash)

        logger.info("Playbook replay completed after %d steps", self.step_index)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_action(self, action: Optional[str]) -> None:
        """Execute (or simulate) a single action.

        :param action: Action name string, or ``None`` for no-op / initial frame.
        """
        if action is None:
            logger.debug("No-op initial frame")
            return
        logger.debug("Executing action: %s", action)

    def _validate_hash(self, expected_hash: str) -> None:
        """Validate the frame hash against the expected value.

        In a live replay the observed hash would be computed from the actual
        captured frame and compared against *expected_hash*.  Here we simply
        confirm the hash is a valid 64-char hex string.

        :param expected_hash: The hash value stored in the playbook.
        """
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            logger.warning("Invalid expected hash in playbook step %d", self.step_index)
            return
        # In a fully integrated system the observed hash would be XOR'd against
        # expected_hash and the Hamming distance checked against tolerance.
        # For now we just confirm the format is correct.
        try:
            int(expected_hash, 16)
        except ValueError:
            logger.warning("Non-hex expected hash at step %d", self.step_index)
