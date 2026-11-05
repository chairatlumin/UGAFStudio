from __future__ import annotations

import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Protocol

import numpy as np
from loguru import logger

from qa_framework.gameplay_agent.actions import Action, ActionExecutor
from qa_framework.gameplay_agent.base import GameplayAgent
from qa_framework.gameplay_agent.vlm_agent import VLMAgent, VLMBackend

_ACTION_LOGGER = logger.bind(name="gameplay_agent.moa")

# Whitelist of key names accepted by the key_press / key_hold / key_release handlers.
ALLOWED_KEYS = frozenset(
    {
        "w",
        "a",
        "s",
        "d",
        "space",
        "enter",
        "escape",
        "tab",
        "e",
        "q",
        "shift",
        "arrow_up",
        "arrow_down",
        "arrow_left",
        "arrow_right",
    }
)
ALLOWED_BUTTONS = frozenset({"left", "right", "middle"})

# Actions that may be produced by sub-agents (mirrors the live-script whitelist).
ALLOWED_ACTIONS = [
    "key_press",
    "key_release",
    "key_hold",
    "mouse_move",
    "click",
    "type_text",
    "noop",
]


def normalize_action(action: Action) -> Action:
    """Validate an action against the :class:`ActionExecutor` whitelist.

    Unknown action names and disallowed params are replaced with ``noop`` so
    that every vote cast in the MOA is comparable and safe to dispatch.
    """
    if action.action not in ActionExecutor._ACTION_HANDLERS:
        _ACTION_LOGGER.warning("MOA normalize: unknown action {!r} -> noop", action.action)
        return Action(action="noop", params={})

    params: dict[str, Any] = dict(action.params)

    if "key_name" in params and "key" not in params:
        params["key"] = params.pop("key_name")

    if action.action in ("key_press", "key_release", "key_hold"):
        key = str(params.get("key", "")).lower()
        if not key or key not in ALLOWED_KEYS:
            _ACTION_LOGGER.warning("MOA normalize: key {!r} not allowed -> noop", key)
            return Action(action="noop", params={})
        params["key"] = key

    if action.action == "click":
        button = str(params.get("button", "left")).lower()
        if button not in ALLOWED_BUTTONS:
            _ACTION_LOGGER.warning("MOA normalize: button {!r} not allowed -> noop", button)
            return Action(action="noop", params={})
        params["button"] = button

    if action.action == "type_text":
        text = str(params.get("text", "")).strip()[:32]
        if not text or not all(c.isprintable() for c in text):
            _ACTION_LOGGER.warning("MOA normalize: type_text has invalid text -> noop")
            return Action(action="noop", params={})

    return Action(action=action.action, params=params)


def _action_signature(action: Action) -> str:
    """Stable grouping key for an action (used for reward-weighted voting)."""
    parts = [action.action]
    for k in sorted(action.params):
        parts.append(f"{k}={action.params[k]}")
    return "|".join(parts)


class _BackendFactory(Protocol):
    """Callable producing a :class:`VLMBackend` for a given model name."""

    def __call__(self, model: str) -> VLMBackend: ...


class MOAAgent(GameplayAgent):
    """Mixture-of-Agents gameplay agent (v2).

    Combines multiple :class:`VLMAgent` "sub-agents" (each potentially backed
    by a different VLM) by querying them in parallel and taking a
    reward-weighted majority vote over their normalized actions.

    Improvements over v1:

    * **Early-exit (low-latency).** When ``early_exit=True`` the vote concludes
      as soon as the primary sub-agent (index 0) and ``min_votes`` results are
      in — so the loop waits for the *fast* model, not the *slowest* one. Slow
      stragglers are settled in a background drain thread (and only counted as
      backend errors if they actually error, never for merely being slow).
    * **Reward-weighted voting.** ``update_rewards({action_sig: reward})`` feeds
      a per-action EMA reward back into each sub-agent's effective weight, so
      sub-agents whose decisions tend to change the screen (reward > 0) gain
      influence over time. This realizes the "reward-weighted majority" promise
      that the static-weight v1 only described.
    """

    def __init__(
        self,
        agents: list[VLMAgent],
        weights: list[float] | None = None,
        allowed_actions: list[str] | None = None,
        *,
        early_exit: bool = False,
        min_votes: int = 1,
        reward_alpha: float = 1.0,
        reward_ema: float = 0.25,
        backend_timeout: float | None = None,
    ) -> None:
        if not agents:
            msg = "MOAAgent requires at least one sub-agent"
            raise ValueError(msg)
        if weights is None:
            weights = [1.0] * len(agents)
        if len(weights) != len(agents):
            msg = "weights length must match number of agents"
            raise ValueError(msg)

        self._agents = list(agents)
        self._weights = [float(w) for w in weights]
        self.allowed_actions = allowed_actions or list(ALLOWED_ACTIONS)
        self._early_exit = early_exit
        self._min_votes = max(1, min(min_votes, len(agents)))
        self._reward_alpha = float(reward_alpha)
        self._reward_ema = float(reward_ema)

        # Reward-weighted voting state.
        self._reward_history: dict[str, float] = defaultdict(float)

        self._backend_timeout = backend_timeout or self._inherited_timeout()
        self.backend_errors = 0
        self._last_counts: dict[str, float] = {}
        # Whether the most recent decide() produced at least one real vote.
        # Distinct from ``consecutive_fallbacks`` (which counts *sub-agent*
        # fallbacks): a 3-model MOA where 2 models error but 1 succeeds still
        # makes a valid decision, so this stays True and the live loop must NOT
        # back off. Only goes False when *every* sub-agent fails.
        self.last_decision_succeeded = True
        self._lock = threading.Lock()
        # Reused across decides so we don't spin up a fresh pool each step.
        self._executor = ThreadPoolExecutor(max_workers=max(1, len(agents)))

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def _inherited_timeout(self) -> float:
        """Inherit the smallest per-call backend timeout across sub-agents."""
        timeouts: list[float] = []
        for agent in self._agents:
            backend = getattr(agent, "_backend", None)
            timeout = getattr(backend, "_timeout", None)
            if timeout is not None:
                timeouts.append(float(timeout))
        if timeouts:
            return min(timeouts)
        return 90.0

    # ------------------------------------------------------------------
    # Reward-weighted voting
    # ------------------------------------------------------------------

    def update_rewards(self, signature_to_reward: dict[str, float]) -> None:
        """Feed a per-action-signature reward map into the voting weights.

        Each entry updates an EMA of that action's observed reward; the EMA is
        then folded into the effective weight used by :meth:`_vote` via
        ``effective = base * (1 + reward_alpha * reward_ema)``.
        """
        with self._lock:
            for sig, observed in signature_to_reward.items():
                prev = self._reward_history.get(sig, 0.0)
                self._reward_history[sig] = (
                    prev * (1.0 - self._reward_ema) + float(observed) * self._reward_ema
                )

    def _effective_weight(self, idx: int, action: Action) -> float:
        """Base weight scaled by the action's reward EMA (>= 0)."""
        base = self._weights[idx]
        ema = self._reward_history.get(_action_signature(action), 0.0)
        return base * (1.0 + self._reward_alpha * ema)

    # ------------------------------------------------------------------
    # GameplayAgent interface
    # ------------------------------------------------------------------

    def observe(self, frame: Any) -> Any:
        """A frame is already pixel-ready; pass it through unchanged."""
        return frame

    @property
    def consecutive_fallbacks(self) -> int:
        """Expose backend error count so callers can apply back-off logic."""
        return self.backend_errors

    def learn(self, reward: float, done: bool) -> None:
        """No-op; sub-agents manage their own episode logs."""

    # ------------------------------------------------------------------
    # Decision / voting
    # ------------------------------------------------------------------

    def decide(  # type: ignore[override]
        self,
        state_sig: Any = None,
        ocr_words: Any = None,
        frame: np.ndarray | None = None,
        history: Any = None,
        observation: Any = None,
        context: str | None = None,
        strategy: str | None = None,
        menu_keywords: list[str] | None = None,
        **kwargs: Any,
    ) -> Action:
        """Query sub-agents in parallel and return the reward-weighted majority action.

        Also accepts the VLMAgent-compatible keyword form
        ``decide(observation=..., context=..., state_sig=..., strategy=...,
        menu_keywords=...)`` so the MOA can be dropped into the live gameplay
        loop as a drop-in replacement. ``strategy`` / ``menu_keywords`` are
        accepted for signature compatibility and forwarded to sub-agents.
        """
        _ = strategy
        _ = menu_keywords
        obs = frame if frame is not None else observation
        ctx = self._build_context(ocr_words, history) or context

        futures: dict[Future[Action], int] = {
            self._executor.submit(self._query, agent, obs, ctx, state_sig): i
            for i, agent in enumerate(self._agents)
        }

        votes: list[tuple[int, Action]] = []
        # Futures settled in the foreground (so we never double-count errors in
        # both the decide loop and the background drain).
        settled: set[Future[Action]] = set()

        if self._early_exit:
            # Conclude as soon as the primary (index 0) + min_votes are in. We
            # inspect results via as_completed but STOP iterating the moment the
            # trigger condition is met, and only the *unprocessed* stragglers are
            # handed to the background drain (which re-uses `settled` to avoid
            # re-counting the same errors).
            trig = threading.Event()
            try:
                for fut in as_completed(list(futures.keys()), timeout=self._backend_timeout + 5.0):
                    if trig.is_set():
                        break
                    idx = futures[fut]
                    settled.add(fut)
                    try:
                        result = fut.result()
                    except FuturesTimeout:
                        continue
                    except Exception as exc:
                        _ACTION_LOGGER.error("MOA sub-agent {} failed: {}", idx, exc)
                        with self._lock:
                            self.backend_errors += 1
                        continue
                    votes.append((idx, normalize_action(result)))
                    if any(i == 0 for i, _ in votes) and len(votes) >= self._min_votes:
                        trig.set()
                        break
            except FuturesTimeout:
                # Any futures still pending when the timeout hits are slow, not
                # errored; they are abandoned (the pool worker finishes the call
                # harmlessly and the result is discarded). Early-exit returns on
                # the majority, not the slowest model.
                pass
        else:
            # Wait for every sub-agent (each bounded by the backend timeout).
            for fut, idx in futures.items():
                settled.add(fut)
                try:
                    result = fut.result(timeout=self._backend_timeout + 5.0)
                except FuturesTimeout:
                    _ACTION_LOGGER.warning(
                        "MOA sub-agent {} timed out after {:.1f}s",
                        idx,
                        self._backend_timeout,
                    )
                    with self._lock:
                        self.backend_errors += 1
                    continue
                except Exception as exc:
                    _ACTION_LOGGER.error("MOA sub-agent {} failed: {}", idx, exc)
                    with self._lock:
                        self.backend_errors += 1
                    continue
                votes.append((idx, normalize_action(result)))

        if not votes:
            _ACTION_LOGGER.warning("MOA: all sub-agents failed; falling back to first agent")
            self.last_decision_succeeded = False
            try:
                return self._agents[0].decide(obs, context=ctx, state_sig=state_sig)
            except Exception:
                return Action(action="noop", params={})

        winner = self._vote(votes)
        self.last_decision_succeeded = True
        _ACTION_LOGGER.info("MOA vote: {} (counts={})", winner.action, self._last_counts)
        return winner

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query(
        self, agent: VLMAgent, frame: Any, context: str | None, state_sig: str | None
    ) -> Action:
        """Call a single sub-agent, treating an internal fallback as a failure.

        ``VLMAgent.decide`` swallows backend/parse errors internally and returns
        a fallback action (e.g. ``key_press`` -> normalized to ``noop``) rather
        than raising. If we counted that fallback as a real vote, a transient
        backend error would silently dilute the majority toward ``noop`` and
        ``backend_errors`` would never increment.  So we snapshot the agent's
        ``consecutive_fallbacks`` counter before/after the call: an increase
        means the sub-agent fell back (backend error or unparseable response),
        which we surface as an exception so the caller excludes the vote and
        counts the failure.  Each sub-agent owns its own ``consecutive_fallbacks``
        and is queried by exactly one future, so this snapshot is race-free.
        """
        before = agent.consecutive_fallbacks
        try:
            result = agent.decide(frame, context=context, state_sig=state_sig)
        except Exception:
            # A genuine raise (not just an internal fallback) propagates as-is.
            raise
        if agent.consecutive_fallbacks > before:
            msg = "sub-agent fell back internally (backend error / parse failure)"
            _ACTION_LOGGER.warning(msg)
            raise RuntimeError(msg)
        return result

    def _vote(self, votes: list[tuple[int, Action]]) -> Action:
        """Return the reward-weighted majority action.

        Winner is the action with the highest summed *effective* sub-agent
        weight (base weight scaled by that action's reward EMA).  Ties are
        broken by the single highest contributing effective weight, then by
        the earliest contributing agent index.
        """
        total: dict[str, float] = {}
        max_weight: dict[str, float] = {}
        order: dict[str, int] = {}

        for idx, action in votes:
            key = action.action
            weight = self._effective_weight(idx, action)
            total[key] = total.get(key, 0.0) + weight
            max_weight[key] = max(max_weight.get(key, 0.0), weight)
            if key not in order:
                order[key] = idx

        ranked = sorted(total, key=lambda k: (-total[k], -max_weight[k], order[k]))
        self._last_counts = {k: round(total[k], 3) for k in ranked}

        winner_key = ranked[0]
        for idx, action in votes:
            if action.action == winner_key:
                return action
        return votes[0][1]

    @staticmethod
    def _build_context(ocr_words: Any, history: Any) -> str | None:
        """Build an OCR/history context string for the sub-agents."""
        parts: list[str] = []

        if ocr_words:
            parts.append("OCR detected text on screen:")
            for w in ocr_words:
                if isinstance(w, dict):
                    parts.append(
                        '  "{}" at ({},{})'.format(w.get("text", ""), w.get("x", 0), w.get("y", 0))
                    )
                else:
                    parts.append(f"  {w}")

        if history:
            parts.append("Recent action history:")
            for entry in list(history)[-5:]:
                parts.append(f"  - {entry}")

        return "\n".join(parts) if parts else None

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_backends(
        cls,
        *,
        backend_factory: _BackendFactory,
        specs: list[tuple[str, float]],
        allowed_actions: list[str],
        system_prompt: str = "",
        cache: Any = None,
        strategy: str | None = None,
        menu_keywords: list[str] | None = None,
        max_tokens: int = 128,
        timeout: float = 90.0,
        **kwargs: Any,
    ) -> MOAAgent:
        """Build an :class:`MOAAgent` from a backend factory + (model, weight) specs.

        ``backend_factory(model)`` is called once per spec to construct a
        :class:`VLMBackend`.  This keeps live wiring (LM Studio / OpenAI-compatible)
        in one place instead of duplicating the sub-agent construction loop.
        """
        if not specs:
            msg = "MOAAgent.from_backends requires at least one (model, weight) spec"
            raise ValueError(msg)

        sub_agents: list[VLMAgent] = []
        for model, weight in specs:
            backend = backend_factory(model)
            sub_agents.append(
                VLMAgent(
                    backend=backend,
                    allowed_actions=allowed_actions,
                    system_prompt=system_prompt,
                    cache=cache,
                    strategy=strategy,
                    menu_keywords=list(menu_keywords) if menu_keywords else None,
                )
            )
        _ = max_tokens  # accepted for parity with the live backend config
        _ = timeout
        return cls(sub_agents, weights=[w for _, w in specs], **kwargs)
