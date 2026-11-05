"""Narrow QA Workbench: fresh per-run profile/case selection, bounded VLM play.

All live gameplay runs in the VLM runner child process spawned by
qa_framework.mcp_tools; this widget never synthesizes input frames.
QA status stays UNASSERTED unless stored assertions support otherwise.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class QAWorkbenchWidget(QWidget):
    """Manual per-session QA launcher with live logs and auto DOCX export."""

    def __init__(self) -> None:
        super().__init__()
        self._run_id: str | None = None
        self._completed_run_id = ""
        self._profile = ""
        self._run_dir: Path | None = None
        self._stdout_pos = 0
        self._stderr_pos = 0
        self._finished = False
        self._draft = ""

        self._profiles = QComboBox()
        self._profiles.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_profiles)
        top = QHBoxLayout()
        top.addWidget(QLabel("เกม"))
        top.addWidget(self._profiles, 1)
        top.addWidget(refresh)
        self._profiles.currentTextChanged.connect(self._on_profile_changed)

        self._categories = QListWidget()
        self._categories.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._cases = QListWidget()
        self._cases.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        lists = QSplitter(Qt.Orientation.Horizontal)
        left, right = QWidget(), QWidget()
        left_layout, right_layout = QVBoxLayout(left), QVBoxLayout(right)
        left_layout.addWidget(QLabel("ประเภทการทดสอบ (เลือกได้หลายประเภท)"))
        left_layout.addWidget(self._categories)
        right_layout.addWidget(QLabel("Test case (เลือกอย่างน้อย 1 เคส หรือเลือกประเภทด้านซ้าย)"))
        right_layout.addWidget(self._cases)
        lists.addWidget(left)
        lists.addWidget(right)

        self._steps = QSpinBox()
        self._steps.setRange(1, 600)
        self._steps.setValue(30)
        self._confirm_input = QCheckBox("อนุญาตให้ AI กดปุ่ม/คลิกในเกมรอบนี้")
        self._confirm_eula = QCheckBox("ฉันเปิดเกมและจัดการ EULA ด้วยตัวเองแล้ว")
        bounds = QHBoxLayout()
        bounds.addWidget(QLabel("จำนวนจังหวะสูงสุด"))
        bounds.addWidget(self._steps)
        bounds.addStretch()
        bounds.addWidget(self._confirm_input)

        self._start = QPushButton("เริ่มทดสอบ")
        self._stop = QPushButton("หยุดทดสอบ")
        self._stop.setEnabled(False)
        self._start.clicked.connect(self.start_run)
        self._stop.clicked.connect(self.stop_run)
        actions = QHBoxLayout()
        actions.addWidget(self._start)
        actions.addWidget(self._stop)
        actions.addStretch()

        self._status = QLabel("เริ่มจากเลือกเกมและหัวข้อทดสอบ ระบบจะบันทึกผลและสร้างรายงานให้อัตโนมัติ")
        self._status.setWordWrap(True)

        self._log = QTextBrowser()
        self._log.setPlaceholderText("สถานะการทำงานและเหตุการณ์ที่พบจะแสดงที่นี่")
        self._result = QTextBrowser()
        self._result.setMaximumHeight(160)
        self._copy_draft = QPushButton("คัดลอกร่าง Feedback")
        self._save_feedback = QPushButton("บันทึกร่าง Feedback")
        self._copy_draft.setEnabled(False)
        self._save_feedback.setEnabled(False)
        self._copy_draft.clicked.connect(self._on_copy_draft)
        self._save_feedback.clicked.connect(self._on_save_feedback)
        draft_row = QHBoxLayout()
        draft_row.addWidget(self._copy_draft)
        draft_row.addWidget(self._save_feedback)
        draft_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("เลือกเกม → เลือกสิ่งที่ต้องตรวจ → เริ่มทดสอบ → รับรายงาน Word"))
        layout.addLayout(top)
        layout.addWidget(lists, 3)
        layout.addLayout(bounds)
        layout.addWidget(self._confirm_eula)
        layout.addLayout(actions)
        layout.addWidget(self._status)
        layout.addWidget(QLabel("บันทึกการทดสอบสด"))
        layout.addWidget(self._log, 2)
        layout.addWidget(QLabel("รายงานและหลักฐาน"))
        layout.addWidget(self._result, 1)
        layout.addLayout(draft_row)

        self._poller = QTimer(self)
        self._poller.setInterval(1000)
        self._poller.timeout.connect(self._poll)
        self.refresh_profiles()

    # -- discovery ---------------------------------------------------------
    def select_profile(self, profile: str) -> bool:
        """Select a known profile; return False when it is unavailable."""
        index = self._profiles.findText(profile)
        if index < 0:
            return False
        self._profiles.setCurrentIndex(index)
        return True

    def refresh_profiles(self) -> None:
        try:
            from qa_framework.mcp_tools import list_game_profiles_tool
        except Exception as exc:
            self._status.setText(f"Could not list profiles: {exc}")
            return
        try:
            payload = list_game_profiles_tool()
        except Exception as exc:
            self._status.setText(f"Could not list profiles: {exc}")
            return
        current = self._profiles.currentText()
        self._profiles.blockSignals(True)
        self._profiles.clear()
        profile_ids: list[str] = []
        for entry in payload.get("profiles", []):
            profile = str(entry.get("profile", ""))
            self._profiles.addItem(profile)
            profile_ids.append(profile)
        preferred = (
            current if current in profile_ids
            else "highschoolblood-demo" if "highschoolblood-demo" in profile_ids
            else (profile_ids[0] if profile_ids else "")
        )
        if preferred:
            self._profiles.setCurrentIndex(self._profiles.findText(preferred))
        self._profiles.blockSignals(False)
        self._on_profile_changed(self._profiles.currentText())

    @Slot(str)
    def _on_profile_changed(self, profile: str) -> None:
        self._categories.clear()
        self._cases.clear()
        if not profile:
            return
        try:
            from qa_framework.mcp_tools import describe_qa_selection_tool

            selection = describe_qa_selection_tool(profile)
        except Exception as exc:
            self._status.setText(f"Could not describe {profile!r}: {exc}")
            return
        for category in selection.get("categories", []):
            QListWidgetItem(str(category), self._categories)
        for case in selection.get("cases", []):
            item = QListWidgetItem(f"{case.get('id')} — {case.get('title')}", self._cases)
            item.setData(Qt.ItemDataRole.UserRole, str(case.get("id", "")))
        needs_eula = bool(selection.get("requires_eula_ack", False))
        self._confirm_eula.setEnabled(needs_eula)
        self._confirm_eula.setChecked(False)
        self._confirm_eula.setText(
            "I personally handled and cleared the in-game EULA (required for this profile)"
            if needs_eula
            else "EULA acknowledgement not required for this profile"
        )

    # -- run lifecycle ------------------------------------------------------
    def _selected(self) -> tuple[list[str], list[str]]:
        cats = [item.text() for item in self._categories.selectedItems()]
        ids = [
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self._cases.selectedItems()
            if str(item.data(Qt.ItemDataRole.UserRole))
        ]
        return cats, ids

    def start_run(self) -> None:
        profile = self._profiles.currentText().strip()
        if not profile:
            QMessageBox.warning(self, "No profile", "Select a game profile first.")
            return
        categories, case_ids = self._selected()
        if not categories and not case_ids:
            QMessageBox.warning(
                self, "Nothing selected", "Select at least one category or case."
            )
            return
        if not self._confirm_input.isChecked():
            QMessageBox.warning(
                self, "Confirmation required", "Tick the live-input authorization box."
            )
            return
        if self._confirm_eula.isEnabled() and not self._confirm_eula.isChecked():
            QMessageBox.warning(
                self, "EULA confirmation required", "The user must handle the EULA directly."
            )
            return
        if self._run_id is not None:
            return
        self._status.setText(f"Starting {profile}…")
        self._log.clear()
        self._result.clear()
        self._stdout_pos = self._stderr_pos = 0
        self._finished = False
        thread = threading.Thread(
            target=self._start_in_background,
            args=(profile, categories, case_ids, self._steps.value(),
                  self._confirm_input.isChecked(), self._confirm_eula.isChecked()),
            daemon=True,
        )
        thread.start()
        self._start.setEnabled(False)
        self._stop.setEnabled(True)
        self._poller.start()

    def _start_in_background(
        self, profile: str, categories: list[str], case_ids: list[str],
        max_steps: int, confirm_input: bool, confirm_eula: bool,
    ) -> None:
        try:
            from qa_framework.mcp_tools import start_live_session_tool

            run = start_live_session_tool(
                profile=profile,
                max_steps=max_steps,
                confirm_gameplay_input=confirm_input,
                confirm_eula_cleared=confirm_eula,
                case_ids=case_ids,
                categories=categories or None,
            )
            self._run_id = str(run.get("run_id", ""))
            self._profile = profile
            self._run_dir = Path(str(run.get("run_dir", "")))
        except Exception as exc:  # surfaced on next poll tick
            self._run_id = f"ERROR: {exc}"

    def stop_run(self) -> None:
        if not self._run_id or self._run_id.startswith("ERROR"):
            return
        try:
            from qa_framework.mcp_tools import stop_live_session_tool

            stop_live_session_tool(self._run_id)
            self._status.setText(f"Stop requested for {self._run_id}.")
        except Exception as exc:
            self._status.setText(f"Stop failed: {exc}")

    # -- polling / completion ------------------------------------------------
    def _poll(self) -> None:
        if self._run_id is None:
            return
        if self._run_id.startswith("ERROR"):
            self._poller.stop()
            self._status.setText(f"Start failed: {self._run_id[7:]}")
            self._run_id = None
            self._start.setEnabled(True)
            self._stop.setEnabled(False)
            return
        self._tail_logs()
        try:
            from qa_framework.mcp_tools import list_live_runs_tool

            runs = {r.get("run_id"): r for r in list_live_runs_tool().get("runs", [])}
        except Exception as exc:
            self._status.setText(f"Run {self._run_id} active; status poll failed: {exc}")
            return
        run = runs.get(self._run_id)
        if run is None:
            return
        status = str(run.get("status", "RUNNING"))
        if status == "RUNNING":
            self._status.setText(f"Run {self._run_id} RUNNING — qa: {run.get('qa_status')}")
            return
        self._poller.stop()
        self._tail_logs()
        self._on_finished(run)

    def _tail_logs(self) -> None:
        if self._run_dir is None:
            return
        for name, attr in (("stdout.log", "_stdout_pos"), ("stderr.log", "_stderr_pos")):
            path = self._run_dir / name
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            pos = getattr(self, attr)
            if len(text) > pos:
                self._log.append(text[pos : pos + 20000])
                setattr(self, attr, len(text))

    def _on_finished(self, run: dict[str, Any]) -> None:
        self._finished = True
        run_id = str(run.get("run_id", self._run_id))
        self._completed_run_id = run_id
        try:
            from qa_framework.mcp_tools import (
                export_testcase_report_docx_tool,
                get_testcase_report_tool,
            )

            exported = export_testcase_report_docx_tool(run_id=run_id, profile=self._profile)
            payload = get_testcase_report_tool(run_id=run_id, profile=self._profile)
            results = list(payload.get("testcase_results", []))
            docx = str(exported.get("docx_path", ""))
            qa_status = str(exported.get("qa_status", "UNASSERTED"))
            # ponytail: report stays beside exe when frozen; never claim more than stored.
            self._status.setText(f"Run {run_id} {run.get('status')} — QA: {qa_status}")
            self._result.setPlainText(
                f"DOCX: {docx}\nQA status: {qa_status}\nCases: {len(results)}\n"
                f"Trace: {run.get('trace')}\nManifest: {run.get('manifest')}"
            )
            self._draft = self._build_draft(run, results)
            self._copy_draft.setEnabled(True)
            self._save_feedback.setEnabled(True)
        except Exception as exc:
            self._status.setText(f"Run {run_id} ended; auto-export failed: {exc}")
            self._draft = (
                f"[DRAFT feedback — run {run_id}, profile {self._profile}]\n"
                f"Auto-export failed ({exc}); outcome UNASSERTED. "
                "Human review required; nothing here is a PASS."
            )
            self._copy_draft.setEnabled(True)
        self._run_id = None
        self._start.setEnabled(True)
        self._stop.setEnabled(False)

    @staticmethod
    def _build_draft(run: dict[str, Any], results: list[dict[str, Any]]) -> str:
        bad = [r for r in results if str(r.get("status", "")) not in ("PASS",)]
        lines = [
            f"[DRAFT feedback — run {run.get('run_id')}, profile {run.get('profile')}]",
            f"Run status: {run.get('status')}; QA status: {run.get('qa_status', 'UNASSERTED')}.",
        ]
        if not results:
            lines.append("No testcase results recorded — UNASSERTED, needs human review.")
        else:
            lines.append(f"{len(bad)} of {len(results)} case(s) need review:")
            for item in bad[:10]:
                lines.append(
                    f"- {item.get('case_id')}: {item.get('status', 'UNASSERTED')} — "
                    f"observed: {item.get('observed') or '—'}"
                )
        lines.append("Uncertainty: VLM observations only; nothing above is a PASS.")
        return "\n".join(lines)

    # -- draft feedback -------------------------------------------------------
    def _on_copy_draft(self) -> None:
        QApplication.clipboard().setText(self._draft)
        self._status.setText("Draft copied — review before sharing; it is not a verdict.")

    def _on_save_feedback(self) -> None:
        if not self._finished or not self._draft:
            return
        confirm = QMessageBox.question(
            self, "Save feedback?", "Save this DRAFT note to the local feedback log?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            from qa_framework.mcp_tools import record_feedback_tool

            record_feedback_tool(
                category="workbench_draft",
                note=self._draft,
                run_id=self._completed_run_id,
                profile=self._profile,
            )
            self._status.setText("Draft saved to local feedback log (source data untouched).")
        except Exception as exc:
            self._status.setText(f"Saving feedback failed: {exc}")
