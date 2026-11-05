"""Profile-scoped known-screen recognition from imported story text.

This is a conservative gate, not a semantic scene classifier: it recognizes a
screen only when OCR contains text already present in the selected game's
imported subtitle/choice data or its explicitly configured menu cues.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


class ProfileStateOracle:
    """Match OCR against known story cues for exactly one game profile."""

    def __init__(
        self,
        cues: list[dict[str, str]],
        profile: str,
        story_choice_groups: list[list[str]] | None = None,
    ) -> None:
        self.profile = profile
        # Longer phrases first, so common short words cannot dominate matches.
        unique = {
            (_normalize(item.get("text", "")), item.get("scene_id", ""), item.get("kind", ""))
            for item in cues
            if _normalize(item.get("text", ""))
        }
        self._cues = sorted(
            (cue for cue in unique if len(cue[0].replace(" ", "")) >= 5),
            key=lambda cue: len(cue[0]),
            reverse=True,
        )
        # Compile boundary-aware Latin patterns once when loading the profile.
        # Recompiling thousands of patterns on every video frame made OCR
        # recognition exceed the FMV choice timer on modest machines.
        self._compiled_cues = tuple(
            (
                phrase,
                scene_id,
                kind,
                re.compile(
                    r"(?<!\w)"
                    + r"\s*".join(re.escape(token) for token in phrase.split())
                    + r"(?!\w)"
                ) if " " in phrase else None,
            )
            for phrase, scene_id, kind in self._cues
        )
        self.story_choice_labels = tuple(sorted({
            item["text"].strip()
            for item in cues
            if item.get("kind") == "story_choice"
            and isinstance(item.get("text"), str)
            and "\ufffd" not in item["text"]
            and len(_normalize(item["text"]).replace(" ", "")) >= 5
        }))
        self._story_choice_groups = tuple(
            tuple(sorted({label.strip() for label in group if isinstance(label, str) and label.strip()}))
            for group in (story_choice_groups or [])
        )

    @classmethod
    def from_database(
        cls,
        profile: str,
        database_path: str | Path,
        menu_cues: list[str] | tuple[str, ...] = (),
    ) -> ProfileStateOracle:
        """Load only cue data scoped to *profile* from a read-only SQLite DB."""
        cues = [
            {"text": text, "scene_id": "", "kind": "profile_menu"}
            for text in menu_cues
        ]
        path = Path(database_path).resolve()
        choice_labels_by_scene: dict[str, set[str]] = {}
        choice_groups: list[list[str]] = []
        if path.is_file():
            # URI read-only mode prevents the runtime recognizer from migrating
            # or modifying the user's source database.
            uri = f"file:{path.as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                for table in ("subtitle_cues", "story_choices"):
                    rows = connection.execute(
                        f"SELECT scene_id, translations_json FROM {table} WHERE profile = ?",
                        (profile,),
                    )
                    for scene_id, raw_translations in rows:
                        try:
                            translations: Any = json.loads(raw_translations)
                        except (TypeError, json.JSONDecodeError):
                            continue
                        if not isinstance(translations, dict):
                            continue
                        for language, text in translations.items():
                            if language.casefold() != "key" and isinstance(text, str):
                                cues.append({
                                    "text": text,
                                    "scene_id": str(scene_id),
                                    "kind": table.removesuffix("s"),
                                })
                                if table == "story_choices" and text.strip() and "\ufffd" not in text:
                                    choice_labels_by_scene.setdefault(str(scene_id), set()).add(text.strip())
                has_story_links = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'story_links'"
                ).fetchone()
                if has_story_links:
                    linked_sources = connection.execute(
                        "SELECT DISTINCT source_scene FROM story_links WHERE profile = ?",
                        (profile,),
                    )
                    for (source_scene,) in linked_sources:
                        siblings = connection.execute(
                            "SELECT target_scene FROM story_links WHERE profile = ? AND source_scene = ?",
                            (profile, source_scene),
                        ).fetchall()
                        group_labels = {
                            label
                            for (sibling_scene,) in siblings
                            for label in choice_labels_by_scene.get(str(sibling_scene), set())
                        }
                        if len(group_labels) > 1:
                            choice_groups.append(sorted(group_labels))
        return cls(cues, profile, choice_groups)

    def visual_choice_candidates(self, requested_labels: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        """Expand requested choice labels to options linked from the same source node."""
        def normalize_label(value: str) -> str:
            return _normalize(value).replace(" ", "")

        requested = {normalize_label(value) for value in requested_labels if value.strip()}
        labels = {value.strip() for value in requested_labels if value.strip()}
        for group in self._story_choice_groups:
            group = tuple(value for value in group if "\ufffd" not in value)
            group_keys = {normalize_label(value) for value in group}
            if requested & group_keys:
                labels.update(group)
        return tuple(sorted(labels))

    def recognize(self, ocr_words: list[dict[str, Any]]) -> dict[str, Any]:
        """Return known status and grounded cues; empty/noisy OCR stays unknown."""
        raw_text = " ".join(
            str(word.get("text", "")) for word in ocr_words if word.get("text")
        )
        text = _normalize(raw_text)
        if not text:
            return {"known": False, "profile": self.profile, "scene_ids": [], "matches": []}

        text_compact = text.replace(" ", "")
        matches: list[dict[str, str]] = []
        scene_ids: set[str] = set()
        for phrase, scene_id, kind, compiled_pattern in self._compiled_cues:
            if compiled_pattern is not None:
                # Latin/space-delimited labels must match token boundaries.
                found = compiled_pattern.search(text) is not None
            else:
                # Thai and other scripts are commonly OCR'd without spaces.
                found = phrase in text_compact
            if found:
                matches.append({"text": phrase, "scene_id": scene_id, "kind": kind})
                if scene_id:
                    scene_ids.add(scene_id)
                if len(matches) >= 8:
                    break
        return {
            "known": bool(matches),
            "profile": self.profile,
            "scene_ids": sorted(scene_ids),
            "matches": matches,
        }
