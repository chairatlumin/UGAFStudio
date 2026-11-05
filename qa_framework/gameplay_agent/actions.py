from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

_ACTION_LOGGER = logger.bind(name="gameplay_agent.action")


class ActionExecutor:
    """Maps an :class:`Action` to the existing automation services.

    Supported action names and their parameter mappings:

    - ``key_press`` / ``key_release`` / ``key_hold`` — uses :class:`KeyboardService`
    - ``mouse_move`` — uses :class:`MouseService`
    - ``click`` — uses :class:`MouseService`
    - ``type_text`` — uses :class:`KeyboardService`
    """

    def __init__(self, *, keyboard: Any = None, mouse: Any = None) -> None:
        from app.input.keyboard_service import KeyboardService
        from app.input.mouse_service import MouseService

        self._kb = keyboard if keyboard is not None else KeyboardService()
        self._mouse = mouse if mouse is not None else MouseService()

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------

    def dispatch(self, action: Action) -> None:
        """Execute the given *action* by routing to the appropriate service."""
        name = action.action
        params = action.params or {}

        handler = self._ACTION_HANDLERS.get(name)
        if handler is None:
            _ACTION_LOGGER.warning("Unsupported action: {}", name)
            return
        handler(params)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    _default_kb: Any = None
    _default_ms: Any = None

    @staticmethod
    def _get_default_service(service: str) -> Any:
        """Return the default :class:`KeyboardService` or :class:`MouseService`,
        lazily instantiated if not already created."""
        if service == "keyboard":
            from app.input.keyboard_service import KeyboardService

            if ActionExecutor._default_kb is None:
                ActionExecutor._default_kb = KeyboardService()
            return ActionExecutor._default_kb
        if service == "mouse":
            from app.input.mouse_service import MouseService

            if ActionExecutor._default_ms is None:
                ActionExecutor._default_ms = MouseService()
            return ActionExecutor._default_ms
        msg = f"Unknown service: {service}"
        _ACTION_LOGGER.error(msg)
        raise ValueError(msg)

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_key_press(params: dict[str, Any]) -> None:
        key = params.get("key", "space")
        kb = ActionExecutor._get_default_service("keyboard")
        kb.press(str(key))

    @staticmethod
    def _handle_key_release(params: dict[str, Any]) -> None:
        key = params.get("key", "space")
        kb = ActionExecutor._get_default_service("keyboard")
        kb.release(str(key))

    @staticmethod
    def _handle_key_hold(params: dict[str, Any]) -> None:
        key = params.get("key", "space")
        kb = ActionExecutor._get_default_service("keyboard")
        kb.hold(str(key))

    @staticmethod
    def _handle_mouse_move(params: dict[str, Any]) -> None:
        x = params.get("x", 0)
        y = params.get("y", 0)
        ms = ActionExecutor._get_default_service("mouse")
        ms.move(int(x), int(y))

    @staticmethod
    def _handle_click(params: dict[str, Any]) -> None:
        button = params.get("button", "left")
        ms = ActionExecutor._get_default_service("mouse")
        # x/y are absolute screen coordinates when supplied. Passing them to
        # MouseService avoids a move-then-click race with other input events.
        ms.click(
            x=params.get("x"),
            y=params.get("y"),
            button=str(button),
        )

    @staticmethod
    def _handle_type_text(params: dict[str, Any]) -> None:
        text = params.get("text", "")
        kb = ActionExecutor._get_default_service("keyboard")
        kb.write(str(text))

    @staticmethod
    def _handle_noop(params: dict[str, Any]) -> None:
        """Represent an intentional observation-only step without a warning."""
        return None

    _ACTION_HANDLERS: dict[str, Any] = {
        "key_press": _handle_key_press,
        "key_release": _handle_key_release,
        "key_hold": _handle_key_hold,
        "mouse_move": _handle_mouse_move,
        "click": _handle_click,
        "type_text": _handle_type_text,
        "noop": _handle_noop,
    }


@dataclass(frozen=True)
class Action:
    """Represents a single gameplay action with parameters.

    Attributes:
        action: The action name (e.g. "key_press", "mouse_move", "click").
        params: Optional dictionary of parameters specific to the action.
    """

    action: str
    params: dict[str, Any] = field(default_factory=dict)
