"""Foreground keyboard/mouse interaction for declarative gameplay QA.

The public action format is intentionally small and engine-agnostic:
``press``, ``hold``, ``release``, ``interact``, ``move``, ``look``, ``click``,
``wait`` and ``wait_for``.  The controller is injectable so all behavior can
be tested without launching a game.
"""

from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol


class InputController(Protocol):
    def press(self, key: str) -> None: ...

    def hold(self, key: str) -> None: ...

    def release(self, key: str) -> None: ...

    def move(self, dx: int, dy: int) -> None: ...

    def click(self, x: int | None = None, y: int | None = None) -> None: ...


@dataclass(frozen=True)
class InteractionResult:
    action: str
    passed: bool
    message: str


class WindowsInputController:
    """Send foreground input to the window belonging to a launched PID."""

    _SCAN_CODES = {
        "w": 0x11,
        "a": 0x1E,
        "s": 0x1F,
        "d": 0x20,
        "e": 0x12,
        "enter": 0x1C,
        "escape": 0x01,
        "esc": 0x01,
        "space": 0x39,
        "shift": 0x2A,
        "ctrl": 0x1D,
        "tab": 0x0F,
    }

    def __init__(self, pid: int, *, sleep: Callable[[float], None] = time.sleep) -> None:
        self.pid = pid
        self._sleep = sleep
        self._held: set[str] = set()
        if not hasattr(ctypes, "windll"):
            raise OSError("Foreground SendInput is only available on Windows.")
        self._user32 = ctypes.windll.user32

    def _focus(self) -> tuple[int, int]:
        """Find the game window, attach input threads, and return thread IDs.

        Returns (game_tid, current_tid) so the caller can detach later.
        """
        target_hwnd: int = 0
        game_tid: int | None = None

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def callback(hwnd: int, _param: int) -> bool:
            nonlocal target_hwnd, game_tid
            process_id = ctypes.c_ulong()
            thread_id = ctypes.c_ulong()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if (
                process_id.value == self.pid
                and self._user32.IsWindowVisible(hwnd)
                and target_hwnd == 0
            ):
                target_hwnd = hwnd
                game_tid = thread_id.value
            return True

        self._user32.EnumWindows(callback, 0)
        if target_hwnd:
            ctypes.windll.user32.AttachThreadInput(
                ctypes.c_uint(int(ctypes.windll.kernel32.GetCurrentThreadId())),
                ctypes.c_uint(game_tid or 0),
                True,
            )
            self._user32.SetForegroundWindow(target_hwnd)
            self._sleep(0.05)
        return (game_tid or 0, int(ctypes.windll.kernel32.GetCurrentThreadId()))

    def _detach(self, game_tid: int, current_tid: int) -> None:
        """Detach the input queues."""
        ctypes.windll.user32.AttachThreadInput(
            ctypes.c_uint(current_tid),
            ctypes.c_uint(game_tid),
            False,
        )

    def _keyboard(self, key: str, flags: int, game_tid: int, current_tid: int) -> None:
        scan = self._SCAN_CODES.get(key.lower())
        if scan is None:
            raise ValueError(f"Unsupported game key: {key!r}")
        extra = ctypes.POINTER(ctypes.c_ulong)()

        class KeyboardInput(ctypes.Structure):
            _fields_ = [
                ("vk", ctypes.c_ushort),
                ("scan", ctypes.c_ushort),
                ("flags", ctypes.c_uint32),
                ("time", ctypes.c_uint32),
                ("extra", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class InputUnion(ctypes.Union):
            _fields_ = [("ki", KeyboardInput)]

        class Input(ctypes.Structure):
            _fields_ = [("type", ctypes.c_uint32), ("u", InputUnion)]

        event = Input(1, InputUnion(ki=KeyboardInput(0, scan, flags, 0, extra)))
        sent = self._user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input))
        if sent != 1:
            # Some elevated/fullscreen Unreal windows reject SendInput while
            # still accepting the legacy keyboard event API.
            self._user32.keybd_event(0, scan, flags, 0)
            self._detach(game_tid, current_tid)
            return
        self._detach(game_tid, current_tid)

    def press(self, key: str) -> None:
        game_tid, current_tid = self._focus()
        try:
            self._keyboard(key, 0x0008, game_tid, current_tid)
            self._sleep(0.05)
            self._keyboard(key, 0x0008 | 0x0002, game_tid, current_tid)
        finally:
            self._detach(game_tid, current_tid)

    def hold(self, key: str) -> None:
        normalized = key.lower()
        if normalized not in self._held:
            game_tid, current_tid = self._focus()
            try:
                self._keyboard(normalized, 0x0008, game_tid, current_tid)
                self._held.add(normalized)
            finally:
                self._detach(game_tid, current_tid)

    def release(self, key: str) -> None:
        normalized = key.lower()
        if normalized in self._held:
            game_tid, current_tid = self._focus()
            try:
                self._keyboard(normalized, 0x0008 | 0x0002, game_tid, current_tid)
                self._held.discard(normalized)
            finally:
                self._detach(game_tid, current_tid)


    def move(self, dx: int, dy: int) -> None:
        game_tid, current_tid = self._focus()
        try:
            self._user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)
        finally:
            self._detach(game_tid, current_tid)

    def click(self, x: int | None = None, y: int | None = None) -> None:
        game_tid, current_tid = self._focus()
        try:
            if x is not None and y is not None:
                self._user32.SetCursorPos(int(x), int(y))
            self._user32.mouse_event(0x0002, 0, 0, 0, 0)
            self._user32.mouse_event(0x0004, 0, 0, 0, 0)
        finally:
            self._detach(game_tid, current_tid)

    def release_all(self) -> None:
        for key in tuple(self._held):
            self.release(key)


def execute_actions(
    actions: list[dict[str, Any]],
    controller: InputController,
    *,
    capture: Callable[[], Any] | None = None,
    assert_frame: Callable[[Any, list[dict[str, Any]]], list[Any]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[InteractionResult]:
    """Execute configured actions and return one result per action."""
    results: list[InteractionResult] = []
    try:
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                raise ValueError(f"Action at index {index} must be an object.")
            kind = str(action.get("action", ""))
            if kind in {"press", "interact"}:
                controller.press(str(action.get("key", "e" if kind == "interact" else "")))
            elif kind == "hold":
                controller.hold(str(action["key"]))
            elif kind == "release":
                controller.release(str(action["key"]))
            elif kind == "move":
                direction = str(action.get("direction", "forward")).lower()
                key = {"forward": "w", "back": "s", "left": "a", "right": "d"}.get(direction)
                if key is None:
                    raise ValueError(f"Unsupported movement direction: {direction!r}")
                controller.hold(key)
                sleep(float(action.get("seconds", 1.0)))
                controller.release(key)
            elif kind == "look":
                controller.move(int(action.get("dx", 0)), int(action.get("dy", 0)))
            elif kind == "click":
                controller.click(action.get("x"), action.get("y"))
            elif kind == "wait":
                sleep(float(action.get("seconds", 1.0)))
            elif kind == "wait_for":
                if capture is None or assert_frame is None:
                    raise ValueError("wait_for requires capture and assertion services.")
                deadline = time.monotonic() + float(action.get("timeout", 15.0))
                assertion = action.get("assertion")
                if not isinstance(assertion, dict):
                    raise ValueError("wait_for requires an assertion object.")
                while True:
                    checks = assert_frame(capture(), [assertion])
                    if all(getattr(check, "passed", False) for check in checks):
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"wait_for timed out: {assertion.get('name', 'assertion')}"
                        )
                    sleep(0.25)
            else:
                raise ValueError(f"Unsupported interaction action: {kind!r}")
            results.append(InteractionResult(kind, True, "completed"))
    finally:
        release_all = getattr(controller, "release_all", None)
        if callable(release_all):
            release_all()
    return results
