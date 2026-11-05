from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TraceEvent:
    timestamp: float
    action: Optional[str]  # None for initial frame
    frame_hash: str  # hex-encoded 256-bit perceptual hash
    state_signature: str  # OCR-detected state label (e.g., "menu", "combat", "cutscene")


@dataclass
class Playbook:
    game_id: int  # Steam AppID
    goal: str  # e.g., "complete_tutorial", "defeat_first_boss"
    events: List[TraceEvent] = field(default_factory=list)
    success_count: int = 0
    fail_count: int = 0
    last_run: float = 0.0
    version: str = "1.0"  # playbook schema version
    game_build: str = ""  # game build identifier (for invalidation)
