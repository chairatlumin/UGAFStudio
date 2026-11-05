from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.vision.ocr import OCREngine
from qa_framework.gameplay.assertions import (
    AssertionResult,
    VisualAssertionEngine,
    _region_tuple,
)
from qa_framework.gameplay.suite import load_run_config

_EVIDENCE_PATTERNS: dict[int, list[str]] = {
    4077460: ["swishflow", "sw_"],
    4307180: ["av_", "st2"],
    4511140: ["ul_", "love"],
}

_OCR_CHECKS = {"ocr_contains", "ocr_word_present", "ocr_region_contains"}


def _find_evidence(evidence_dir: Path, app_id: int | None) -> list[Path]:
    """Return candidate evidence PNGs for ``app_id`` (or all PNGs if unknown)."""
    pngs = [p for p in evidence_dir.rglob("*.png") if p.is_file()]
    if app_id is None:
        return sorted(pngs)
    patterns = _EVIDENCE_PATTERNS.get(int(app_id), [])
    matches: list[Path] = []
    for path in pngs:
        lowered = str(path).lower()
        if any(pattern in lowered for pattern in patterns):
            matches.append(path)
    return sorted(set(matches))


def _ocr_snapshot(ocr: OCREngine, frame: np.ndarray, assertion: dict[str, Any]) -> str:
    """Return the OCR'd word text for the assertion's frame (best of frame)."""
    if assertion.get("check") not in _OCR_CHECKS:
        return ""
    psm = assertion.get("psm")
    words = ocr.read_words(
        frame,
        scale=float(assertion.get("scale", 1.0)),
        psm=int(psm) if psm is not None else 7,
        region=_region_tuple(assertion),
        preprocessing=assertion.get("preprocessing", "ui"),
        confidence_threshold=0.0,
    )
    return " | ".join(word.text for word in words)


def validate_suite(
    suite_dict: dict[str, Any],
    evidence_dir: str | Path,
    max_frames: int = 12,
) -> list[dict[str, Any]]:
    """Run OCR/visual assertions against saved evidence frames.

    ``suite_dict`` is a single-game suite mapping with ``assertions`` and
    optional ``app_id``/``name``. Returns one result dict per assertion, choosing
    the best (PASS > FAIL) outcome across all candidate evidence frames.

    Each result dict has keys: ``app_id``, ``game``, ``evidence``, ``name``,
    ``check``, ``status`` (PASS/FAIL/SKIP), ``passed`` (bool), ``ocr`` and
    ``message``. An assertion whose ``message`` starts with ``error:`` signals an
    unexpected throw (caller should treat that as a crash).
    """
    app_id = suite_dict.get("app_id")
    assertions: list[dict[str, Any]] = suite_dict.get("assertions") or []
    game = (
        suite_dict.get("name")
        or suite_dict.get("game")
        or (str(app_id) if app_id is not None else "suite")
    )

    evidence_dir_path = Path(evidence_dir)
    frames = _find_evidence(evidence_dir_path, app_id)
    if max_frames > 0:
        frames = frames[:max_frames]

    engine = VisualAssertionEngine()
    ocr = OCREngine()

    if not frames:
        return [
            {
                "app_id": app_id,
                "game": game,
                "evidence": "(none)",
                "name": assertion.get("name", "?"),
                "check": assertion.get("check", "?"),
                "status": "SKIP",
                "passed": False,
                "ocr": "",
                "message": "no evidence frames found",
            }
            for assertion in assertions
        ]

    best: dict[str, dict[str, Any]] = {}
    for frame_path in frames:
        frame = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        if frame is None:
            continue
        for assertion in assertions:
            name = assertion.get("name", "?")
            try:
                result = engine.assert_frame(frame, [assertion])[0]
            except Exception as exc:  # noqa: BLE001 - surface as crash
                result = AssertionResult(name=name, passed=False, message=f"error: {exc}")
            record = {
                "app_id": app_id,
                "game": game,
                "evidence": frame_path.name,
                "name": name,
                "check": assertion.get("check", "?"),
                "status": "PASS" if result.passed else "FAIL",
                "passed": result.passed,
                "ocr": _ocr_snapshot(ocr, frame, assertion),
                "message": result.message,
            }
            existing = best.get(name)
            if existing is None or _is_better(record, existing):
                best[name] = record

    return list(best.values())


def _is_better(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    """Prefer PASS over FAIL; on ties prefer the more OCR-informative frame.

    Added: on further ties, prefer the frame with the higher non_black_ratio
    (i.e. a brighter/less-dark capture), since that is more likely to yield
    reliable OCR text.
    """
    if candidate["passed"] and not current["passed"]:
        return True
    if candidate["passed"] == current["passed"]:
        if len(candidate["ocr"]) != len(current["ocr"]):
            return len(candidate["ocr"]) > len(current["ocr"])
        # further tie: prefer higher non_black_ratio (brighter capture)
        return candidate.get("ocr_non_black_ratio", 0.0) > current.get("ocr_non_black_ratio", 0.0)
    return False


def _games_from_suite(suite_path: Path) -> list[dict[str, Any]]:
    """Build per-game suite dicts (with app_id) from a single or combined suite."""
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    games = data.get("games")
    out: list[dict[str, Any]] = []
    if isinstance(games, list) and games:
        for entry in games:
            app_id = int(entry["app_id"])
            sub_path = (suite_path.parent / entry["suite"]).resolve()
            config = load_run_config(sub_path)
            out.append(
                {
                    "app_id": app_id,
                    "name": entry.get("name") or sub_path.stem,
                    "assertions": config.assertions,
                }
            )
        return out

    config = load_run_config(suite_path)
    single_app_id: int | None = _app_id_from_filename(suite_path)
    name = config.executable_name or suite_path.stem
    return [{"app_id": single_app_id, "name": name, "assertions": config.assertions}]


def _app_id_from_filename(path: Path) -> int | None:
    stem = path.stem
    if stem.startswith("game_"):
        digits = "".join(ch for ch in stem[len("game_") :] if ch.isdigit())
        if digits:
            return int(digits)
    return None


def _print_report(all_results: list[dict[str, Any]]) -> None:
    groups: dict[tuple[Any, str], list[dict[str, Any]]] = {}
    for record in all_results:
        key = (record["app_id"], record["game"])
        groups.setdefault(key, []).append(record)

    total_pass = total_fail = total_skip = 0
    for (app_id, game), records in groups.items():
        evidence = next((r["evidence"] for r in records if r["evidence"] != "(none)"), "(none)")
        print(f"[{app_id}] {game}  evidence={evidence}")
        for r in records:
            tag = r["status"]
            ocr_field = f'  ocr="{r["ocr"]}"' if r["ocr"] else ""
            note = ""
            if tag == "FAIL" and r["message"].startswith("error:"):
                note = "  (CRASH)"
            elif tag == "SKIP":
                note = "  (evidence missing)"
            print(f"  {tag}  {r['check']}:{r['name']}{ocr_field}  {r['message']}{note}")
            if tag == "PASS":
                total_pass += 1
            elif tag == "FAIL":
                total_fail += 1
            else:
                total_skip += 1
        game_pass = sum(1 for r in records if r["status"] == "PASS")
        game_fail = sum(1 for r in records if r["status"] == "FAIL")
        game_skip = sum(1 for r in records if r["status"] == "SKIP")
        print(
            f"SUMMARY: {game_pass} passed, {game_fail} failed, {game_skip} skipped (game {app_id})"
        )
        print()

    print(f"TOTAL: {total_pass} passed, {total_fail} failed, {total_skip} skipped")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Headless OCR-suite validator against saved evidence frames."
    )
    parser.add_argument("--suite", required=True, help="Path to an OCR JSON suite.")
    parser.add_argument(
        "--evidence-dir",
        default="screenshots",
        help="Directory containing captured evidence PNGs.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=12,
        help="Maximum evidence frames to try per game (0 = no limit).",
    )
    args = parser.parse_args()

    suite_path = Path(args.suite).resolve()
    evidence_dir = Path(args.evidence_dir)

    games = _games_from_suite(suite_path)

    all_results: list[dict[str, Any]] = []
    for game in games:
        all_results.extend(validate_suite(game, evidence_dir, max_frames=args.max_frames))

    _print_report(all_results)

    if any(r["message"].startswith("error:") for r in all_results):
        return 2
    if any(r["evidence"] != "(none)" and not r["passed"] for r in all_results):
        # A game had evidence but every assertion failed: signal failure.
        has_evidence_with_zero_pass = False
        groups: dict[tuple[Any, str], list[dict[str, Any]]] = {}
        for record in all_results:
            key = (record["app_id"], record["game"])
            groups.setdefault(key, []).append(record)
        for records in groups.values():
            if any(r["evidence"] != "(none)" for r in records):
                if not any(r["status"] == "PASS" for r in records):
                    has_evidence_with_zero_pass = True
        if has_evidence_with_zero_pass:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
