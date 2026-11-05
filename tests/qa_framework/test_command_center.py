from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_framework.command_center import ActionCard, ActionCardStore, CardStatus


def _card() -> ActionCard:
    return ActionCard.proposed(
        title="Review preflight",
        persona="QA Intake",
        category="preflight",
        summary="The vision endpoint is unavailable.",
        recommendation="Start the local VLM, then run preflight again.",
    )


def test_store_persists_human_approval(tmp_path: Path) -> None:
    store = ActionCardStore(tmp_path / "cards.json")
    card = store.add(_card())

    decided = store.decide(card.card_id, CardStatus.APPROVED, "QA reviewer", "Reviewed")

    reloaded = ActionCardStore(store.path).list_cards()
    assert decided.status is CardStatus.APPROVED
    assert reloaded[0].decision_by == "QA reviewer"
    assert reloaded[0].decision_note == "Reviewed"


def test_store_requires_named_reviewer_and_one_decision(tmp_path: Path) -> None:
    store = ActionCardStore(tmp_path / "cards.json")
    card = store.add(_card())

    with pytest.raises(ValueError, match="named reviewer"):
        store.decide(card.card_id, CardStatus.APPROVED, " ")
    store.decide(card.card_id, CardStatus.DISMISSED, "QA reviewer")
    with pytest.raises(ValueError, match="already been decided"):
        store.decide(card.card_id, CardStatus.APPROVED, "QA reviewer")


def test_preflight_blockers_become_review_cards_not_game_actions(tmp_path: Path) -> None:
    manifest = tmp_path / "run_manifest.json"
    manifest.write_text(
        json.dumps({"run_id": "test-run", "blockers": ["vlm_ready", "user_cleared_eula"]}),
        encoding="utf-8",
    )
    store = ActionCardStore(tmp_path / "cards.json")

    cards = store.ingest_preflight(manifest)

    assert len(cards) == 2
    assert all(card.status is CardStatus.PROPOSED for card in cards)
    assert all(
        "must not accept it" in card.recommendation
        for card in cards
        if "EULA" in card.recommendation
    )
