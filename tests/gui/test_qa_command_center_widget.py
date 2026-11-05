from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton  # noqa: E402

from app.gui.widgets.qa_command_center_widget import QACommandCenterWidget  # noqa: E402
from qa_framework.command_center import ActionCard, ActionCardStore, CardStatus  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return cast(QApplication, QApplication.instance() or QApplication([]))


@pytest.fixture
def make_widget(app: QApplication, tmp_path: Path):
    widgets: list[QACommandCenterWidget] = []

    def create(store: ActionCardStore | None = None) -> QACommandCenterWidget:
        widget = QACommandCenterWidget(
            store or ActionCardStore(tmp_path / f"cards-{len(widgets)}.json")
        )
        widgets.append(widget)
        return widget

    yield create

    for widget in widgets:
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_gameplay_stays_disabled_until_preflight_and_human_eula_gate(
    make_widget,
) -> None:
    widget = make_widget()
    execute = widget.findChild(QPushButton, "runSupervisedSmoke")
    eula = widget.findChild(QCheckBox, "eulaCleared")

    assert execute is not None and eula is not None
    assert not execute.isEnabled()
    eula.setChecked(True)
    assert not execute.isEnabled()


def test_preflight_passes_only_the_user_confirmed_eula_ack(make_widget) -> None:
    widget = make_widget()
    eula = widget.findChild(QCheckBox, "eulaCleared")
    assert eula is not None
    started: list[tuple[str, list[str]]] = []
    widget._start_process = lambda operation, args: started.append((operation, args))

    eula.setChecked(True)
    widget.run_preflight()

    assert eula.isChecked()
    assert started == [(
        "preflight",
        ["--profile", "highschoolblood-demo", "--steps", "10", "--eula-cleared"],
    )]


def test_preflight_does_not_assume_eula_ack(make_widget) -> None:
    widget = make_widget()
    started: list[tuple[str, list[str]]] = []
    widget._start_process = lambda operation, args: started.append((operation, args))

    widget.run_preflight()

    assert started == [("preflight", ["--profile", "highschoolblood-demo", "--steps", "10"])]


def test_preflight_blocker_is_shown_as_reviewable_card(
    make_widget: Callable[..., QACommandCenterWidget], tmp_path: Path
) -> None:
    store = ActionCardStore(tmp_path / "review-cards.json")
    card = ActionCard.proposed(
        title="VLM unavailable",
        persona="QA Intake",
        category="preflight_blocker",
        summary="Local vision endpoint is not ready.",
        recommendation="Start the approved local vision service.",
        risk="high",
    )
    store.add(card)
    widget = make_widget(store)

    assert widget._cards.count() == 1
    widget._cards.setCurrentRow(0)
    widget._approve.click()

    assert store.list_cards()[0].status is CardStatus.APPROVED
    assert not widget.findChild(QPushButton, "runSupervisedSmoke").isEnabled()
