from __future__ import annotations

import numpy as np

from app.vision.color_detector import ColorDetector
from app.vision.detector import ObjectDetector
from app.vision.template_match import TemplateMatcher


def test_object_detector_wires_services() -> None:
    template = np.zeros((20, 20, 3), dtype=np.uint8)
    template[::2] = 200
    template[:, 1::2] = 200

    source = np.zeros((60, 80, 3), dtype=np.uint8)
    source[15:35, 20:40] = template

    detector = ObjectDetector()

    match = detector.find_template(source, template, threshold=0.9)

    assert match is not None
    assert match.box == (20, 15, 20, 20)

    color = detector.find_color(source, target=(200, 200, 200))

    assert color is not None
    assert color.width == 20


def test_object_detector_accepts_injected_services() -> None:
    detector = ObjectDetector(
        matcher=TemplateMatcher(),
        color_detector=ColorDetector(),
    )

    assert detector.matcher is not None
    assert detector.color_detector is not None
