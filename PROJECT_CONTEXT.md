# Project Context

Project

UGAF Studio

Current Version

0.1.0

Current Sprint

Sprint 5.1 (Multi-monitor Foundation) — complete

Current Architecture

MainWindow (UI only) ↓

CaptureController / QAController ↓

Services (CaptureService, ScreenshotService, MouseService, KeyboardService,
HotkeyService, GamepadService, MacroRecorder/Player, ScriptRunner,
ObjectDetector, TemplateMatcher, ColorDetector, OCREngine, TestRunner,
ReportGenerator) ↓

Widgets (Preview, Status, Logger, Dashboard, RegionSelector)

Completed

- Desktop Capture (virtual desktop + per-monitor)
- Live Preview
- FPS Counter
- Mouse Tracking
- Resolution
- Pixel Inspector (RGB + HEX)
- Screenshot
- Region Capture
- Vision: Template Matching, Color Detection, OCR
- Automation: Mouse, Keyboard, Hotkeys, Gamepad, Macro, Script Runner
- QA: Test Runner, HTML Report, Dashboard

Next

- Vision: OCR tuning, object detection polish
- Automation: macro UI recording
- QA: scripted test cases from disk
