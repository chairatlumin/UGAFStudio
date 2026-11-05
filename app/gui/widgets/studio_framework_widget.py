from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.paths import writable_path
from app.database.database import PROFILE_DB_DIR, QADatabase, sanitize_profile_key
from app.qa.game_memory_vault import export_game_vault, search_game_memory
from app.qa.workbook_import import import_source_document, import_source_workbook
from app.services.comfyui_service import ComfyUIService

DEMO_WORKBOOK_URL = (
    "https://docs.google.com/spreadsheets/d/1O330dlrm8_6G4N9CXxzoYhTbT-DIluwPp1Vu6z4M0tA/edit"
)
FULL_WORKBOOK_URL = "https://docs.google.com/spreadsheets/d/1ohPVHfDdJWKfWMRSH445erC4y1cRgFfE/edit"
DEMO_SOURCES = [
    DEMO_WORKBOOK_URL,
    "https://docs.google.com/spreadsheets/d/1YgM62LkVJzsdqQmRqOnDDzA-927QoYzLrue4QGw-Mww/edit",
    "https://docs.google.com/document/d/1xUEw3M7H5F4_bgO_bjlT0JbsLRDnItNVdxL5XCCQYb8/edit",
]
FULL_SOURCES = [
    FULL_WORKBOOK_URL,
    "https://docs.google.com/spreadsheets/d/1b_N7FjwOKSOphXd5m0w-XxfeZcESebjnxFd4aX_Gzfk/edit?gid=2133243036",
    "https://docs.google.com/document/d/1uIkg7y2AoZMvWAZbvG9b2uMw-k7Gf1j8wQXf7Z2GML4/edit",
]

GENRES = [
    ("FMV / Interactive Story", "fmv_visual_novel"),
    ("Visual Novel", "visual_novel"),
    ("RPG / JRPG", "rpg"),
    ("Action / Adventure", "action_adventure"),
    ("Platformer", "platformer"),
    ("Horror Platformer · Little Nightmares style", "horror_platformer"),
    ("Puzzle", "puzzle"),
    ("Strategy / Simulation", "strategy_simulation"),
    ("Horror / Survival", "horror_survival"),
    ("Racing / Sports", "racing_sports"),
    ("Other", "other"),
]


class _WorkflowTask(QThread):
    completed = Signal(str, object)
    failed = Signal(str)

    def __init__(
        self, service: ComfyUIService, workflow_path: Path, image_path: Path, profile: str
    ) -> None:
        super().__init__()
        self._service = service
        self._workflow_path = workflow_path
        self._image_path = image_path
        self._profile = profile

    def run(self) -> None:
        try:
            prompt_id = self._service.queue_workflow(self._workflow_path, self._image_path)
            result = self._service.wait_for_workflow(prompt_id)
            result["ugaf_output_artifacts"] = self._service.collect_workflow_output_artifacts(
                prompt_id, result, self._profile
            )
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(prompt_id, result)


class _SourceImportTask(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self, profile: str, game_name: str, game_type: str, source_urls: list[str]
    ) -> None:
        super().__init__()
        self._profile = profile
        self._game_name = game_name
        self._game_type = game_type
        self._source_urls = source_urls

    def run(self) -> None:
        try:
            db = QADatabase.for_profile(self._profile)
            results = []
            for source_url in self._source_urls:
                if "/document/d/" in source_url:
                    result = import_source_document(
                        db,
                        profile=self._profile,
                        game_name=self._game_name,
                        game_type=self._game_type,
                        source_url=source_url,
                    )
                else:
                    result = import_source_workbook(
                        db,
                        profile=self._profile,
                        game_name=self._game_name,
                        game_type=self._game_type,
                        source_url=source_url,
                    )
                results.append(result)
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(results)


class StudioFrameworkWidget(QWidget):
    """Game-scoped image analysis, ComfyUI handoff, and timeline evidence."""

    def __init__(self) -> None:
        super().__init__()
        self._image_path: Path | None = None
        self._service = ComfyUIService()
        self._games = QComboBox()
        self._genre = QComboBox()
        for label, key in GENRES:
            self._genre.addItem(label, key)
        self._title = QLineEdit()
        self._title.setPlaceholderText("ชื่อเกม เช่น HighSchoolBloodDemo")
        self._scene = QLineEdit()
        self._scene.setPlaceholderText("Scene / Chapter / Level (ไม่บังคับ)")
        self._expected = QLineEdit()
        self._expected.setPlaceholderText("ข้อความที่คาดว่าจะเห็น เช่น Go Left")
        self._comfy_url = QLineEdit("http://127.0.0.1:8188")
        self._workflow = QLineEdit()
        self._workflow_purpose = QComboBox()
        self._workflow_purpose.addItem("UI Mockup", "ui_mockup")
        self._workflow_purpose.addItem("Screen Annotation", "screen_annotation")
        self._workflow_purpose.addItem("Visual Review", "visual_review")
        self._image = QLabel("เลือกรูปหน้าจอเกมเพื่อเริ่มวิเคราะห์")
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setMinimumSize(480, 270)
        self._image.setStyleSheet("background:#101c24;border:1px dashed #56717c;color:#a9bdc5")
        self._result = QPlainTextEdit()
        self._result.setReadOnly(True)
        self._evidence = QListWidget()
        self._timeline_nodes = QListWidget()
        self._workflow_task: _WorkflowTask | None = None
        self._source_task: _SourceImportTask | None = None
        self._source_url = QLineEdit(DEMO_WORKBOOK_URL)
        self._source_list = QListWidget()
        self._conflict_list = QListWidget()
        self._memory_key = QLineEdit()
        self._memory_key.setPlaceholderText("key เช่น choice.timeout_behavior")
        self._memory_value = QLineEdit()
        self._memory_value.setPlaceholderText("ข้อเท็จจริงหรือสิ่งที่ QA ควรจำ")
        self._memory_list = QListWidget()
        self._memory_search = QLineEdit()
        self._memory_search.setPlaceholderText("ค้นหา flow, subtitle, testcase, run หรือ feedback")
        self._memory_search_results = QListWidget()
        self._build_ui()
        self._games.currentIndexChanged.connect(self._on_profile_changed)
        self._refresh_games()

    @property
    def profile(self) -> str:
        return str(self._games.currentData() or "")

    def _build_ui(self) -> None:
        heading = QLabel("Studio Framework")
        heading.setStyleSheet("font-size:24px;font-weight:700;color:#e4f1f1")
        intro = QLabel(
            "วิเคราะห์ภาพเกม เก็บหลักฐานผูกกับ Story Timeline และแยกฐานข้อมูลตามเกม/แนวเกม "
            "ComfyUI รับภาพต่อผ่าน workflow API ที่เลือกไว้"
        )
        intro.setWordWrap(True)
        game_form = QFormLayout()
        game_form.addRow("เกมที่กำลังทดสอบ", self._games)
        game_form.addRow("ชื่อเกมใหม่", self._title)
        game_form.addRow("ประเภทเกม", self._genre)
        add_game = QPushButton("สร้างโปรไฟล์เกม")
        add_game.clicked.connect(self._add_game)
        game_form.addRow("", add_game)

        source_row = QHBoxLayout()
        choose = QPushButton("เลือกรูป / Screenshot")
        choose.clicked.connect(self._choose_image)
        source_row.addWidget(choose)
        self._image_name = QLabel("ยังไม่ได้เลือกรูป")
        source_row.addWidget(self._image_name, 1)

        analyze = QPushButton("วิเคราะห์ภาพและบันทึก Timeline")
        analyze.clicked.connect(self._analyze)
        self._queue_button = QPushButton("วิเคราะห์ภาพด้วย ComfyUI workflow")
        self._queue_button.clicked.connect(self._queue_comfy)

        form = QFormLayout()
        form.addRow("Scene / Chapter / Level", self._scene)
        form.addRow("ข้อความที่ต้องตรวจ", self._expected)
        form.addRow("ComfyUI URL", self._comfy_url)
        form.addRow("API workflow JSON", self._workflow)
        form.addRow("Workflow purpose", self._workflow_purpose)
        workflow_browse = QPushButton("เลือก Workflow")
        workflow_browse.clicked.connect(self._choose_workflow)
        form.addRow("", workflow_browse)
        sample_workflow = QPushButton("ใช้ Workflow ตัวอย่าง SDXL")
        sample_workflow.clicked.connect(self._load_sample_workflow)
        form.addRow("", sample_workflow)
        ta_mockup_workflow = QPushButton("ใช้ Workflow ตัวอย่าง TA Optimize Mockup")
        ta_mockup_workflow.clicked.connect(self._load_ta_optimize_workflow)
        form.addRow("", ta_mockup_workflow)
        register_workflow = QPushButton("ตรวจและลงทะเบียน Workflow ที่ตรวจทานแล้ว")
        register_workflow.clicked.connect(self._register_comfy_workflow)
        form.addRow("", register_workflow)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("หลักฐานภาพ"))
        left_layout.addLayout(source_row)
        left_layout.addWidget(self._image, 2)
        left_layout.addLayout(form)
        actions = QHBoxLayout()
        actions.addWidget(analyze)
        actions.addWidget(self._queue_button)
        left_layout.addLayout(actions)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("ผลวิเคราะห์ / Feedback"))
        right_layout.addWidget(self._result, 2)
        export = QPushButton("ส่งออกรายงานหลักฐาน")
        export.clicked.connect(self._export_report)
        right_layout.addWidget(export)
        right_layout.addWidget(QLabel("Story Timeline ของเกมนี้"))
        right_layout.addWidget(self._timeline_nodes, 1)
        right_layout.addWidget(QLabel("ภาพและผลวิเคราะห์"))
        right_layout.addWidget(self._evidence, 2)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        source_note = QLabel(
            "นำเข้าชีตทั้งหมดรวมถึง hyperlink โดยเก็บเป็น read-only snapshot แยกตามโปรไฟล์เกม "
            "วาง URL ของชีตหรือ Google Docs แล้วกดนำเข้า/อัปเดต"
        )
        source_note.setWordWrap(True)
        source_layout.addWidget(source_note)
        import_row = QHBoxLayout()
        import_row.addWidget(self._source_url, 1)
        self._import_button = QPushButton("นำเข้าข้อมูลทั้งหมด")
        self._import_button.clicked.connect(self._import_source)
        import_row.addWidget(self._import_button)
        source_layout.addLayout(import_row)
        refresh_all = QPushButton("อัปเดตทุกชีตและเอกสารที่เชื่อมกับเกมนี้")
        refresh_all.clicked.connect(self._sync_known_sources)
        source_layout.addWidget(refresh_all)
        source_layout.addWidget(QLabel("ชีต/เอกสารที่เก็บไว้ พร้อมจำนวนแถวและลิงก์"))
        source_layout.addWidget(self._source_list, 2)
        source_layout.addWidget(QLabel("Localization conflicts ที่ต้องตรวจ พร้อมแถวต้นทาง"))
        source_layout.addWidget(self._conflict_list, 1)
        memory_form = QFormLayout()
        memory_form.addRow("Memory key", self._memory_key)
        memory_form.addRow("สิ่งที่ควรจำ", self._memory_value)
        memory_save = QPushButton("บันทึก Memory ของเกมนี้")
        memory_save.clicked.connect(self._save_memory)
        source_layout.addLayout(memory_form)
        source_layout.addWidget(memory_save)
        source_layout.addWidget(QLabel("Game Memory ที่ผู้ช่วย QA เรียกดูได้"))
        source_layout.addWidget(self._memory_list, 2)
        search_row = QHBoxLayout()
        search_row.addWidget(self._memory_search, 1)
        memory_search = QPushButton("ค้น Memory")
        memory_search.clicked.connect(self._search_memory)
        search_row.addWidget(memory_search)
        source_layout.addLayout(search_row)
        source_layout.addWidget(self._memory_search_results, 1)
        export_vault = QPushButton("สร้าง / อัปเดต Obsidian Vault ของเกมนี้")
        export_vault.clicked.connect(self._export_memory_vault)
        source_layout.addWidget(export_vault)

        work_tabs = QTabWidget()
        work_tabs.addTab(split, "Vision / Story Timeline")
        work_tabs.addTab(source_page, "Source Sheets / Memory")

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(intro)
        layout.addLayout(game_form)
        layout.addWidget(work_tabs, 1)

    def _refresh_games(self) -> None:
        selected = self.profile
        self._games.clear()
        databases = sorted(PROFILE_DB_DIR.glob("qa_*.sqlite3")) if PROFILE_DB_DIR.exists() else []
        records: dict[str, dict[str, str]] = {}
        for path in databases:
            for record in QADatabase(path).list_games():
                records[record["profile"]] = record
        for item in records.values():
            self._games.addItem(f"{item['display_name']}  ·  {item['game_type']}", item["profile"])
        row = self._games.findData(selected)
        if row >= 0:
            self._games.setCurrentIndex(row)
        self._refresh_evidence()

    def _on_profile_changed(self, *_args: object) -> None:
        if self.profile == "highschoolblood-demo":
            self._source_url.setText(DEMO_WORKBOOK_URL)
        elif self.profile == "highschoolblood-full":
            self._source_url.setText(FULL_WORKBOOK_URL)
        self._refresh_evidence()

    def _import_source(self) -> None:
        if self._source_task is not None and self._source_task.isRunning():
            return
        if not self.profile:
            QMessageBox.information(self, "นำเข้าข้อมูล", "เลือกหรือสร้างโปรไฟล์เกมก่อน")
            return
        game_name = self._games.currentText().split("  ·  ", maxsplit=1)[0]
        database = QADatabase.for_profile(self.profile)
        records = database.list_games()
        selected = next((record for record in records if record["profile"] == self.profile), {})
        game_type = selected.get("game_type", str(self._genre.currentData()))
        url = self._source_url.text().strip()
        if not url:
            QMessageBox.information(self, "นำเข้าข้อมูล", "วาง URL ของ Google Sheets หรือ Google Docs")
            return
        self._start_source_import(game_name, game_type, [url])

    def _sync_known_sources(self) -> None:
        if self.profile == "highschoolblood-demo":
            sources = DEMO_SOURCES
        elif self.profile == "highschoolblood-full":
            sources = FULL_SOURCES
        else:
            QMessageBox.information(
                self, "อัปเดตทุกแหล่ง", "โปรไฟล์เกมนี้ยังไม่มีชุดแหล่งข้อมูลที่ตั้งค่าไว้ ใช้ URL ด้านบนได้"
            )
            return
        game_name = self._games.currentText().split("  ·  ", maxsplit=1)[0]
        records = QADatabase.for_profile(self.profile).list_games()
        game_type = next(
            (record["game_type"] for record in records if record["profile"] == self.profile),
            str(self._genre.currentData()),
        )
        self._start_source_import(game_name, game_type, sources)

    def _start_source_import(self, game_name: str, game_type: str, urls: list[str]) -> None:
        if self._source_task is not None and self._source_task.isRunning():
            return
        self._source_task = _SourceImportTask(self.profile, game_name, game_type, urls)
        self._source_task.completed.connect(self._source_imported)
        self._source_task.failed.connect(self._source_import_failed)
        self._source_task.finished.connect(lambda: self._import_button.setEnabled(True))
        self._import_button.setEnabled(False)
        self._source_list.addItem("กำลังดาวน์โหลดและจัดทำ index…")
        self._source_task.start()

    def _source_imported(self, results: list[dict[str, Any]]) -> None:
        self._refresh_evidence()
        details = "\n".join(
            f"{item['source_name']}: {item.get('sheet_count', item.get('lines', 0))} tabs/lines, "
            f"{item.get('nonempty_rows', 0)} rows, {item.get('hyperlinks', 0)} links, "
            f"{item.get('subtitle_cues_imported', 0)} subtitles, "
            f"{item.get('choices_imported', 0)} choices, "
            f"{item.get('testcases_imported', 0)} testcases, "
            f"{item.get('localization_conflicts', 0)} localization conflicts\n"
            f"Archive: {item.get('archive_path', '')}"
            for item in results
        )
        if results:
            details += f"\n\nIndex: {results[-1].get('index_path', '')}"
        QMessageBox.information(self, "อัปเดต Source / Memory แล้ว", details)

    def _source_import_failed(self, message: str) -> None:
        QMessageBox.warning(self, "นำเข้าไม่สำเร็จ", message)

    def _save_memory(self) -> None:
        key = self._memory_key.text().strip()
        value = self._memory_value.text().strip()
        if not self.profile or not key or not value:
            QMessageBox.information(self, "บันทึก Memory", "เลือกเกมและกรอก key กับสิ่งที่ต้องจำ")
            return
        QADatabase.for_profile(self.profile).store_game_memory(
            self.profile, key, "manual", value, source="Studio Framework"
        )
        self._memory_key.clear()
        self._memory_value.clear()
        self._refresh_evidence()

    def _search_memory(self) -> None:
        query = self._memory_search.text().strip()
        if not self.profile or not query:
            return
        self._memory_search_results.clear()
        try:
            results = search_game_memory(QADatabase.for_profile(self.profile), self.profile, query)
        except (OSError, sqlite3.Error, ValueError) as exc:
            QMessageBox.warning(self, "ค้น Memory ไม่สำเร็จ", str(exc))
            return
        for result in results:
            self._memory_search_results.addItem(
                f"{result['entity_type']} · {result['title']} · {result['snippet']}"
            )
            self._memory_search_results.item(self._memory_search_results.count() - 1).setToolTip(
                json.dumps(result["citation"], ensure_ascii=False, indent=2)
            )
        if not results:
            self._memory_search_results.addItem("ไม่พบข้อมูลใน memory ของเกมนี้")

    def _export_memory_vault(self) -> None:
        if not self.profile:
            QMessageBox.information(self, "Obsidian Vault", "เลือกโปรไฟล์เกมก่อน")
            return
        try:
            result = export_game_vault(QADatabase.for_profile(self.profile), self.profile)
        except (OSError, sqlite3.Error, ValueError) as exc:
            QMessageBox.warning(self, "สร้าง Vault ไม่สำเร็จ", str(exc))
            return
        QMessageBox.information(
            self,
            "Obsidian Vault พร้อมแล้ว",
            f"สร้าง Markdown {result['markdown_pages']} หน้า\n"
            f"ค้นได้ {result['search_documents']} รายการ\n\n{result['vault_path']}\n\n"
            "ไฟล์นี้เป็น projection แบบอ่านอย่างเดียว การแก้ Markdown จะไม่เขียนกลับฐานข้อมูลหรือชีต",
        )

    def _add_game(self) -> None:
        title = self._title.text().strip()
        profile = sanitize_profile_key(title)
        if not title:
            QMessageBox.information(self, "สร้างโปรไฟล์", "กรอกชื่อเกมก่อน")
            return
        db = QADatabase.for_profile(profile)
        db.register_game(profile, title, str(self._genre.currentData()))
        if db.load_story_project(profile) is None:
            db.save_story_project(
                profile,
                {
                    "title": title,
                    "source_summary": {"created_locally": True},
                    "required_locales": [],
                    "conflicts": [],
                    "patch_items": [],
                    "scenes": {},
                },
            )
        self._title.clear()
        self._refresh_games()
        index = self._games.findData(profile)
        if index >= 0:
            self._games.setCurrentIndex(index)

    def _choose_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "เลือกรูปหลักฐาน", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if filename:
            self._image_path = Path(filename)
            self._image_name.setText(self._image_path.name)
            self._image.setPixmap(
                QPixmap(filename).scaled(
                    self._image.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def _choose_workflow(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "เลือก ComfyUI API workflow", "", "JSON (*.json)"
        )
        if filename:
            self._workflow.setText(filename)

    def _load_sample_workflow(self) -> None:
        """Copy the bundled SDXL image-review workflow to the writable data folder."""
        self._copy_bundled_workflow("comfyui_sdxl_image_review_api.json")

    def _load_ta_optimize_workflow(self) -> None:
        """Copy the bundled Unreal performance dashboard concept workflow."""
        self._copy_bundled_workflow("ugaf_ta_optimize_mockup_api.json")

    def _copy_bundled_workflow(self, filename: str) -> None:
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
        source = bundle_root / "qa_framework" / "workflows" / filename
        destination = writable_path("data", "comfyui", "workflows", filename)
        if not source.is_file():
            QMessageBox.warning(self, "ComfyUI", "ไม่พบ Workflow ตัวอย่างที่ติดตั้งมากับโปรแกรม")
            return
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(source, destination)
        except OSError as exc:
            QMessageBox.warning(self, "ComfyUI", f"คัดลอก Workflow ตัวอย่างไม่สำเร็จ: {exc}")
            return
        self._workflow.setText(str(destination))
        self._result.setPlainText(
            "โหลด Workflow ตัวอย่างแล้ว ตรวจทานและลงทะเบียนก่อนใช้งาน "
            "โดยต้องมี SDXL base checkpoint ใน ComfyUI "
            "ผลภาพเป็นแนวทางออกแบบและยังไม่ใช่ผล QA"
        )

    def _register_comfy_workflow(self) -> None:
        filename = self._workflow.text().strip()
        if not filename:
            QMessageBox.information(self, "ComfyUI", "เลือก API workflow JSON ก่อน")
            return
        try:
            self._service.base_url = self._comfy_url.text().strip()
            registered = self._service.register_workflow(
                Path(filename), str(self._workflow_purpose.currentData())
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "ลงทะเบียน Workflow ไม่สำเร็จ", str(exc))
            return
        self._result.setPlainText(json.dumps(registered, ensure_ascii=False, indent=2))

    def _analyze(self) -> None:
        if not self._image_path or not self.profile:
            QMessageBox.information(self, "วิเคราะห์ภาพ", "เลือกเกมและรูปหลักฐานก่อน")
            return
        try:
            self._service.base_url = self._comfy_url.text().strip()
            result = self._service.analyze_image(self._image_path, self._expected.text())
            db = QADatabase.for_profile(self.profile)
            evidence_id = db.save_story_evidence(
                self.profile,
                self._scene.text().strip(),
                "image_analysis",
                str(self._image_path.resolve()),
                result,
            )
            expected = result.get("expected_text")
            check = result.get("expected_text_found")
            if expected:
                db.record_feedback(
                    evidence_id,
                    "visual_assertion",
                    "PASS" if check else "FAIL",
                    case_id=self._scene.text().strip(),
                )
            self._result.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
            self._refresh_evidence()
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "วิเคราะห์ภาพไม่สำเร็จ", str(exc))

    def _queue_comfy(self) -> None:
        if self._workflow_task is not None and self._workflow_task.isRunning():
            return
        if not self.profile or not self._image_path or not self._workflow.text().strip():
            QMessageBox.information(self, "ComfyUI", "เลือกเกม รูป และ API workflow JSON ก่อน")
            return
        try:
            self._service.base_url = self._comfy_url.text().strip()
            registered = self._service.get_registered_workflow(Path(self._workflow.text()))
            inspected = self._service.inspect_workflow(Path(self._workflow.text()))
            if not registered or registered.get("sha256") != inspected.get("sha256"):
                QMessageBox.information(self, "ComfyUI", "ตรวจทานและลงทะเบียน Workflow นี้ก่อนใช้งาน")
                return
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "ComfyUI", str(exc))
            return
        self._workflow_task = _WorkflowTask(
            self._service, Path(self._workflow.text()), self._image_path, self.profile
        )
        self._workflow_task.completed.connect(self._comfy_completed)
        self._workflow_task.failed.connect(self._comfy_failed)
        self._workflow_task.finished.connect(lambda: self._queue_button.setEnabled(True))
        self._queue_button.setEnabled(False)
        self._result.setPlainText("กำลังส่งภาพให้ ComfyUI และรอผล workflow…")
        self._workflow_task.start()

    def _comfy_completed(self, prompt_id: str, result: dict[str, Any]) -> None:
        outputs = result.get("outputs", {}) if isinstance(result, dict) else {}
        record = {
            "prompt_id": prompt_id,
            "workflow": self._service.get_registered_workflow(Path(self._workflow.text())),
            "outputs": outputs,
            "output_artifacts": result.get("ugaf_output_artifacts", []),
            "qa_status": "UNASSERTED",
        }
        QADatabase.for_profile(self.profile).save_story_evidence(
            self.profile,
            self._scene.text().strip(),
            "comfyui_workflow",
            str(self._image_path.resolve()) if self._image_path else "",
            record,
        )
        self._result.setPlainText(json.dumps(record, ensure_ascii=False, indent=2))
        self._refresh_evidence()

    def _comfy_failed(self, message: str) -> None:
        self._result.setPlainText(f"ComfyUI workflow ไม่สำเร็จ\n{message}")

    def _refresh_evidence(self) -> None:
        self._evidence.clear()
        self._timeline_nodes.clear()
        self._source_list.clear()
        self._conflict_list.clear()
        self._memory_list.clear()
        self._memory_search_results.clear()
        if not self.profile:
            return
        try:
            db = QADatabase.for_profile(self.profile)
            for scene in db.list_story_scenes(self.profile):
                self._timeline_nodes.addItem(
                    f"{scene['scene_order'] + 1:03}  {scene['scene_id']}  ·  {scene['group_name']}"
                )
            for item in db.list_story_evidence(self.profile):
                scene = item["scene_id"] or "ไม่ระบุซีน"
                result = item["result"]
                detected = re.sub(r"\s+", " ", result.get("detected_text", ""))[:100]
                self._evidence.addItem(f"{scene} · {item['evidence_type']} · {detected}")
            sheets = db.list_source_sheets(self.profile)
            seen_revisions: set[tuple[str, str]] = set()
            for sheet in sheets:
                revision_hash = str(sheet.get("revision_hash") or "")
                self._source_list.addItem(
                    f"{sheet['source_name']} · {sheet['sheet_name']} · "
                    f"{sheet['row_count']} rows · {len(sheet['hyperlinks'])} links · "
                    f"rev {revision_hash[:10] or 'unknown'}"
                )
                revision_id = (str(sheet["source_id"]), revision_hash)
                if not revision_hash or revision_id in seen_revisions:
                    continue
                seen_revisions.add(revision_id)
                candidates = db.list_source_localization_candidates(
                    self.profile, source_id=revision_id[0], revision_hash=revision_hash
                )
                grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
                for candidate in candidates:
                    if candidate["has_conflict"]:
                        grouped.setdefault(
                            (candidate["entity_type"], candidate["entity_key"]), []
                        ).append(candidate)
                for (entity_type, _entity_key), variants in grouped.items():
                    first = variants[0]["payload"]
                    label = first.get("key", "unknown key")
                    scene = first.get("scene_id", "unknown scene")
                    detail = "\n".join(
                        f"{locale}={text!r} ({item['sheet_name']}!{item['row_number']})"
                        for item in variants
                        for locale, text in item["payload"].get("translations", {}).items()
                        if locale in item["conflicting_locales"]
                    )
                    self._conflict_list.addItem(
                        f"{sheet['source_name']} · {scene} · {entity_type} {label} · "
                        f"{len(variants)} candidates"
                    )
                    self._conflict_list.item(self._conflict_list.count() - 1).setToolTip(detail)
            for item in db.list_game_memory(self.profile):
                value = json.dumps(item["value"], ensure_ascii=False)
                self._memory_list.addItem(
                    f"{item['category']} · {item['memory_key']} = {value[:220]}"
                )
        except OSError:
            return

    def _export_report(self) -> None:
        if not self.profile:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "ส่งออกรายงาน", "vision-report.json", "JSON (*.json)"
        )
        if not filename:
            return
        db = QADatabase.for_profile(self.profile)
        payload: dict[str, Any] = {
            "profile": self.profile,
            "game": next(
                (
                    self._games.itemText(i)
                    for i in range(self._games.count())
                    if self._games.itemData(i) == self.profile
                ),
                self.profile,
            ),
            "evidence": db.list_story_evidence(self.profile),
        }
        Path(filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        QMessageBox.information(self, "ส่งออกรายงานแล้ว", filename)
