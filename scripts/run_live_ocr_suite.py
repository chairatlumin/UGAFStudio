"""Run the per-game OCR/visual-assertion suites against the live Steam games.

This is the live-verification entry point for NEXT_SPRINT_PLAN.md. It launches
each selected game on D:\\SteamLibrary, captures a post-startup frame, runs the
OCR/color assertions defined in qa_framework/examples/*_ocr.json, and writes one
combined HTML report.

NOTE: capturing a fullscreen D3D game from a background process is unreliable on
Windows (PrintWindow returns black; mss needs the game to be the foreground
window). Run this script from a session where the launched game can be brought
to the foreground, or the color assertions (frame-is-non-black) will still pass
while OCR assertions may miss text. Tune `region` / `psm` / `confidence_threshold`
in the JSON suites from the captured evidence as needed.

Usage:
    C:\\Python314\\python.exe scripts/run_live_ocr_suite.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from qa_framework.gameplay.coordinator import run_combined_suite  # noqa: E402

COMBINED_SUITE = PROJECT_ROOT / "qa_framework" / "examples" / "gameplay_combined_ocr.json"
OUTPUT_DIR = PROJECT_ROOT / "reports" / "live_ocr"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Running combined OCR suite: {COMBINED_SUITE}")
    print(f"Report output dir: {OUTPUT_DIR}")
    try:
        results = run_combined_suite(COMBINED_SUITE, output_dir=OUTPUT_DIR)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR running suite: {exc}")
        return 1

    passed = 0
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        started = "started" if r.started else "not-started"
        n_assert = len(r.assertions)
        n_ok = sum(1 for a in r.assertions if a.passed)
        print(
            f"[{status}] {r.game_name} (app {r.app_id}) {started} "
            f"assertions {n_ok}/{n_assert} cleanup={r.cleanup.status if r.cleanup else 'n/a'}"
        )
        for a in r.assertions:
            mark = "ok " if a.passed else "XX "
            print(f"    {mark} {a.name}: {a.message}")
        if r.passed:
            passed += 1

    print(f"\nSummary: {passed}/{len(results)} games passed")
    print(f"Reports: {OUTPUT_DIR}")
    return 0 if passed == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
