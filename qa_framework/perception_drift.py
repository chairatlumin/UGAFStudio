from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def _perceptual_hash(data: str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()[:32]


def _similarity(hash_a: str, hash_b: str) -> float:
    if len(hash_a) != len(hash_b):
        return 0.0
    matches = sum(1 for a, b in zip(hash_a, hash_b) if a == b)
    return matches / len(hash_a)


@dataclass
class PerceptionDriftDetector:
    threshold: float = 0.85
    _references: dict[str, str] = field(default_factory=dict)
    _drift_counts: dict[str, int] = field(default_factory=dict)

    def set_reference(self, scene: str, frame_data: str) -> None:
        self._references[scene] = _perceptual_hash(frame_data)

    def check_drift(self, scene: str, frame_data: str) -> dict:
        if scene not in self._references:
            return {"drifted": None, "similarity": None, "scene": scene}
        ref_hash = self._references[scene]
        cur_hash = _perceptual_hash(frame_data)
        sim = _similarity(ref_hash, cur_hash)
        drifted = sim < self.threshold
        if drifted:
            self._drift_counts[scene] = self._drift_counts.get(scene, 0) + 1
        return {"drifted": drifted, "similarity": round(sim, 4), "scene": scene}

    def report(self) -> dict:
        scenes = []
        for scene, ref_hash in self._references.items():
            scenes.append({
                "scene": scene,
                "drift_count": self._drift_counts.get(scene, 0),
            })
        return {
            "scenes": scenes,
            "total_scenes": len(scenes),
            "threshold": self.threshold,
        }
