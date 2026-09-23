from qa_framework.anomaly_injector import AnomalyInjector, AnomalyType
from qa_framework.vision_game_runner import PerceptionState


def test_no_injection_when_disabled():
    injector = AnomalyInjector(enabled=False)
    base = PerceptionState(scene_classification="gameplay", confidence=0.9)
    result = injector.wrap(lambda: base)
    assert result.scene_classification == "gameplay"


def test_popup_inject():
    injector = AnomalyInjector(enabled=True, injection_rate=1.0, seed=42)
    injector.register_anomaly(
        AnomalyType.POPUP, lambda: PerceptionState(scene_classification="popup")
    )
    base = PerceptionState(scene_classification="gameplay")
    results = [injector.wrap(lambda: base).scene_classification for _ in range(10)]
    assert "popup" in results


def test_lag_injection():
    injector = AnomalyInjector(enabled=True, injection_rate=1.0)
    injector.register_anomaly(AnomalyType.INPUT_LAG, lambda: PerceptionState(confidence=0.1))
    base = PerceptionState(confidence=0.9)
    result = injector.wrap(lambda: base)
    assert result.confidence < 0.5
