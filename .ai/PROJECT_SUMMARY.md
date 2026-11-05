# Shinebringer Demo Automation — Project Summary

**Date**: 2026-09-04
**Game**: Shinebringer Demo (Steam App 4077460, UE5.7.4)
**Goal**: Autonomous gameplay automation

---

## ✅ What Works

### Input Injection
- **`swishflow.py`** — uses `AttachThreadInput` to bind input threads
  - This is the ONLY method that works with UE5 Raw Input
  - Supports: W/A/S/D, E, F, Enter, Esc, Space, Tab
  - All other methods (SendInput, keybd_event, PostMessage, ViGEmBus, pyautogui, etc.) FAIL

### Vision
- **OCR** via pytesseract — reads game state (menu, tutorial, combat, death)
- **Color detection** via OpenCV HSV — finds light orbs (yellow/white/red/orange)
- **Template matching** for UI elements

### Automation
- **Menu** → clicks Play Showcase
- **Tutorial** → moves forward, interacts, collects light
- **Combat** → attacks enemies, dodges
- **Death** → auto-respawn

---

## 📁 Files Created/Modified

| File | Status | Description |
|------|--------|-------------|
| `.ai/swishflow.py` | ✅ Modified | Added Q/R/1-5 key bindings |
| `.ai/auto_continue.py` | ✅ Created | Main autoplay bot with vision |
| `.ai/vision_bot.py` | ✅ Created | Vision-based gameplay bot |
| `.ai/autoplay.py` | ✅ Created | Early autoplay prototype |
| `.ai/a2a/a2a_server.py` | ✅ Created | FastAPI A2A server for OpenCode agents |
| `.ai/a2a/start.sh` | ✅ Created | A2A server start script |
| `reports/qa_plan_shinebringer_lean_20260904.md` | ✅ Created | QA test plan |
| `reports/product-gate_shinebringer_20260904.md` | ✅ Created | Product gate checklist |

---

## ❌ What Doesn't Work

| Method | Reason |
|--------|--------|
| SendInput / keybd_event | UE5 Raw Input bypasses these |
| PostMessage / SendMessage | Not received by UE5 |
| ViGEmBus virtual gamepad | Detected but A button doesn't navigate menus |
| pyautogui / pydirectinput | Blocked by Raw Input |
| Steam Input API | Read-only, cannot send input |
| UE4SS | Incomplete, game-specific signatures needed |

---

## 📊 Test Results

### Input Methods Tried
1. ViGEmBus XInput (VX360Gamepad) — detected, no menu response
2. ViGEmBus DS4 (VDS4Gamepad) — minor pixel change, no navigation
3. SendInput (VK + scancode) — no response
4. keybd_event — no response
5. PostMessage / SendMessage — no response
6. AttachThreadInput + keybd_event — no response
7. AttachThreadInput + SendInput — sent: 0 (failed)
8. pyautogui / pydirectinput — no response
9. keyboard / pynput — no response
10. computer_use (cua-driver) — no response
11. **AttachThreadInput (swishflow.py)** — ✅ WORKS

### Gameplay Results
- **Menu → Play Showcase**: ✅ Success
- **Tutorial**: ✅ Completed (gather light orb)
- **Combat**: ✅ Engaging enemies
- **Play time**: ~13 minutes before game closed
- **Death/Respawn**: ✅ Working

---

## 🔑 Key Insight

**`AttachThreadInput`** is the secret. When you attach your thread's input queue to the game's thread, SendInput events are processed by the game's message loop. Without this, UE5 Raw Input ignores all synthetic input.

```python
# The magic line
user32.AttachThreadInput(current_tid, game_tid, True)
# ... send input ...
user32.AttachThreadInput(current_tid, game_tid, False)
```

---

## 🛠️ How to Run

```bash
# Start game
"D:/SteamLibrary/steamapps/common/SHINEBRINGERS Demo/SwishAndFlick/Binaries/Win64/SwishAndFlickDemo.exe" -windowed -ResX=1920 -ResY=1080

# Wait 15 seconds for game to load

# Run autoplay bot
cd C:/Users/Admin/UGAFStudio
C:/Python314/python.exe .ai/auto_continue.py
```

---

## 📋 Next Steps

1. **Improve combat AI** — better enemy tracking, ability usage, potion management
2. **Handle Steam overlay** — detect and dismiss with Esc
3. **Wave completion** — detect wave end and transition
4. **Crafting** — automate potion/spell crafting between waves
5. **Error recovery** — handle unexpected states gracefully
6. **Long-run stability** — run for hours without getting stuck

---

## 📝 Notes

- Game PID changes on each launch — bot detects it dynamically
- swishflow.py saves screenshots to `screenshots/swishflow/`
- OCR is slow (~2-3 seconds per read) — use sparingly
- Bright orb detection works but needs tuning for different lighting conditions
