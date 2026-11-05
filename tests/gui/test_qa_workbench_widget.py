from __future__ import annotations

import os
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.gui.widgets.qa_workbench_widget import QAWorkbenchWidget  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return cast(QApplication, QApplication.instance() or QApplication([]))


def test_fmv_demo_is_default_profile_and_fmv_cases_are_available(app: QApplication) -> None:
    widget = QAWorkbenchWidget()

    assert widget._profiles.currentText() == "highschoolblood-demo"
    cases = [
        widget._cases.item(index).text()
        for index in range(widget._cases.count())
    ]
    assert any(item.startswith("FMV-FLOW-001") for item in cases)
    assert any(item.startswith("FMV-MINIGAME-001") for item in cases)
