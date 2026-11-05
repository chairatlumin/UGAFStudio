from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.vision.template_match import MatchResult

DEFAULT_TESSERACT_CMD = (
    shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


@dataclass(frozen=True)
class OCRWord:
    """A word detected by the OCR engine."""

    text: str
    box: MatchResult
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return self.box.center


class OCREngine:
    """Optical character recognition backed by pytesseract.

    The engine degrades gracefully when the Tesseract binary is unavailable.
    """

    def __init__(self, tesseract_cmd: str | None = DEFAULT_TESSERACT_CMD) -> None:
        self._tesseract_cmd = tesseract_cmd
        self._pytesseract: Any = None

    def available(self) -> bool:
        """Return whether Tesseract is installed and importable."""
        if self._pytesseract is None:
            try:
                import pytesseract

                if self._tesseract_cmd:
                    pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd

                self._pytesseract = pytesseract
            except ImportError:
                return False

        command = self._tesseract_cmd or "tesseract"
        return Path(command).is_file() if ("\\" in command or "/" in command) else bool(shutil.which(command))

    def read(
        self,
        frame: np.ndarray,
        *,
        scale: float = 1.0,
        psm: int | None = None,
        lang: str = "eng",
        config: str = "",
        region: tuple[int, int, int, int] | None = None,
        preprocessing: str = "raw",
    ) -> str:
        """Return the raw text recognized in a BGR or BGRA frame."""
        if not self.available():
            return ""
        prepared = _prepare_frame(frame, scale, region, preprocessing)
        image = _to_rgb(prepared)
        tesseract_config = _tesseract_config(config, psm)
        if lang == "eng" and not tesseract_config:
            text = self._pytesseract.image_to_string(image)
        else:
            text = self._pytesseract.image_to_string(
                image, lang=lang, config=tesseract_config
            )
        return str(text)

    def read_words(
        self,
        frame: np.ndarray,
        *,
        scale: float = 1.0,
        lang: str = "eng",
        config: str = "",
        psm: int | None = None,
        region: tuple[int, int, int, int] | None = None,
        preprocessing: str = "raw",
        confidence_threshold: float = 0.0,
    ) -> list[OCRWord]:
        """Return recognized words with their locations and confidence."""
        if not self.available():
            return []
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")
        prepared = _prepare_frame(frame, scale, region, preprocessing)
        image = _to_rgb(prepared)
        tesseract_config = _tesseract_config(config, psm)
        if lang == "eng" and not tesseract_config:
            data = self._pytesseract.image_to_data(image, output_type="dict")
        else:
            data = self._pytesseract.image_to_data(
                image, output_type="dict", lang=lang, config=tesseract_config
            )

        words: list[OCRWord] = []

        for index, text in enumerate(data["text"]):
            word = str(text).strip()

            if not word:
                continue

            confidence = float(data["conf"][index])

            if confidence < 0 or confidence / 100.0 < confidence_threshold:
                continue

            x = int(round(int(data["left"][index]) / scale))
            y = int(round(int(data["top"][index]) / scale))
            width = int(round(int(data["width"][index]) / scale))
            height = int(round(int(data["height"][index]) / scale))
            if region is not None:
                x += region[0]
                y += region[1]

            box = MatchResult(
                x=x,
                y=y,
                width=width,
                height=height,
                confidence=confidence / 100.0,
            )

            words.append(OCRWord(text=word, box=box, confidence=confidence / 100.0))

        return words


def _to_rgb(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame

    if frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)

    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def crop_region(
    frame: np.ndarray, region: tuple[int, int, int, int] | list[int]
) -> np.ndarray:
    """Crop a validated (x, y, width, height) region without padding."""
    if len(region) != 4:
        raise ValueError("region must contain x, y, width, height")
    x, y, width, height = (int(value) for value in region)
    if frame.ndim not in {2, 3} or frame.size == 0:
        raise ValueError("frame must be a non-empty image")
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("region must have nonnegative origin and positive size")
    if x + width > frame.shape[1] or y + height > frame.shape[0]:
        raise ValueError("region extends beyond frame bounds")
    return frame[y : y + height, x : x + width]


def _prepare_frame(
    frame: np.ndarray,
    scale: float,
    region: tuple[int, int, int, int] | None,
    preprocessing: str,
) -> np.ndarray:
    if frame.ndim not in {2, 3} or frame.size == 0:
        raise ValueError("OCR requires a non-empty image frame")
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("OCR scale must be a finite positive number")
    image = crop_region(frame, region) if region is not None else frame
    key = (preprocessing or "raw").casefold()
    if key == "raw":
        prepared = image
    elif key in {"gray", "grey", "ui", "binary"}:
        gray = image if image.ndim == 2 else cv2.cvtColor(
            image, cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY
        )
        if key == "binary":
            prepared = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        elif key == "ui":
            prepared = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        else:
            prepared = gray
    else:
        raise ValueError(f"Unsupported OCR preprocessing mode: {preprocessing!r}")
    if scale != 1.0:
        width = max(1, int(round(prepared.shape[1] * scale)))
        height = max(1, int(round(prepared.shape[0] * scale)))
        prepared = cv2.resize(prepared, (width, height), interpolation=cv2.INTER_CUBIC)
    return prepared


def _tesseract_config(config: str, psm: int | None) -> str:
    pieces = [config.strip()] if config.strip() else []
    if psm is not None:
        if isinstance(psm, bool) or not 0 <= int(psm) <= 13:
            raise ValueError("psm must be an integer between 0 and 13")
        pieces.append(f"--psm {int(psm)}")
    return " ".join(pieces)
