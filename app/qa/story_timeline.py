from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from openpyxl import load_workbook

from app.database.database import QADatabase


_CASE_SNAPSHOT = (
    Path(__file__).resolve().parents[2]
    / "qa_framework"
    / "testcases"
    / "highschool_blood_cases.json"
)
_SUBTITLE_SHEET_PRIORITY = {
    "Luna Subtitle": 0,
    "ชีต11": 1,
    "Subtitles_Demo": 2,
    "Subtitles": 3,
}
_CHOICE_SHEET_PRIORITY = {"Luna Choice": 0, "ชีต10": 1}


@dataclass
class StoryCue:
    key: str
    scene_id: str
    start: float
    end: float
    translations: dict[str, str]
    source_sheet: str
    source_row: int = 0


@dataclass
class StoryChoice:
    key: str
    scene_id: str
    translations: dict[str, str]
    source_sheet: str
    source_row: int = 0


@dataclass
class StoryScene:
    scene_id: str
    group: str
    order: int
    cases: list[dict[str, Any]] = field(default_factory=list)
    cues: list[StoryCue] = field(default_factory=list)
    choices: list[StoryChoice] = field(default_factory=list)
    outgoing: list[dict[str, str]] = field(default_factory=list)


@dataclass
class PatchItem:
    version: str
    build_id: str
    category: str
    text: str
    scene_ids: list[str] = field(default_factory=list)
    source: str = "manual"


@dataclass
class TimelineFinding:
    severity: str
    code: str
    message: str
    scene_id: str = ""


@dataclass
class StoryTimelineProject:
    title: str = "HighSchool Blood"
    scenes: dict[str, StoryScene] = field(default_factory=dict)
    patch_items: list[PatchItem] = field(default_factory=list)
    source_summary: dict[str, Any] = field(default_factory=dict)
    required_locales: list[str] = field(default_factory=lambda: ["th", "en"])
    conflicts: list[str] = field(default_factory=list)


class StoryTimelineService:
    """Read-only source import and local story timeline project operations."""

    def __init__(
        self,
        case_snapshot: Path = _CASE_SNAPSHOT,
        database: QADatabase | None = None,
        database_profile: str = "highschoolblood-demo",
    ) -> None:
        self.database = database or QADatabase.for_profile(database_profile)
        self.database_profile = database_profile
        self.project = StoryTimelineProject()
        self._load_cases(case_snapshot)
        self.database.register_game(
            database_profile, self.project.title, "fmv_visual_novel", "5173380"
        )
        self.database.seed_testcases(database_profile, self._source_cases)
        saved_project = self.database.load_story_project(database_profile)
        if saved_project is not None:
            self._load_project_data(saved_project)
        else:
            self._persist_database()

    def _load_cases(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._source_cases = list(data.get("cases", []))
        for record in self._source_cases:
            scene_id = str(record.get("scene_id", "")).strip()
            if not scene_id:
                continue
            scene = self.project.scenes.get(scene_id)
            if scene is None:
                scene = StoryScene(
                    scene_id=scene_id,
                    group=str(record.get("group", "Unassigned")),
                    order=len(self.project.scenes),
                )
                self.project.scenes[scene_id] = scene
            scene.cases.append(record)
        self.project.source_summary["qa_cases"] = len(data.get("cases", []))
        self.project.source_summary["scene_ids"] = len(self.project.scenes)
        self.project.source_summary["qa_statuses"] = data.get("row_level_summary", {}).get(
            "statuses", {}
        )

    def _persist_database(self) -> None:
        payload = _project_to_dict(self.project)
        self.database.save_story_project(self.database_profile, payload)

    def import_patch_note(self, source: str) -> int:
        if "docs.google.com/spreadsheets/" in source or Path(source).suffix.casefold() == ".xlsx":
            workbook_data, source_name = _read_workbook_source(source)
            parsed = _parse_patch_workbook(workbook_data, source_name, tuple(self.project.scenes))
            self.project.patch_items = [
                item for item in self.project.patch_items if item.source != source_name
            ] + parsed
        else:
            content, source_name = _read_text_source(source)
            parsed = parse_patch_note(content, tuple(self.project.scenes))
            self.project.patch_items = [
                item for item in self.project.patch_items if item.source != source_name
            ] + [
                PatchItem(item.version, item.build_id, item.category, item.text, item.scene_ids, source_name)
                for item in parsed
            ]
        self.project.source_summary["patch_note"] = source_name
        self.project.source_summary["patch_items"] = len(self.project.patch_items)
        self.project.source_summary["patch_versions"] = list(
            dict.fromkeys(item.version for item in self.project.patch_items if item.version)
        )
        self._persist_database()
        return len(parsed)

    def add_patch_note(
        self,
        *,
        version: str,
        build_id: str,
        category: str,
        text: str,
        scene_ids: list[str] | None = None,
    ) -> None:
        note = text.strip()
        if not version.strip() or not note:
            raise ValueError("Version and patch note are required.")
        references = [value.strip() for value in (scene_ids or []) if value.strip()]
        unknown = sorted(set(references) - set(self.project.scenes))
        if unknown:
            raise ValueError(f"Unknown scene ID(s): {', '.join(unknown[:5])}")
        self.project.patch_items.append(
            PatchItem(version.strip(), build_id.strip(), category.strip() or "release", note, references)
        )
        self.project.source_summary["patch_items"] = len(self.project.patch_items)
        self.project.source_summary["patch_versions"] = list(
            dict.fromkeys(item.version for item in self.project.patch_items if item.version)
        )
        self._persist_database()

    def import_localization(self, source: str) -> int:
        workbook_data, source_name = _read_workbook_source(source)
        candidates: dict[tuple[str, str, float, float], list[StoryCue]] = defaultdict(list)
        choice_candidates: dict[str, list[StoryChoice]] = defaultdict(list)
        sheet_counts: Counter[str] = Counter()
        workbook = load_workbook(workbook_data, read_only=True, data_only=True)
        try:
            for worksheet in workbook.worksheets:
                rows = worksheet.iter_rows(values_only=True)
                header_row = next(rows, None)
                if header_row is None:
                    continue
                headers = [str(value).strip() if value is not None else "" for value in header_row]
                header_map = {name: index for index, name in enumerate(headers) if name}
                if {"Key", "Time_Start", "Time_End"} <= header_map.keys():
                    for source_row, row in enumerate(rows, start=2):
                        cue = _parse_cue_row(worksheet.title, header_map, row, source_row)
                        if cue is None:
                            continue
                        identity = (cue.scene_id, cue.key, cue.start, cue.end)
                        candidates[identity].append(cue)
                        sheet_counts[worksheet.title] += 1
                elif "Key" in header_map and "lang-en" in header_map:
                    for source_row, row in enumerate(rows, start=2):
                        choice = _parse_choice_row(worksheet.title, header_map, row, source_row)
                        if choice is None:
                            continue
                        choice_candidates[choice.key].append(choice)
                        sheet_counts[worksheet.title] += 1
        finally:
            workbook.close()

        self.project.conflicts.clear()
        for scene in self.project.scenes.values():
            scene.cues.clear()
            scene.choices.clear()

        for identity, variants in candidates.items():
            ordered = sorted(variants, key=lambda cue: _SUBTITLE_SHEET_PRIORITY.get(cue.source_sheet, 9))
            preferred = ordered[0]
            for alternate in ordered[1:]:
                if _translations_conflict(preferred.translations, alternate.translations):
                    self.project.conflicts.append(
                        f"Subtitle key {preferred.key} differs between "
                        f"{preferred.source_sheet} and {alternate.source_sheet}."
                    )
                    preferred = _merge_translations(preferred, alternate)
            scene = self.project.scenes.get(preferred.scene_id)
            if scene is None:
                scene = StoryScene(
                    scene_id=preferred.scene_id,
                    group="Localization only",
                    order=len(self.project.scenes),
                )
                self.project.scenes[scene.scene_id] = scene
            scene.cues.append(preferred)

        for variants in choice_candidates.values():
            ordered = sorted(variants, key=lambda choice: _CHOICE_SHEET_PRIORITY.get(choice.source_sheet, 9))
            preferred = ordered[0]
            for alternate in ordered[1:]:
                if _translations_conflict(preferred.translations, alternate.translations):
                    self.project.conflicts.append(
                        f"Choice key {preferred.key} differs between "
                        f"{preferred.source_sheet} and {alternate.source_sheet}."
                    )
                    preferred = _merge_choice_translations(preferred, alternate)
            scene = self.project.scenes.get(preferred.scene_id)
            if scene is None:
                scene = StoryScene(
                    scene_id=preferred.scene_id,
                    group="Localization only",
                    order=len(self.project.scenes),
                )
                self.project.scenes[scene.scene_id] = scene
            scene.choices.append(preferred)

        for scene in self.project.scenes.values():
            scene.cues.sort(key=lambda cue: (cue.start, cue.end, cue.key))
            scene.choices.sort(key=lambda choice: choice.key)

        self.project.source_summary["localization"] = source_name
        self.project.source_summary["localization_sheets"] = dict(sheet_counts)
        self.project.source_summary["subtitle_cues"] = sum(
            len(scene.cues) for scene in self.project.scenes.values()
        )
        self.project.source_summary["choice_keys"] = sum(
            len(scene.choices) for scene in self.project.scenes.values()
        )
        self.project.source_summary["localization_conflicts"] = len(self.project.conflicts)
        self._persist_database()
        return self.project.source_summary["subtitle_cues"]

    def add_link(self, source_scene: str, target_scene: str, choice_key: str = "") -> None:
        if source_scene not in self.project.scenes or target_scene not in self.project.scenes:
            raise ValueError("Both source and destination scenes must exist in the timeline.")
        if source_scene == target_scene:
            raise ValueError("A scene cannot link to itself.")
        scene = self.project.scenes[source_scene]
        link = {"target": target_scene, "choice_key": choice_key.strip()}
        if link not in scene.outgoing:
            scene.outgoing.append(link)
            self._persist_database()

    def remove_link(self, source_scene: str, index: int) -> None:
        self.project.scenes[source_scene].outgoing.pop(index)
        self._persist_database()

    def audit(self) -> list[TimelineFinding]:
        findings = [
            TimelineFinding("warning", "source-conflict", conflict)
            for conflict in self.project.conflicts
        ]
        scene_ids = set(self.project.scenes)
        for scene in self.project.scenes.values():
            previous: StoryCue | None = None
            for cue in scene.cues:
                for locale in self.project.required_locales:
                    if not cue.translations.get(locale, "").strip():
                        findings.append(
                            TimelineFinding(
                                "warning",
                                "missing-localization",
                                f"{cue.key}: missing {locale} text.",
                                scene.scene_id,
                            )
                        )
                if cue.start < 0 or cue.end <= cue.start:
                    findings.append(
                        TimelineFinding(
                            "error",
                            "invalid-cue-time",
                            f"{cue.key}: invalid range {cue.start:.3f}–{cue.end:.3f} seconds.",
                            scene.scene_id,
                        )
                    )
                if previous is not None and cue.start < previous.end:
                    findings.append(
                        TimelineFinding(
                            "warning",
                            "overlapping-cues",
                            f"{previous.key} overlaps {cue.key}.",
                            scene.scene_id,
                        )
                    )
                previous = cue
            for link in scene.outgoing:
                if link["target"] not in scene_ids:
                    findings.append(
                        TimelineFinding(
                            "error",
                            "broken-link",
                            f"Link target {link['target']} is missing.",
                            scene.scene_id,
                        )
                    )
        for item in self.project.patch_items:
            for scene_id in item.scene_ids:
                if scene_id not in scene_ids:
                    findings.append(
                        TimelineFinding(
                            "warning",
                            "unknown-patch-scene",
                            f"Patch note references unknown scene {scene_id}.",
                        )
                    )
        return findings

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _project_to_dict(self.project)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._persist_database()

    def load(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._load_project_data(data)
        self._persist_database()

    def _load_project_data(self, data: dict[str, Any]) -> None:
        scenes: dict[str, StoryScene] = {}
        for scene_id, raw in data.get("scenes", {}).items():
            scenes[scene_id] = StoryScene(
                scene_id=scene_id,
                group=raw.get("group", "Unassigned"),
                order=int(raw.get("order", len(scenes))),
                cases=list(raw.get("cases", [])),
                cues=[StoryCue(**cue) for cue in raw.get("cues", [])],
                choices=[StoryChoice(**choice) for choice in raw.get("choices", [])],
                outgoing=list(raw.get("outgoing", [])),
            )
        self.project = StoryTimelineProject(
            title=data.get("title", "HighSchool Blood"),
            scenes=scenes,
            patch_items=[PatchItem(**item) for item in data.get("patch_items", [])],
            source_summary=dict(data.get("source_summary", {})),
            required_locales=list(data.get("required_locales", ["th", "en"])),
            conflicts=list(data.get("conflicts", [])),
        )


def parse_patch_note(text: str, known_scenes: tuple[str, ...] = ()) -> list[PatchItem]:
    items: list[PatchItem] = []
    version = ""
    build_id = ""
    category = "release"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        version_match = re.search(r"\b\d+\.\d+\.\d+(?:[-\w.]*)", line)
        if version_match:
            version = version_match.group(0)
            category = "release"
        build_match = re.search(r"Build\s*ID\s*[:：]\s*(\S+)", line, re.IGNORECASE)
        if build_match:
            build_id = build_match.group(1)
        if not line:
            continue
        lowered = line.casefold()
        if "backlog" in lowered or "ยังไม่ได้แก้" in line:
            category = "backlog"
            continue
        if "feedback" in lowered or "feedback" in line:
            category = "feedback"
            continue
        if "สิ่งที่จะไม่มี" in line:
            category = "excluded"
            continue
        if "สิ่งที่จะต้องมี" in line:
            category = "planned"
            continue
        if "ข้อมูลเพิ่มเติม" in line:
            category = "note"
            continue
        if line.startswith(("*", "-", "•")):
            body = re.sub(r"^[*\-•]\s*", "", line).strip()
            references = [scene for scene in known_scenes if scene in body]
            items.append(
                PatchItem(
                    version=version,
                    build_id=build_id,
                    category=category,
                    text=body,
                    scene_ids=references,
                )
            )
    return items


def _parse_patch_workbook(
    workbook_data: BytesIO,
    source_name: str,
    known_scenes: tuple[str, ...] = (),
) -> list[PatchItem]:
    workbook = load_workbook(workbook_data, read_only=True, data_only=True)
    try:
        worksheet = next(
            (sheet for sheet in workbook.worksheets if "patch" in sheet.title.casefold()),
            workbook.worksheets[0] if workbook.worksheets else None,
        )
        if worksheet is None:
            return []
        version = ""
        build_id = ""
        category = "demo-update"
        items: list[PatchItem] = []
        for row in worksheet.iter_rows(values_only=True):
            cells = [str(value).strip() if value is not None else "" for value in row]
            text = next((value for value in cells if value), "")
            if not text:
                continue
            version_match = re.search(r"\bV?(\d+\.\d+\.\d+(?:[-\w.]*)?)", text, re.IGNORECASE)
            if version_match:
                version = version_match.group(1)
                continue
            build_match = re.search(r"Build\s*ID\s*[:：]\s*(\S+)", text, re.IGNORECASE)
            if build_match:
                build_id = build_match.group(1)
                continue
            if text.casefold() in {"note dev", "report", "patch/demo"}:
                category = "report" if text.casefold() == "report" else category
                continue
            if not version or text.casefold().startswith("player "):
                continue
            # Ignore rows that are only a label/status; retain test notes and outcomes.
            detail = "\n".join(value for value in cells if value)
            if len(detail.strip()) < 4:
                continue
            references = [scene for scene in known_scenes if scene in detail]
            items.append(PatchItem(version, build_id, category, detail, references, source_name))
        return items
    finally:
        workbook.close()


def _read_text_source(source: str) -> tuple[str, str]:
    value = source.strip()
    if value.startswith(("https://docs.google.com/document/", "http://docs.google.com/document/")):
        match = re.search(r"/document/d/([\w-]+)", value)
        if not match:
            raise ValueError("Google Docs link does not contain a document ID.")
        url = f"https://docs.google.com/document/d/{match.group(1)}/export?format=txt"
        with urlopen(url, timeout=30) as response:
            content = response.read().decode("utf-8-sig")
        return content, "Google Docs patch note"
    path = Path(value)
    return path.read_text(encoding="utf-8-sig"), path.name


def _read_workbook_source(source: str) -> tuple[BytesIO, str]:
    value = source.strip()
    if value.startswith(("https://docs.google.com/spreadsheets/", "http://docs.google.com/spreadsheets/")):
        match = re.search(r"/spreadsheets/d/([\w-]+)", value)
        if not match:
            raise ValueError("Google Sheets link does not contain a spreadsheet ID.")
        url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=xlsx"
        with urlopen(url, timeout=60) as response:
            payload = response.read()
        return BytesIO(payload), f"Google Sheets {match.group(1)}"
    path = Path(value)
    return BytesIO(path.read_bytes()), path.name


def _parse_cue_row(
    sheet_name: str, headers: dict[str, int], row: tuple[Any, ...], source_row: int = 0
) -> StoryCue | None:
    key = _cell_text(row, headers.get("Key", -1))
    if not key:
        return None
    row_name = _cell_text(row, headers.get("Row Name", -1))
    scene_id = _scene_from_key(row_name or key)
    start = _parse_time(_cell(row, headers.get("Time_Start", -1)))
    end = _parse_time(_cell(row, headers.get("Time_End", -1)))
    translations = {
        locale: text
        for header, index in headers.items()
        if (locale := _normalize_locale(header))
        and (text := _cell_text(row, index))
    }
    return StoryCue(key, scene_id, start, end, translations, sheet_name, source_row)


def _parse_choice_row(
    sheet_name: str, headers: dict[str, int], row: tuple[Any, ...], source_row: int = 0
) -> StoryChoice | None:
    key = _cell_text(row, headers.get("Key", -1))
    if not key:
        return None
    translations = {
        locale: text
        for header, index in headers.items()
        if (locale := _normalize_locale(header))
        and (text := _cell_text(row, index))
    }
    return StoryChoice(
        key, _scene_from_key(_cell_text(row, headers.get("---", -1)) or key),
        translations, sheet_name, source_row,
    )


def _normalize_locale(header: str) -> str:
    value = header.strip().casefold()
    if value.startswith("lang-"):
        value = value[5:]
    aliases = {
        "thai": "th",
        "th": "th",
        "english": "en",
        "en": "en",
        "japanese": "ja",
        "jp": "ja",
        "ja": "ja",
        "chinese (simplified)": "zh-hans",
        "zh-hans": "zh-hans",
        "chinese (traditional)": "zh-hant",
        "zh-hant": "zh-hant",
        "spanish (spain)": "es-es",
        "es-es": "es-es",
    }
    if value in aliases:
        return aliases[value]
    return value if re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]+)?", value) else ""


def _scene_from_key(value: str) -> str:
    return re.sub(r"_\d{3,4}$", "", value.strip())


def _parse_time(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "total_seconds"):
        return float(value.total_seconds())
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return float(value.hour * 3600 + value.minute * 60 + value.second) + value.microsecond / 1e6
    raw = str(value).strip().replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        parts = raw.split(":")
        if len(parts) not in {2, 3}:
            raise ValueError(f"Unsupported subtitle time value: {value!r}")
        seconds = float(parts[-1])
        minutes = int(parts[-2])
        hours = int(parts[-3]) if len(parts) == 3 else 0
        return hours * 3600 + minutes * 60 + seconds


def _cell(row: tuple[Any, ...], index: int) -> Any:
    return row[index] if 0 <= index < len(row) else None


def _cell_text(row: tuple[Any, ...], index: int) -> str:
    value = _cell(row, index)
    return str(value).strip() if value is not None else ""


def _merge_translations(primary: StoryCue, alternate: StoryCue) -> StoryCue:
    translations = dict(alternate.translations)
    translations.update(primary.translations)
    return StoryCue(
        primary.key,
        primary.scene_id,
        primary.start,
        primary.end,
        translations,
        primary.source_sheet,
        primary.source_row,
    )


def _merge_choice_translations(primary: StoryChoice, alternate: StoryChoice) -> StoryChoice:
    translations = dict(alternate.translations)
    translations.update(primary.translations)
    return StoryChoice(
        primary.key, primary.scene_id, translations, primary.source_sheet, primary.source_row
    )


def _translations_conflict(primary: dict[str, str], alternate: dict[str, str]) -> bool:
    return any(
        primary[locale].strip() != alternate[locale].strip()
        for locale in primary.keys() & alternate.keys()
    )


def _project_to_dict(project: StoryTimelineProject) -> dict[str, Any]:
    return {
        "title": project.title,
        "required_locales": project.required_locales,
        "source_summary": project.source_summary,
        "conflicts": project.conflicts,
        "patch_items": [asdict(item) for item in project.patch_items],
        "scenes": {scene_id: asdict(scene) for scene_id, scene in project.scenes.items()},
    }
