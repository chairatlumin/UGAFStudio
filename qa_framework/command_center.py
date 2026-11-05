from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4


class CardStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    DISMISSED = "DISMISSED"


@dataclass
class ActionCard:
    card_id: str
    title: str
    persona: str
    category: str
    summary: str
    recommendation: str
    source_refs: list[str] = field(default_factory=list)
    risk: str = "low"
    status: CardStatus = CardStatus.PROPOSED
    created_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    decision_by: str | None = None
    decision_note: str = ""

    @classmethod
    def proposed(
        cls,
        title: str,
        persona: str,
        category: str,
        summary: str,
        recommendation: str,
        source_refs: list[str] | None = None,
        risk: str = "low",
    ) -> ActionCard:
        return cls(
            card_id=uuid4().hex,
            title=title,
            persona=persona,
            category=category,
            summary=summary,
            recommendation=recommendation,
            source_refs=source_refs or [],
            risk=risk,
        )


class ActionCardStore:
    """Atomic, local-only persistence for proposed QA actions and human decisions."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def list_cards(self) -> list[ActionCard]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read QA action-card store {self.path}: {exc}") from exc
        if not isinstance(payload, list):
            raise ValueError(f"QA action-card store must contain a JSON list: {self.path}")
        return [
            ActionCard(**{**item, "status": CardStatus(item.get("status", "PROPOSED"))})
            for item in payload
            if isinstance(item, dict)
        ]

    def add(self, card: ActionCard) -> ActionCard:
        cards = self.list_cards()
        if any(existing.card_id == card.card_id for existing in cards):
            raise ValueError(f"Duplicate action-card id: {card.card_id}")
        cards.insert(0, card)
        self._write(cards)
        return card

    def decide(self, card_id: str, status: CardStatus, actor: str, note: str = "") -> ActionCard:
        if status not in (CardStatus.APPROVED, CardStatus.DISMISSED):
            raise ValueError("A human decision must be APPROVED or DISMISSED.")
        if not actor.strip():
            raise ValueError("A named reviewer is required for a card decision.")
        cards = self.list_cards()
        for card in cards:
            if card.card_id == card_id:
                if card.status is not CardStatus.PROPOSED:
                    raise ValueError(f"Card {card_id} has already been decided.")
                card.status = status
                card.decision_by = actor.strip()
                card.decision_note = note.strip()
                self._write(cards)
                return card
        raise KeyError(f"Unknown action-card id: {card_id}")

    def ingest_preflight(self, manifest_path: Path) -> list[ActionCard]:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run_id = str(manifest.get("run_id", manifest_path.parent.name))
        blockers = manifest.get("blockers", [])
        created: list[ActionCard] = []
        if blockers:
            for blocker in blockers:
                card = ActionCard.proposed(
                    title=f"Resolve QA preflight blocker: {blocker}",
                    persona="QA Intake & Build Control",
                    category="preflight_blocker",
                    summary=f"Run {run_id} stopped before gameplay. Blocker: {blocker}.",
                    recommendation=_recommendation(str(blocker)),
                    source_refs=[str(manifest_path), f"run_id:{run_id}"],
                    risk="high",
                )
                self.add(card)
                created.append(card)
        else:
            card = ActionCard.proposed(
                title=f"Preflight ready for supervised review ({run_id})",
                persona="QA Intake & Build Control",
                category="preflight_ready",
                summary="Harness prerequisites passed. This is not a gameplay result or test pass.",
                recommendation=(
                    "Review target build, testcase scope, and human gates. Start gameplay only "
                    "from the explicit supervised-run control."
                ),
                source_refs=[str(manifest_path)],
                risk="medium",
            )
            self.add(card)
            created.append(card)
        return created

    def _write(self, cards: list[ActionCard]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [{**asdict(card), "status": card.status.value} for card in cards]
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp"
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        temporary_path.replace(self.path)


def _recommendation(blocker: str) -> str:
    if blocker == "vlm_ready":
        return (
            "Configure and verify the approved local VLM endpoint/model, then run preflight again."
        )
    if blocker == "user_cleared_eula":
        return (
            "The user must handle the in-game EULA directly and confirm it; "
            "automation must not accept it."
        )
    if blocker == "demo_window_present":
        return "Open the exact Demo build and verify its window title before rerunning preflight."
    if blocker == "executable_present":
        return "Verify the Demo installation path and profile; do not substitute the full game."
    return f"Review the failed preflight check '{blocker}' and resolve it before gameplay."
