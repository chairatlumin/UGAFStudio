from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.vision.color_detector import ColorDetector
from app.vision.ocr import OCREngine
from app.vision.template_match import TemplateMatcher


@dataclass(frozen=True)
class AssertionResult:
    """Outcome of a single configured visual assertion."""

    name: str
    passed: bool
    message: str


class VisualAssertionEngine:
    """Runs declarative visual assertions against a captured frame."""

    def __init__(
        self,
        template_matcher: TemplateMatcher | None = None,
        color_detector: ColorDetector | None = None,
        ocr_engine: OCREngine | None = None,
    ) -> None:
        self._template = template_matcher or TemplateMatcher()
        self._color = color_detector or ColorDetector()
        self._ocr = ocr_engine or OCREngine()

    def assert_frame(
        self,
        frame: np.ndarray,
        assertions: list[dict[str, Any]],
    ) -> list[AssertionResult]:
        """Evaluate every assertion config against ``frame``.

        Each config is a dict with at least ``name`` and ``check``. Supported
        checks:

        * ``template_match`` — requires ``template`` (path) and optional
          ``threshold`` (default 0.9).
        * ``frame_not_black`` — requires a minimum fraction of pixels to be
          brighter than ``brightness_threshold``.
        * ``color_detected`` — requires ``color`` (``[b, g, r]``) and optional
          ``tolerance`` (default 30).
        * ``color_region_detected`` — like ``color_detected`` but constrained to
          ``region`` (``[x, y, w, h]``).
        * ``ocr_contains`` — requires ``text``; asserts the OCR'd frame contains
          the substring (case-insensitive). Optional ``region``, ``scale``,
          ``psm``, ``preprocessing``.
        * ``ocr_word_present`` — requires ``text``; passes only when that word is
          recognized exactly (case-insensitive) at or above ``confidence_threshold``
          (default 0.6). Optional ``region``, ``scale``, ``psm``, ``preprocessing``.
        * ``ocr_region_contains`` — requires ``text`` and ``region``; asserts the
          OCR'd region contains the substring.
        """
        results: list[AssertionResult] = []
        for index, raw in enumerate(assertions):
            if not isinstance(raw, dict):
                raise ValueError(f"Assertion at index {index} must be an object.")
            name = raw.get("name", f"assertion {index + 1}")
            check = raw.get("check")
            try:
                results.append(self._run_one(name, check, raw, frame))
            except Exception as exc:  # noqa: BLE001 - surface as a failed assertion
                results.append(AssertionResult(name=name, passed=False, message=f"error: {exc}"))
        return results

    def _run_one(
        self,
        name: str,
        check: Any,
        config: dict[str, Any],
        frame: np.ndarray,
    ) -> AssertionResult:
        if check == "template_match":
            return self._template_match(name, config, frame)
        if check == "frame_not_black":
            return self._frame_not_black(name, config, frame)
        if check == "color_detected":
            return self._color_detected(name, config, frame)
        if check == "color_region_detected":
            return self._color_region_detected(name, config, frame)
        if check == "ocr_contains":
            return self._ocr_contains(name, config, frame)
        if check == "ocr_word_present":
            return self._ocr_word_present(name, config, frame)
        if check == "ocr_region_contains":
            return self._ocr_region_contains(name, config, frame)
        raise ValueError(f"Unsupported visual assertion: {check!r}")

    def _frame_not_black(
        self,
        name: str,
        config: dict[str, Any],
        frame: np.ndarray,
    ) -> AssertionResult:
        if frame.size == 0 or frame.ndim not in {2, 3}:
            raise ValueError("frame_not_black requires a non-empty image frame.")
        brightness_threshold = int(config.get("brightness_threshold", 8))
        minimum_ratio = float(config.get("min_visible_ratio", 0.02))
        if not 0 <= brightness_threshold <= 255:
            raise ValueError("brightness_threshold must be between 0 and 255.")
        if not 0.0 <= minimum_ratio <= 1.0:
            raise ValueError("min_visible_ratio must be between 0 and 1.")
        visible = (
            np.any(frame > brightness_threshold, axis=2)
            if frame.ndim == 3
            else frame > brightness_threshold
        )
        ratio = float(np.count_nonzero(visible) / visible.size)
        passed = ratio >= minimum_ratio
        message = (
            f"Visible pixel ratio {ratio:.3f} meets minimum {minimum_ratio:.3f}."
            if passed
            else (
                f"Near-black frame: visible pixel ratio {ratio:.3f} is below {minimum_ratio:.3f}."
            )
        )
        return AssertionResult(
            name=name,
            passed=passed,
            message=message,
        )

    def _template_match(
        self,
        name: str,
        config: dict[str, Any],
        frame: np.ndarray,
    ) -> AssertionResult:
        template_path = config.get("template")
        if not isinstance(template_path, str) or not template_path.strip():
            raise ValueError("template_match requires a 'template' path.")
        template = _load_image(template_path)
        threshold = float(config.get("threshold", 0.9))
        match = self._template.match(frame, template, threshold=threshold)
        if match is None:
            return AssertionResult(
                name=name,
                passed=False,
                message=f"No template match above {threshold:.2f}: {template_path}",
            )
        return AssertionResult(
            name=name,
            passed=True,
            message=f"Matched at ({match.x}, {match.y}) conf {match.confidence:.2f}",
        )

    def _color_detected(
        self,
        name: str,
        config: dict[str, Any],
        frame: np.ndarray,
    ) -> AssertionResult:
        raw_color = config.get("color")
        if not _is_bgr_tuple(raw_color):
            raise ValueError("color_detected requires 'color' as [b, g, r].")
        color = tuple(raw_color)  # type: ignore[arg-type]
        tolerance = int(config.get("tolerance", 30))
        detected = self._color.detect(frame, color, tolerance=tolerance)
        if detected is None:
            return AssertionResult(
                name=name,
                passed=False,
                message=f"No color {color} within tolerance {tolerance}.",
            )
        return AssertionResult(
            name=name,
            passed=True,
            message=(
                f"Color region {detected.width}x{detected.height} at ({detected.x}, {detected.y})"
            ),
        )

    def _color_region_detected(
        self,
        name: str,
        config: dict[str, Any],
        frame: np.ndarray,
    ) -> AssertionResult:
        raw_color = config.get("color")
        if not _is_bgr_tuple(raw_color):
            raise ValueError("color_region_detected requires 'color' as [b, g, r].")
        color = tuple(raw_color)  # type: ignore[arg-type]
        tolerance = int(config.get("tolerance", 30))
        region = _region_tuple(config)
        if region is None:
            raise ValueError("color_region_detected requires 'region' as [x, y, w, h].")
        from app.vision.ocr import crop_region

        region_frame = crop_region(frame, region)
        detected = self._color.detect(region_frame, color, tolerance=tolerance)
        if detected is None:
            return AssertionResult(
                name=name,
                passed=False,
                message=f"No color {color} within tolerance {tolerance} in region {region}.",
            )
        return AssertionResult(
            name=name,
            passed=True,
            message=(
                f"Color region {detected.width}x{detected.height} at "
                f"({detected.x}, {detected.y}) within {region}"
            ),
        )

    def _ocr_contains(
        self,
        name: str,
        config: dict[str, Any],
        frame: np.ndarray,
    ) -> AssertionResult:
        expected = config.get("text")
        if not isinstance(expected, str) or not expected.strip():
            raise ValueError("ocr_contains requires 'text'.")
        if not self._ocr.available():
            return AssertionResult(
                name=name,
                passed=False,
                message="OCR unavailable (Tesseract not installed).",
            )
        text = self._ocr.read(
            frame,
            scale=float(config.get("scale", 1.0)),
            psm=config.get("psm"),
            region=_region_tuple(config),
            preprocessing=config.get("preprocessing", "raw"),
        )
        if expected.lower() not in text.lower():
            return AssertionResult(
                name=name,
                passed=False,
                message=f"OCR text did not contain {expected!r}: {text!r}",
            )
        return AssertionResult(name=name, passed=True, message=f"OCR contained {expected!r}")

    def _ocr_word_present(
        self,
        name: str,
        config: dict[str, Any],
        frame: np.ndarray,
    ) -> AssertionResult:
        expected = config.get("text")
        if not isinstance(expected, str) or not expected.strip():
            raise ValueError("ocr_word_present requires 'text'.")
        if not self._ocr.available():
            return AssertionResult(
                name=name,
                passed=False,
                message="OCR unavailable (Tesseract not installed).",
            )
        threshold = float(config.get("confidence_threshold", 0.6))
        region = _region_tuple(config)
        words = self._ocr.read_words(
            frame,
            scale=float(config.get("scale", 1.0)),
            psm=int(config.get("psm", 7)) if config.get("psm") is not None else 7,
            region=region,
            preprocessing=config.get("preprocessing", "ui"),
            confidence_threshold=threshold,
        )
        for w in words:
            if w.text.lower() == expected.lower():
                return AssertionResult(
                    name=name,
                    passed=True,
                    message=f"'{w.text}' at {w.center} conf {w.confidence:.2f}",
                )
        found = ", ".join(repr(w.text) for w in words[:8]) or "(none)"
        return AssertionResult(
            name=name,
            passed=False,
            message=f"Word {expected!r} not present (conf>={threshold}). Saw: {found}",
        )

    def _ocr_region_contains(
        self,
        name: str,
        config: dict[str, Any],
        frame: np.ndarray,
    ) -> AssertionResult:
        expected = config.get("text")
        if not isinstance(expected, str) or not expected.strip():
            raise ValueError("ocr_region_contains requires 'text'.")
        region = _region_tuple(config)
        if region is None:
            raise ValueError("ocr_region_contains requires 'region' as [x, y, w, h].")
        if not self._ocr.available():
            return AssertionResult(
                name=name,
                passed=False,
                message="OCR unavailable (Tesseract not installed).",
            )
        words = self._ocr.read_words(
            frame,
            scale=float(config.get("scale", 1.0)),
            psm=int(config.get("psm", 7)) if config.get("psm") is not None else 7,
            region=region,
            preprocessing=config.get("preprocessing", "ui"),
        )
        seen = " ".join(w.text for w in words)
        if expected.lower() in seen.lower():
            return AssertionResult(
                name=name,
                passed=True,
                message=f"Region OCR contained {expected!r}: {seen[:80]!r}",
            )
        return AssertionResult(
            name=name,
            passed=False,
            message=f"Region OCR did not contain {expected!r}: {seen[:80]!r}",
        )


def _region_tuple(config: dict[str, Any]) -> tuple[int, int, int, int] | None:
    region = config.get("region")
    if not _is_region(region):
        return None
    r = tuple(int(v) for v in region)  # type: ignore[union-attr]
    return (r[0], r[1], r[2], r[3])


def _is_bgr_tuple(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(isinstance(channel, int) for channel in value)
    )


def _is_region(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(isinstance(coord, int) for coord in value)
    )


def _load_image(path: str) -> np.ndarray:
    image = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Template image not found: {path}")
    return image
