#!/usr/bin/env python3
"""Shinebringer Demo auto-play bot.

Loop: OCR -> decide -> input -> repeat.
"""
from __future__ import annotations

import subprocess
import sys
import time

import cv2
import numpy as np
import pytesseract

GAME = r"C:\Users\Admin\UGAFStudio\.ai\swishflow.py"
TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESS


def run(cmd: str, *args: str) -> str:
    """Run swishflow command and return stdout."""
    result = subprocess.run(
        [sys.executable, GAME, cmd, *args],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout + result.stderr


def ocr_state() -> list[str]:
    """Read game state via OCR."""
    out = run("probe")
    words = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("(") and ")" in line:
            # Parse tuple like: ('word', x, y, w, h)
            try:
                parts = line.strip("()").split(",")
                word = parts[0].strip("'\"")
                words.append(word)
            except:
                pass
    return words


def has_word(words: list[str], *targets: str) -> bool:
    """Check if any target word appears in OCR output."""
    text = " ".join(words).lower()
    return any(t.lower() in text for t in targets)


def auto_step(words: list[str]) -> str:
    """Decide action based on game state. Returns action description."""
    # Tutorial phase - just press enter/w
    if has_word(words, "basic", "controls", "prepare", "spellbooks"):
        return "tutorial"
    # Need to gather light
    elif has_word(words, "gather", "light"):
        return "gather"
    # Crafting phase
    elif has_word(words, "craft", "health", "potion", "spell"):
        return "craft"
    # Combat / wave
    elif has_word(words, "monster", "wave", "attack", "defend"):
        return "combat"
    # Movement
    elif has_word(words, "movement", "travel"):
        return "move"
    else:
        return "explore"


def main() -> None:
    print("=== Shinebringer Auto-Bot Started ===")
    print("Press Ctrl+C to stop\n")

    step = 0
    last_action = ""

    try:
        while True:
            step += 1
            words = ocr_state()
            action = auto_step(words)

            print(f"[Step {step}] State: {action}")

            if action == "tutorial":
                # Press W to move forward + Enter to advance dialog
                run("key", "w", "0.5")
                time.sleep(0.5)
                run("key", "enter", "0.3")
            elif action == "gather":
                # Move toward light (W + interact E)
                run("key", "w", "1.0")
                run("key", "e", "0.3")
            elif action == "craft":
                # Craft health potion (press 1)
                run("key", "1", "0.3")
                run("key", "e", "0.3")
            elif action == "combat":
                # Attack (E) and dodge (A/D)
                run("key", "e", "0.3")
                run("key", "a", "0.2")
                run("key", "e", "0.3")
                run("key", "d", "0.2")
            elif action == "move":
                # Move forward
                run("key", "w", "1.0")
            else:  # explore
                # Wandering
                run("key", "w", "0.5")
                run("key", "a", "0.3")
                run("key", "w", "0.5")
                run("key", "d", "0.3")

            # Brief pause between actions
            time.sleep(1)

            # Every 10 steps, print full state
            if step % 10 == 0:
                print(f"  Words: {' '.join(words[:15])}...")
                print()

    except KeyboardInterrupt:
        print(f"\n=== Bot stopped at step {step} ===")


if __name__ == "__main__":
    main()
