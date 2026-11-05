"""Tests for PerceptionDriftDetector."""
from __future__ import annotations

from qa_framework.perception_drift import PerceptionDriftDetector, _perceptual_hash, _similarity


def test_similarity_identical() -> None:
    h = _perceptual_hash("same data")
    assert _similarity(h, h) == 1.0


def test_similarity_different() -> None:
    h1 = _perceptual_hash("data one")
    h2 = _perceptual_hash("data two")
    sim = _similarity(h1, h2)
    assert 0.0 <= sim <= 1.0
    assert sim < 1.0


def test_drift_detection_similar_frame() -> None:
    detector = PerceptionDriftDetector(threshold=0.85)
    detector.set_reference("menu", "frame_data_1")
    result = detector.check_drift("menu", "frame_data_1")
    assert result["drifted"] is False
    assert result["similarity"] is not None


def test_drift_detection_different_frame() -> None:
    detector = PerceptionDriftDetector(threshold=0.85)
    detector.set_reference("menu", "frame_data_1")
    result = detector.check_drift("menu", "frame_data_2")
    assert result["drifted"] is True
    assert result["similarity"] is not None


def test_unknown_scene_returns_none() -> None:
    detector = PerceptionDriftDetector(threshold=0.85)
    result = detector.check_drift("unknown_scene", "frame_data")
    assert result["drifted"] is None
    assert result["similarity"] is None
    assert result["scene"] == "unknown_scene"


def test_multi_scene_report() -> None:
    detector = PerceptionDriftDetector(threshold=0.85)
    detector.set_reference("scene_a", "frame_a")
    detector.set_reference("scene_b", "frame_b")
    # No drift yet
    report = detector.report()
    assert report["total_scenes"] == 2
    assert len(report["scenes"]) == 2
