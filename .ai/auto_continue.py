#!/usr/bin/env python3
"""Shinebringer auto-play: swishflow.py (input) + computer_use (vision)."""
from __future__ import annotations
import subprocess, sys, time, random
from pathlib import Path

GAME = str(Path(__file__).parent / "swishflow.py")

def run(cmd: str, *args: str, timeout: int = 90) -> str:
    try:
        r = subprocess.run([sys.executable, GAME, cmd, *args], capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except: return ""

def get_text() -> str:
    return run("probe").lower()

def is_menu(t: str) -> bool:
    return all(w in t for w in ["play", "showcase", "option", "credits", "exit"])

def is_tutorial(t: str) -> bool:
    return any(w in t for w in ["basic", "controls", "prepare", "spellbooks", "gather"])

def is_combat(t: str) -> bool:
    return any(w in t for w in ["combat", "defeat", "enemies", "wand", "dash"])

def is_dead(t: str) -> bool:
    return "dead" in t and "respawn" in t

def find_orb_color() -> tuple[int, int] | None:
    """Use computer_use to find light orb by color."""
    import cv2, numpy as np
    # This would need computer_use - for now use swishflow capture
    # swishflow saves screenshots to screenshots/swishflow/
    import glob
    pngs = sorted(glob.glob(r"C:\Users\Admin\UGAFStudio\screenshots\swishflow\probe_*.png"))
    if not pngs:
        return None
    img = cv2.imread(pngs[-1])
    if img is None:
        return None

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Bright yellow/gold (light orb)
    mask1 = cv2.inRange(hsv, np.array([15, 80, 180]), np.array([45, 255, 255]))
    # Bright white
    mask2 = cv2.inRange(hsv, np.array([0, 0, 240]), np.array([180, 20, 255]))
    combined = cv2.bitwise_or(mask1, mask2)
    kernel = np.ones((7,7), np.uint8)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) > 30:
            M = cv2.moments(largest)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                return (cx, cy)
    return None

def main() -> None:
    print("=== Shinebringer Auto-Play ===")
    step = 0

    try:
        while True:
            step += 1
            text = get_text()

            if is_menu(text):
                print(f"[{step}] Menu -> Start")
                run("click", "850", "680", "3")
                time.sleep(3)
                run("key", "enter", "1")
                time.sleep(3)

            elif is_dead(text):
                print(f"[{step}] Dead -> Respawn")
                run("key", "enter", "0.5")
                time.sleep(2)
                run("key", "r", "1")
                time.sleep(3)

            elif is_tutorial(text):
                orb = find_orb_color()
                if orb:
                    cx, cy = orb
                    print(f"[{step}] Orb at ({cx},{cy})")
                    if cx < 400:
                        run("key", "a", "0.5")
                    elif cx > 800:
                        run("key", "d", "0.5")
                    run("key", "w", "1.5")
                    run("key", "e", "1")
                else:
                    print(f"[{step}] Tutorial -> Explore")
                    # Systematic exploration
                    phase = step % 8
                    if phase < 2:
                        run("key", "w", "2")
                    elif phase < 3:
                        run("key", "a", "0.5")
                    elif phase < 5:
                        run("key", "w", "2")
                    elif phase < 6:
                        run("key", "d", "0.5")
                    else:
                        run("key", "w", "1")
                        run("key", "e", "0.5")
                    if step % 15 == 0:
                        run("key", "f", "2")

            elif is_combat(text):
                print(f"[{step}] Combat!")
                for _ in range(3):
                    run("key", "e", "0.3")
                    run("key", "w", "0.2")
                run("key", random.choice(["a", "d"]), "0.3")

            else:
                print(f"[{step}] Unknown -> Explore")
                orb = find_orb_color()
                if orb:
                    cx, cy = orb
                    if cx < 400: run("key", "a", "0.3")
                    elif cx > 800: run("key", "d", "0.3")
                    run("key", "w", "1.5")
                    run("key", "e", "0.5")
                else:
                    run("key", "w", "1")
                    run("key", random.choice(["a", "d"]), "0.3")

            time.sleep(0.3)

    except KeyboardInterrupt:
        print(f"\nStopped at {step}")

if __name__ == "__main__":
    main()
