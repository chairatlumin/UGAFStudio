from qa_framework.perception_drift import PerceptionDriftDetector


def test_no_drift_on_identical_frames():
    detector = PerceptionDriftDetector(threshold=0.85)
    frame = "a" * 1000
    detector.set_reference("menu", frame)
    result = detector.check_drift("menu", frame)
    assert result["drifted"] is False
    assert result["similarity"] > 0.99

def test_drift_on_different_frames():
    detector = PerceptionDriftDetector(threshold=0.85)
    frame_a = "a" * 1000
    frame_b = "b" * 1000
    detector.set_reference("menu", frame_a)
    result = detector.check_drift("menu", frame_b)
    assert result["drifted"] is True
    assert result["similarity"] < 0.5

def test_unknown_scene_returns_none():
    detector = PerceptionDriftDetector()
    result = detector.check_drift("nonexistent", "data")
    assert result["drifted"] is None

def test_multiple_scenes_tracked_independently():
    detector = PerceptionDriftDetector(threshold=0.85)
    detector.set_reference("scene1", "a" * 100)
    detector.set_reference("scene2", "b" * 100)
    r1 = detector.check_drift("scene1", "a" * 100)
    r2 = detector.check_drift("scene2", "c" * 100)
    assert r1["drifted"] is False
    assert r2["drifted"] is True

def test_report_shows_all_scenes():
    detector = PerceptionDriftDetector()
    detector.set_reference("s1", "a" * 100)
    detector.set_reference("s2", "b" * 100)
    report = detector.report()
    assert len(report["scenes"]) == 2
