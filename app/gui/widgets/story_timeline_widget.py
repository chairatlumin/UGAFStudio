from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.story_timeline_controller import StoryTimelineController
from app.qa.story_timeline import StoryScene


class StoryTimelineWidget(QWidget):
    """Story scene explorer with subtitle timing, branches, patch notes and QA audit."""

    def __init__(self, controller: StoryTimelineController | None = None) -> None:
        super().__init__()
        self.controller = controller or StoryTimelineController()
        self._selected_scene = ""
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search scene, group, or patch note…")
        self._scene_list = QListWidget()
        self._scene_list.setMinimumWidth(230)
        self._title = QLabel("Select a scene")
        self._meta = QLabel("Read-only sources · timeline changes auto-save to local SQLite")
        self._overview = QLabel()
        self._locale = QComboBox()
        self._locale.addItems(["th", "en"])
        self._timeline_scene = QGraphicsScene(self)
        self._timeline = QGraphicsView(self._timeline_scene)
        self._timeline.setMinimumHeight(170)
        self._timeline.setStyleSheet(
            "background:#101820;border:1px solid #34424a;border-radius:8px"
        )
        self._cue_table = QTableWidget(0, 5)
        self._cue_table.setHorizontalHeaderLabels(["Key", "Time", "Thai", "English", "Source"])
        self._cue_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._cue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._patch_list = QListWidget()
        self._finding_list = QListWidget()
        self._vision_evidence = QListWidget()
        self._target = QComboBox()
        self._choice_key = QLineEdit()
        self._choice_key.setPlaceholderText("Choice key (optional)")
        self._links = QListWidget()
        self._build_ui()
        self._search.textChanged.connect(self._refresh_scenes)
        self._scene_list.currentItemChanged.connect(self._on_scene_selected)
        self._locale.currentTextChanged.connect(self._render_scene)
        self._refresh()

    def _build_ui(self) -> None:
        toolbar = QHBoxLayout()
        for title, handler in (
            ("เพิ่ม Patch Note", self._add_patch_note),
            ("นำเข้า Patch/Dev Update", self._import_patch),
            ("นำเข้า Localization", self._import_localization),
            ("Open Project", self._open_project),
            ("Save Project", self._save_project),
        ):
            button = QPushButton(title)
            button.clicked.connect(handler)
            toolbar.addWidget(button)
        toolbar.addStretch()

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._search)
        left_layout.addWidget(self._scene_list)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 0, 0, 0)
        detail_layout.addWidget(self._title)
        detail_layout.addWidget(self._meta)
        locale_row = QHBoxLayout()
        locale_row.addWidget(QLabel("Timeline language"))
        locale_row.addWidget(self._locale)
        locale_row.addStretch()
        detail_layout.addLayout(locale_row)
        detail_layout.addWidget(self._timeline)
        detail_layout.addWidget(self._cue_table, 2)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(detail)
        split.setStretchFactor(1, 1)

        lower = QSplitter(Qt.Orientation.Horizontal)
        lower.addWidget(self._panel("Patch note changes", self._patch_list))
        lower.addWidget(self._panel("Story links", self._build_links_panel()))
        lower.addWidget(self._panel("QA findings", self._finding_list))
        lower.addWidget(self._panel("Image analysis evidence", self._vision_evidence))
        lower.setStretchFactor(0, 1)
        lower.setStretchFactor(1, 1)
        lower.setStretchFactor(2, 1)
        lower.setStretchFactor(3, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self._overview)
        layout.addWidget(split, 3)
        layout.addWidget(lower, 2)

    def _panel(self, title: str, content: QWidget) -> QWidget:
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(6, 6, 6, 6)
        heading = QLabel(title)
        heading.setStyleSheet("font-weight:600;color:#d8e0e5")
        panel_layout.addWidget(heading)
        panel_layout.addWidget(content)
        return panel

    def _build_links_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(self._target, 2)
        row.addWidget(self._choice_key, 2)
        add = QPushButton("Link")
        add.clicked.connect(self._add_link)
        row.addWidget(add)
        remove = QPushButton("Remove")
        remove.clicked.connect(self._remove_link)
        row.addWidget(remove)
        layout.addLayout(row)
        layout.addWidget(self._links)
        return panel

    def _refresh(self) -> None:
        summary = self.controller.service.project.source_summary
        self._overview.setText(
            f"ซีน {len(self.controller.service.project.scenes):,}  |  "
            f"ซับไตเติล {summary.get('subtitle_cues', 0):,}  |  "
            f"ตัวเลือก {summary.get('choice_keys', 0):,}  |  "
            f"Patch note {len(self.controller.service.project.patch_items):,}  |  "
            f"ข้อขัดแย้ง {len(self.controller.service.project.conflicts):,}"
        )
        self._overview.setStyleSheet("color:#83d4c1;padding:4px 2px")
        self._refresh_scenes()
        self._target.clear()
        self._target.addItems(sorted(self.controller.service.project.scenes))
        self._patch_list.clear()
        for item in self.controller.service.project.patch_items:
            refs = f" · {', '.join(item.scene_ids)}" if item.scene_ids else ""
            self._patch_list.addItem(f"[{item.version or item.category}] {item.text}{refs}")
        self._render_scene()
        self._render_findings()
        self.refresh_evidence()

    def refresh_evidence(self) -> None:
        self._vision_evidence.clear()
        database = self.controller.service.database
        profile = self.controller.service.database_profile
        for item in database.list_story_evidence(profile):
            scene = item["scene_id"] or "ไม่ระบุซีน"
            result = item["result"]
            detected = str(result.get("detected_text", "")).replace("\n", " ")[:100]
            self._vision_evidence.addItem(f"{scene} · {detected} · {item['image_path']}")

    def _refresh_scenes(self) -> None:
        project = self.controller.service.project
        query = self._search.text().casefold().strip()
        current = self._selected_scene
        self._scene_list.clear()
        for scene in sorted(
            project.scenes.values(), key=lambda entry: (entry.order, entry.scene_id)
        ):
            status_counts = Counter(str(case.get("status", "")).casefold() for case in scene.cases)
            label = f"{scene.scene_id}  ·  {len(scene.cues)} cues"
            if status_counts.get("fail"):
                label += f"  ·  {status_counts['fail']} fail"
            if query and query not in f"{scene.scene_id} {scene.group}".casefold():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, scene.scene_id)
            self._scene_list.addItem(item)
            if scene.scene_id == current:
                self._scene_list.setCurrentItem(item)
        if self._scene_list.count() and self._scene_list.currentRow() < 0:
            self._scene_list.setCurrentRow(0)

    def _on_scene_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is not None:
            self._selected_scene = str(current.data(Qt.ItemDataRole.UserRole))
        self._render_scene()

    def _render_scene(self, *_args: str) -> None:
        scene = self.controller.service.project.scenes.get(self._selected_scene)
        if scene is None:
            self._title.setText("Select a scene")
            self._meta.setText("Import sources to assemble the story timeline")
            self._cue_table.setRowCount(0)
            self._timeline_scene.clear()
            self._patch_list.clear()
            return
        cases = scene.cases
        statuses = Counter(str(case.get("status", "pending")).casefold() for case in cases)
        self._title.setText(scene.scene_id)
        self._meta.setText(
            f"{scene.group}  ·  {len(scene.cues)} subtitle cues  ·  "
            f"{len(scene.choices)} choices  ·  "
            f"QA: {statuses.get('pass', 0)} pass / {statuses.get('fail', 0)} fail / "
            f"{statuses.get('pending', 0)} pending"
        )
        self._draw_timeline(scene)
        self._cue_table.setRowCount(len(scene.cues))
        for row, cue in enumerate(scene.cues):
            values = [
                cue.key,
                f"{cue.start:.3f}–{cue.end:.3f}s",
                cue.translations.get("th", ""),
                cue.translations.get("en", ""),
                cue.source_sheet,
            ]
            for column, value in enumerate(values):
                self._cue_table.setItem(row, column, QTableWidgetItem(value))
        self._patch_list.clear()
        for item in self.controller.service.project.patch_items:
            if not item.scene_ids or self._selected_scene in item.scene_ids:
                self._patch_list.addItem(f"[{item.version or item.category}] {item.text}")
        self._links.clear()
        for link in scene.outgoing:
            choice = f" via {link['choice_key']}" if link.get("choice_key") else ""
            self._links.addItem(f"→ {link['target']}{choice}")

    def _draw_timeline(self, scene: StoryScene) -> None:
        self._timeline_scene.clear()
        self._timeline_scene.addText(f"{self._locale.currentText().upper()} subtitle timing")
        cues = [cue for cue in scene.cues if cue.translations.get(self._locale.currentText(), "")]
        max_time = max((cue.end for cue in cues), default=10.0)
        scale = min(48.0, 1200.0 / max(max_time, 1.0))
        left, top = 54.0, 52.0
        self._timeline_scene.addLine(
            left, top + 30, left + max_time * scale, top + 30, QPen(QColor("#63727b"))
        )
        for tick in range(int(max_time) + 1):
            x = left + tick * scale
            self._timeline_scene.addLine(x, top + 26, x, top + 35, QPen(QColor("#63727b")))
            if tick % 2 == 0:
                label = self._timeline_scene.addText(str(tick))
                label.setDefaultTextColor(QColor("#aab7be"))
                label.setPos(x - 3, top + 36)
        for row, cue in enumerate(cues):
            x = left + cue.start * scale
            width = max(8.0, (cue.end - cue.start) * scale)
            y = top + 58 + row % 3 * 27
            rect = self._timeline_scene.addRect(
                x, y, width, 21, QPen(QColor("#7bd6c4")), QBrush(QColor("#245b55"))
            )
            rect.setToolTip(f"{cue.key}\n{cue.translations.get(self._locale.currentText(), '')}")
            if width > 85:
                text = self._timeline_scene.addText(cue.translations[self._locale.currentText()])
                text.setDefaultTextColor(QColor("#edf7f5"))
                text.setPos(x + 4, y)
        self._timeline_scene.setSceneRect(0, 0, max(800.0, left + max_time * scale + 40), 190)

    def _render_findings(self) -> None:
        self._finding_list.clear()
        findings = self.controller.service.audit()
        for finding in findings[:500]:
            prefix = "ERROR" if finding.severity == "error" else "WARN"
            scene = f" · {finding.scene_id}" if finding.scene_id else ""
            self._finding_list.addItem(f"{prefix} · {finding.message}{scene}")
        if not findings:
            self._finding_list.addItem("No timeline findings")

    def _add_link(self) -> None:
        if not self._selected_scene:
            return
        try:
            self.controller.service.add_link(
                self._selected_scene, self._target.currentText(), self._choice_key.text()
            )
        except ValueError as exc:
            self._error(str(exc))
            return
        self._choice_key.clear()
        self._refresh()

    def _remove_link(self) -> None:
        selected = self._links.currentRow()
        if selected >= 0 and self._selected_scene:
            self.controller.service.remove_link(self._selected_scene, selected)
            self._refresh()

    def _import_patch(self) -> None:
        source, accepted = self._source_dialog(
            "วางลิงก์ชีต Patch/Dev Update หรือเลือกไฟล์ .xlsx/.txt",
            "https://docs.google.com/spreadsheets/d/1O330dlrm8_6G4N9CXxzoYhTbT-DIluwPp1Vu6z4M0tA/edit?gid=0#gid=0",
        )
        if not accepted or not source:
            return
        self._run_import(lambda: self.controller.import_patch_note(source), "patch items")

    def _add_patch_note(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("เพิ่ม Patch Note ในเครื่อง")
        dialog.setMinimumWidth(460)
        form = QFormLayout(dialog)
        version = QLineEdit()
        version.setPlaceholderText("เช่น V0.0.3")
        build = QLineEdit()
        build.setPlaceholderText("เช่น 25325884 (ถ้ามี)")
        category = QComboBox()
        category.addItems(["release", "bugfix", "localization", "minigame", "other"])
        scenes = QLineEdit()
        scenes.setPlaceholderText("ใส่ Scene ID คั่นด้วย comma (ไม่บังคับ)")
        note = QPlainTextEdit()
        note.setPlaceholderText("เขียนสิ่งที่ Dev เปลี่ยน หรือสิ่งที่ QA ควรตรวจซ้ำ")
        form.addRow("Version *", version)
        form.addRow("Build ID", build)
        form.addRow("ประเภท", category)
        form.addRow("Scene ID", scenes)
        form.addRow("รายละเอียด *", note)
        form.addRow(QLabel("บันทึกในฐานข้อมูลเครื่องนี้เท่านั้น ไม่แก้ Google Sheet ต้นฉบับ"))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.controller.service.add_patch_note(
                version=version.text(),
                build_id=build.text(),
                category=category.currentText(),
                text=note.toPlainText(),
                scene_ids=scenes.text().split(","),
            )
        except ValueError as exc:
            self._error(str(exc))
            return
        self._refresh()
        QMessageBox.information(self, "บันทึกแล้ว", "เพิ่ม Patch Note ในฐานข้อมูลเกมแล้ว")

    def _import_localization(self) -> None:
        source, accepted = self._source_dialog(
            "Localization Google Sheets URL or local .xlsx path",
            "https://docs.google.com/spreadsheets/d/1b_N7FjwOKSOphXd5m0w-XxfeZcESebjnxFd4aX_Gzfk/edit?gid=1121086550",
        )
        if not accepted or not source:
            return
        self._run_import(lambda: self.controller.import_localization(source), "subtitle cues")

    def _source_dialog(self, prompt: str, initial_value: str) -> tuple[str, bool]:
        return QInputDialog.getText(self, "Read-only source import", prompt, text=initial_value)

    def _run_import(self, operation: Callable[[], int], item_label: str) -> None:
        try:
            count = operation()
        except (OSError, ValueError, KeyError) as exc:
            self._error(str(exc))
            return
        self._refresh()
        QMessageBox.information(self, "Import complete", f"Imported {count} {item_label}.")

    def _save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save timeline project", "story-timeline.json", "JSON (*.json)"
        )
        if path:
            try:
                self.controller.save(Path(path))
            except OSError as exc:
                self._error(str(exc))

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open timeline project", "", "JSON (*.json)")
        if path:
            try:
                self.controller.load(Path(path))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self._error(str(exc))
                return
            self._selected_scene = ""
            self._refresh()

    def _error(self, message: str) -> None:
        QMessageBox.warning(self, "Story Timeline", message)
