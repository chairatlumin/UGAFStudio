# Task: Macro Recording Engine with Live Capture + PySide6 UI

## Context
UGAFStudio has basic `MacroRecorder`/`MacroPlayer` in `app/automation/macro.py` but NO live input capture and NO GUI. The recorder only accepts programmatic `record_*()` calls — there's no way for a user to actually record their keyboard/mouse actions in real-time.

Goal: Add live capture (via pynput) + a PySide6 macro recorder widget so users can record, edit, save, load, and replay macros from the GUI.

## Files to CREATE

### 1. `app/automation/capture.py` — Live Input Capture
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

class CaptureListener(Protocol):
    """Receives raw input events during live capture."""
    def on_key_press(self, key: str) -> None: ...
    def on_key_release(self, key: str) -> None: ...
    def on_mouse_move(self, x: int, y: int) -> None: ...
    def on_mouse_click(self, x: int, y: int, button: str, pressed: bool) -> None: ...
    def on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None: ...

class LiveCapture:
    """Captures keyboard + mouse events via pynput and forwards to a listener."""
    
    def __init__(self, listener: CaptureListener | None = None) -> None:
        self._listener = listener
        self._keyboard_listener = None
        self._mouse_listener = None
        self._capturing = False
    
    @property
    def capturing(self) -> bool: ...
    
    def set_listener(self, listener: CaptureListener | None) -> None: ...
    
    def start(self) -> None:
        """Start listening to keyboard + mouse. Non-blocking (uses pynput threads)."""
        ...
    
    def stop(self) -> None:
        """Stop all listeners."""
        ...
    
    def _on_key_press(self, key) -> None: ...
    def _on_key_release(self, key) -> None: ...
    def _on_mouse_move(self, x, y) -> None: ...
    def _on_mouse_click(self, x, y, button, pressed) -> None: ...
    def _on_mouse_scroll(self, x, y, dx, dy) -> None: ...
```

Key requirements:
- Use `pynput.keyboard.Listener` and `pynput.mouse.Listener`
- Convert pynput key objects to string names (e.g., `Key.ctrl` -> `"ctrl"`, `Key.space` -> `"space"`, `'a'` -> `"a"`)
- Convert pynput button to string (`Button.left` -> `"left"`, `Button.right` -> `"right"`)
- Run listeners in daemon threads (non-blocking)
- Handle exceptions gracefully (pynput can throw on unusual keys)

### 2. `app/automation/macro_recorder.py` — Capture-to-Macro bridge
```python
class CapturingRecorder(CaptureListener):
    """Bridges LiveCapture events to MacroRecorder steps."""
    
    def __init__(
        self,
        recorder: MacroRecorder,
        *,
        capture_mouse_move: bool = False,  # mouse moves are very noisy
        mouse_move_threshold: int = 50,  # pixels
        parent: QObject | None = None,
    ) -> None: ...
    
    def on_key_press(self, key: str) -> None: ...
    def on_key_release(self, key: str) -> None: ...
    def on_mouse_move(self, x: int, y: int) -> None: ...
    def on_mouse_click(self, x: int, y: int, button: str, pressed: bool) -> None: ...
    def on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None: ...
```

### 3. `app/gui/widgets/macro_recorder_widget.py` — PySide6 UI
A QWidget with:
- Record button (QPushButton, toggles start/stop)
- Play button
- Save/Load buttons (QFileDialog for JSON)
- Macro name label
- Steps list (QListWidget showing recorded steps)
- Speed spinbox (0.1x to 10x)
- Status label
- Clear button

Layout:
```
┌─────────────────────────────────┐
│ Macro: [name]          [Clear]  │
├─────────────────────────────────┤
│ [Record] [Play] [Save] [Load]   │
│ Speed: [1.0x ▾]                 │
├─────────────────────────────────┤
│ 1. move(100, 200)     0ms       │
│ 2. click(150, 250, left) 500ms  │
│ 3. key(enter)          200ms    │
│ ...                             │
├─────────────────────────────────┤
│ Status: Recording...            │
└─────────────────────────────────┘
```

Signals:
- `recording_started`
- `recording_stopped`
- `playback_started`
- `playback_stopped`

### 4. `app/controllers/macro_controller.py` — Controller
```python
class MacroController(QObject):
    """Orchestrates macro recording/playback between GUI and services."""
    
    def __init__(
        self,
        mouse_service: MouseService,
        keyboard_service: KeyboardService,
        parent: QObject | None = None,
    ) -> None: ...
    
    def set_widget(self, widget: MacroRecorderWidget) -> None: ...
    def record(self) -> None: ...
    def stop(self) -> None: ...
    def play(self, speed: float = 1.0) -> None: ...
    def load(self, path: Path) -> None: ...
    def save(self, path: Path) -> None: ...
    def clear(self) -> None: ...
```

### 5. Update `app/gui/main_window.py` — Add Macro tab
Add a "Macro" tab containing the MacroRecorderWidget.

### 6. `tests/automation/test_capture.py` — Tests for LiveCapture
- Test that LiveCapture starts/stops without error
- Test that listener receives forwarded events
- Test key/button string conversion
- Mock pynput listeners to avoid real input capture in CI

### 7. `tests/automation/test_macro_recorder_bridge.py` — Tests for CapturingRecorder
- Test key press/release recorded as "key" step
- Test mouse click recorded as "click" step
- Test scroll recorded as "scroll" step
- Test mouse move filtering (threshold)

### 8. `tests/gui/test_macro_recorder_widget.py` — Tests for the widget
- Test widget creates with all child widgets
- Test record button toggles
- Test steps list updates
- Test save/load triggers file dialog

## Dependencies to add to pyproject.toml
```
pynput>=1.8.2
```

## Validation (MUST pass all)
```bash
cd C:/Users/Admin/UGAFStudio
C:/Python314/python.exe -m pytest tests/automation/test_capture.py tests/automation/test_macro_recorder_bridge.py tests/gui/test_macro_recorder_widget.py -v
C:/Python314/python.exe -m pytest tests/ -v
C:/Python314/python.exe -m ruff check .
C:/Python314/python.exe -m ruff format . --check
C:/Python314/python.exe -m mypy qa_framework app
```

## Architecture Rules (from AGENTS.md)
- MainWindow contains UI only
- Controllers orchestrate Services
- Services contain business logic
- Widgets never contain business logic

## Notes
- Keep existing `MacroRecorder`/`MacroPlayer` in `macro.py` unchanged — build on top of them
- Use `PySide6.QtCore.QThread` or `QTimer` for any polling — pynput already uses threads
- For tests, mock pynput listeners (don't capture real input)
- Follow existing code style (ruff line-length=100, double quotes, frozen dataclasses)
- The widget should use `QVBoxLayout`/`QHBoxLayout` (not code-generated UI)
