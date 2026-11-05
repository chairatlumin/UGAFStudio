#!/usr/bin/env python3
"""Shinebringer Demo vision-based auto-play bot.

Uses swishflow.py for input (AttachThreadInput works!).
Uses OpenCV template matching + color detection for state.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

GAME = str(Path(__file__).parent / "swishflow.py")
TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

TEMPLATES = {
    "menu_play": None,      # Will be loaded dynamically
    "light_orb": None,
    "monster": None,
}

SCREENSHOT_DIR = Path(__file__).parent.parent / "screenshots" / "swishflow"


def run(cmd: str, *args: str, timeout: int = 30) -> str:
    """Run swishflow command."""
    result = subprocess.run(
        [sys.executable, GAME, cmd, *args],
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout + result.stderr


def capture() -> np.ndarray:
    """Capture game screen via swishflow probe + parse."""
    out = run("probe")
    # Find the latest screenshot saved by probe
    pngs = sorted(SCREENSHOT_DIR.glob("probe_*.png"))
    if pngs:
        return cv2.imread(str(pngs[-1]))
    return np.zeros((100, 100, 3), dtype=np.uint8)


def find_template(screen: np.ndarray, template: np.ndarray, threshold: float = 0.7) -> tuple[int, int] | None:
    """Find template in screen, return center coords or None."""
    if template is None or screen is None:
        return None
    h, w = template.shape[:2]
    sh, sw = screen.shape[:2]
    if h > sh or w > sw:
        return None
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        x = max_loc[0] + w // 2
        y = max_loc[1] + h // 2
        return (x, y)
    return None


def find_bright_orbs(screen: np.ndarray, min_area: int = 30) -> list[tuple[int, int]]:
    """Find bright/glowing orbs (light shards) in the game."""
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    # Bright yellow/gold detection
    lower_y = np.array([15, 80, 180])
    upper_y = np.array([45, 255, 255])
    mask_y = cv2.inRange(hsv, lower_y, upper_y)
    # Bright white detection
    lower_w = np.array([0, 0, 220])
    upper_w = np.array([180, 50, 255])
    mask_w = cv2.inRange(hsv, lower_w, upper_w)
    # Bright red/orange detection (light orbs in 3D world)
    lower_r = np.array([0, 50, 200])
    upper_r = np.array([10, 255, 255])
    mask_r1 = cv2.inRange(hsv, lower_r, upper_r)
    lower_r2 = np.array([170, 50, 200])
    upper_r2 = np.array([180, 255, 255])
    mask_r2 = cv2.inRange(hsv, lower_r2, upper_r2)
    mask_r = cv2.bitwise_or(mask_r1, mask_r2)
    combined = cv2.bitwise_or(mask_y, mask_w)
    combined = cv2.bitwise_or(combined, mask_r)
    # Morph to clean up
    kernel = np.ones((5,5), np.uint8)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results = []
    for c in contours:
        area = cv2.contourArea(c)
        if area > min_area:
            M = cv2.moments(c)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                results.append((cx, cy, area))
    # Sort by area (largest first)
    results.sort(key=lambda x: x[2], reverse=True)
    return [(x, y) for x, y, a in results]


def find_enemies(screen: np.ndarray) -> list[tuple[int, int]]:
    """Find enemies by detecting red/dark shapes."""
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    # Red detection (enemies, monsters)
    lower1 = np.array([0, 100, 100])
    upper1 = np.array([10, 255, 255])
    lower2 = np.array([170, 100, 100])
    upper2 = np.array([180, 255, 255])
    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    combined = cv2.bitwise_or(mask1, mask2)
    kernel = np.ones((5,5), np.uint8)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results = []
    for c in contours:
        area = cv2.contourArea(c)
        if area > 100:
            M = cv2.moments(c)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                results.append((cx, cy, area))
    results.sort(key=lambda x: x[2], reverse=True)
    return [(x, y) for x, y, a in results]


def find_ui_button(screen: np.ndarray, text_hint: str = "") -> tuple[int, int] | None:
    """Find UI buttons by looking for rectangular bright regions in lower half."""
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    # Look for bright rectangular regions (buttons)
    _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        # Buttons are typically in lower portion, wider than tall
        if h > 200 and w > 40 and h < 200 and w/h < 10:
            return (x + w//2, y + h//2)
    return None


def is_in_game(screen: np.ndarray) -> bool:
    """Check if we're in actual gameplay (not menu/tutorial)."""
    # Gameplay typically has more color variation and no large text blocks
    text = run("probe")
    lines = text.splitlines()
    word_count = sum(1 for l in lines if l.strip().startswith("("))
    # Menu has many OCR'd words, gameplay has fewer
    return word_count < 20


def is_tutorial(screen: np.ndarray) -> bool:
    """Check if tutorial text is on screen."""
    text = run("probe").lower()
    return any(w in text for w in ["basic", "controls", "prepare", "spellbooks", "gather the light"])


def is_menu(screen: np.ndarray) -> bool:
    """Check if main menu is visible."""
    text = run("probe").lower()
    return all(w in text for w in ["play", "showcase", "option", "credits", "exit"])


def auto_play() -> None:
    """Main auto-play loop."""
    print("=== Vision-Based Auto-Play Bot ===")
    print("Using swishflow.py for input (AttachThreadInput)")
    print("Press Ctrl+C to stop\n")

    step = 0
    state = "menu"

    try:
        while True:
            step += 1
            screen = capture()

            if screen is None or screen.size == 0:
                time.sleep(1)
                continue

            # Determine state
            if is_menu(screen):
                state = "menu"
            elif is_tutorial(screen):
                state = "tutorial"
            else:
                state = "gameplay"

            print(f"[Step {step}] State: {state}")

            if state == "menu":
                # Click Play Showcase
                run("click", "768", "475", "2")
                time.sleep(2)
                run("key", "enter", "0.5")
                time.sleep(2)

            elif state == "tutorial":
                # Move forward and interact
                orbs = find_bright_orbs(screen)
                if orbs:
                    # Move toward nearest orb
                    target = orbs[0]
                    cx, cy = target
                    # Calculate direction from center
                    h, w = screen.shape[:2]
                    dx = cx - w//2
                    dy = cy - h//2
                    if dy > 50:
                        run("key", "w", "0.5")
                    if dx < -50:
                        run("key", "a", "0.3")
                    elif dx > 50:
                        run("key", "d", "0.3")
                    run("key", "e", "0.3")
                else:
                    # Systematic exploration: cycle through directions
                    run("key", "w", "0.5")
                    run("key", "e", "0.3")

            elif state == "gameplay":
                # Look for enemies
                enemies = find_enemies(screen)
                if enemies:
                    # Attack nearest enemy
                    target = enemies[0]
                    run("key", "e", "0.3")
                    run("key", "w", "0.2")
                else:
                    # Collect light orbs
                    orbs = find_bright_orbs(screen)
                    if orbs:
                        run("key", "w", "0.5")
                        run("key", "e", "0.3")
                    else:
                        # Explore
                        run("key", "w", "0.5")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print(f"\n=== Bot stopped at step {step} ===")


if __name__ == "__main__":
    auto_play()
