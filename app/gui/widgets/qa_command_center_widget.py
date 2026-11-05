from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.paths import writable_base, writable_path
from qa_framework.command_center import ActionCard, ActionCardStore, CardStatus

ROOT = Path(__file__).resolve().parents[3]
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
WRITABLE_ROOT = writable_base()
CARD_STORE = writable_path("reports", "qa_command_center", "cards.json")


class QACommandCenterWidget(QWidget):
    """Local-first QA inbox with human-reviewed cards and gated game controls."""

    def __init__(self, store: ActionCardStore | None = None) -> None:
        super().__init__()
        self._store = store or ActionCardStore(CARD_STORE)
        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(WRITABLE_ROOT))
        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)
        self._process.readyReadStandardOutput.connect(self._read_output)
        self._process.readyReadStandardError.connect(self._read_error)
        self._output = bytearray()
        self._operation = ""
        self._latest_manifest: Path | None = None
        self._preflight_ready = False

        self._status = QLabel("Ready — no gameplay has been run by this panel.")
        self._steps = QSpinBox()
        self._steps.setRange(1, 60)
        self._steps.setValue(10)
        self._eula_cleared = QCheckBox("I personally handled and cleared the in-game EULA")
        self._preflight_button = QPushButton("Run safe preflight")
        self._execute_button = QPushButton("Start supervised smoke test")
        self._eula_cleared.setObjectName("eulaCleared")
        self._preflight_button.setObjectName("runPreflight")
        self._execute_button.setObjectName("runSupervisedSmoke")
        self._execute_button.setEnabled(False)
        self._preflight_button.clicked.connect(self.run_preflight)
        self._execute_button.clicked.connect(self.run_supervised_smoke)
        self._eula_cleared.toggled.connect(self._update_execution_gate)

        self._cards = QListWidget()
        self._details = QTextBrowser()
        self._cards.currentItemChanged.connect(self._show_card)
        self._approve = QPushButton("Approve recommendation")
        self._dismiss = QPushButton("Dismiss")
        self._approve.clicked.connect(lambda: self._decide(CardStatus.APPROVED))
        self._dismiss.clicked.connect(lambda: self._decide(CardStatus.DISMISSED))

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Max steps"))
        controls.addWidget(self._steps)
        controls.addWidget(self._preflight_button)
        controls.addWidget(self._execute_button)

        decision_row = QHBoxLayout()
        decision_row.addWidget(self._approve)
        decision_row.addWidget(self._dismiss)
        decision_row.addStretch()

        card_column = QVBoxLayout()
        card_column.addWidget(
            QLabel("QA Action Cards — local proposals; approval does not execute them")
        )
        card_column.addWidget(self._cards)
        card_column.addLayout(decision_row)

        detail_column = QVBoxLayout()
        detail_column.addWidget(QLabel("Review"))
        detail_column.addWidget(self._details)

        body = QHBoxLayout()
        body.addLayout(card_column, 2)
        body.addLayout(detail_column, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("High School Blood Demo · Local QA Command Center"))
        layout.addWidget(self._status)
        layout.addLayout(controls)
        layout.addWidget(self._eula_cleared)
        layout.addLayout(body)
        self.refresh_cards()

    def run_preflight(self) -> None:
        self._preflight_ready = False
        self._update_execution_gate()
        args = ["--profile", "highschoolblood-demo", "--steps", str(self._steps.value())]
        if self._eula_cleared.isChecked():
            args.append("--eula-cleared")
        self._start_process(
            "preflight",
            args,
        )

    def run_supervised_smoke(self) -> None:
        if not self._preflight_ready:
            QMessageBox.warning(
                self, "Preflight required", "Run and pass preflight before gameplay."
            )
            return
        if not self._eula_cleared.isChecked():
            QMessageBox.warning(
                self, "EULA confirmation required", "The user must handle the EULA directly."
            )
            return
        self._start_process(
            "execute",
            [
                "--profile",
                "highschoolblood-demo",
                "--steps",
                str(self._steps.value()),
                "--execute",
                "--eula-cleared",
            ],
        )

    def _start_process(self, operation: str, args: list[str]) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            return
        self._operation = operation
        self._output.clear()
        self._status.setText(f"Running {operation}…")
        self._preflight_button.setEnabled(False)
        self._execute_button.setEnabled(False)
        if getattr(sys, "frozen", False):
            self._process.start(
                sys.executable, ["--qa-worker", "scripts.fmv_harness", *args]
            )
        else:
            script = str(RESOURCE_ROOT / "scripts" / "fmv_harness.py")
            self._process.start(sys.executable, [script, *args])

    def _read_output(self) -> None:
        self._output.extend(self._process.readAllStandardOutput().data())

    def _read_error(self) -> None:
        self._output.extend(self._process.readAllStandardError().data())

    def _on_process_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self._read_output()
        if self._operation == "execute":
            self._eula_cleared.setChecked(False)
        manifest = self._extract_manifest(bytes(self._output).decode("utf-8", errors="replace"))
        self._preflight_button.setEnabled(True)
        if manifest is None:
            self._status.setText(
                f"{self._operation} failed; no run manifest was returned (exit {exit_code})."
            )
            self._update_execution_gate()
            return
        self._latest_manifest = manifest
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if self._operation == "preflight":
                self._store.ingest_preflight(manifest)
                self._preflight_ready = data.get("status") == "PREFLIGHT_READY"
                blockers = ", ".join(data.get("blockers", [])) or "none"
                self._status.setText(f"Preflight: {data.get('status')} · blockers: {blockers}")
            else:
                self._preflight_ready = False
                self._store.add(
                    ActionCard.proposed(
                        title=f"Review supervised run {data.get('run_id', '')}",
                        persona="Evidence & Defect Auditor",
                        category="run_review",
                        summary=(
                            f"Harness status: {data.get('status')}; "
                            f"QA status: {data.get('qa_status', 'UNASSERTED')}."
                        ),
                        recommendation=(
                            "Review manifest, trace, assertions, and evidence. "
                            "Do not treat an unasserted run as PASS."
                        ),
                        source_refs=[str(manifest)],
                        risk="high",
                    )
                )
            self.refresh_cards()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._status.setText(f"Run ended, but manifest review failed: {exc}")
        self._update_execution_gate()

    @staticmethod
    def _extract_manifest(output: str) -> Path | None:
        decoder = json.JSONDecoder()
        start = output.find("{")
        if start < 0:
            return None
        try:
            payload, _ = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            return None
        manifest_path = payload.get("run_manifest")
        if manifest_path:
            path = Path(manifest_path)
            return path if path.is_file() else None
        run_id = payload.get("run_id")
        profile = payload.get("profile")
        if run_id and profile:
            path = WRITABLE_ROOT / "reports" / "fmv_harness" / f"{run_id}_{profile}" / "run_manifest.json"
            return path if path.is_file() else None
        return None

    def refresh_cards(self) -> None:
        selected_id = self._selected_card_id()
        self._cards.clear()
        for card in self._store.list_cards():
            item = QListWidgetItem(f"{card.status.value} · {card.persona} · {card.title}")
            item.setData(256, card.card_id)
            self._cards.addItem(item)
            if card.card_id == selected_id:
                self._cards.setCurrentItem(item)
        if self._cards.currentItem() is None and self._cards.count():
            self._cards.setCurrentRow(0)

    def _selected_card_id(self) -> str | None:
        item = self._cards.currentItem()
        return str(item.data(256)) if item is not None else None

    def _show_card(self, item: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if item is None:
            self._details.clear()
            self._approve.setEnabled(False)
            self._dismiss.setEnabled(False)
            return
        card = next((c for c in self._store.list_cards() if c.card_id == item.data(256)), None)
        if card is None:
            return
        refs = "<br>".join(escape(reference) for reference in card.source_refs)
        self._details.setHtml(
            f"<h3>{escape(card.title)}</h3><p><b>Role:</b> {escape(card.persona)} · "
            f"<b>Risk:</b> {escape(card.risk)}</p>"
            f"<p>{escape(card.summary)}</p><p><b>Recommendation</b><br>"
            f"{escape(card.recommendation)}</p>"
            f"<p><b>Sources</b><br>{refs or 'None'}</p>"
            f"<p><b>Decision:</b> {escape(card.decision_by or 'Pending')} "
            f"{escape(card.decision_note)}</p>"
        )
        pending = card.status is CardStatus.PROPOSED
        self._approve.setEnabled(pending)
        self._dismiss.setEnabled(pending)

    def _decide(self, status: CardStatus) -> None:
        card_id = self._selected_card_id()
        if not card_id:
            return
        self._store.decide(card_id, status, "Local QA reviewer")
        self.refresh_cards()

    def _update_execution_gate(self) -> None:
        idle = self._process.state() == QProcess.ProcessState.NotRunning
        self._execute_button.setEnabled(
            idle and self._preflight_ready and self._eula_cleared.isChecked()
        )

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        self._preflight_button.setEnabled(True)
        self._status.setText(f"Could not start {self._operation}: {error.name}")
        self._update_execution_gate()
