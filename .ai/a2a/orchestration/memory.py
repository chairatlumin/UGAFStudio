from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryType(Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


@dataclass
class MemoryEntry:
    key: str
    value: Any
    memory_type: MemoryType
    timestamp: float
    access_count: int = 0


class MemoryManager:
    def __init__(self, max_entries_per_type: Optional[Dict[MemoryType, int]] = None) -> None:
        self._storage: Dict[MemoryType, OrderedDict[str, MemoryEntry]] = {
            mt: OrderedDict() for mt in MemoryType
        }
        self.max_entries_per_type: Dict[MemoryType, int] = (
            max_entries_per_type or {mt: 100 for mt in MemoryType}
        )

    def store(self, entry: MemoryEntry) -> None:
        storage = self._storage[entry.memory_type]
        if entry.key in storage:
            del storage[entry.key]
        storage[entry.key] = entry
        self._prune(entry.memory_type)

    def retrieve(self, key: str, memory_type: MemoryType) -> Optional[MemoryEntry]:
        storage = self._storage.get(memory_type, OrderedDict())
        entry = storage.get(key)
        if entry is not None:
            entry.access_count += 1
        return entry

    def forget(self, key: str, memory_type: MemoryType) -> bool:
        storage = self._storage.get(memory_type, OrderedDict())
        if key in storage:
            del storage[key]
            return True
        return False

    def _prune(self, memory_type: MemoryType) -> None:
        max_entries = self.max_entries_per_type.get(memory_type, 100)
        storage = self._storage[memory_type]
        while len(storage) > max_entries:
            storage.popitem(last=False)

    def get_all(self, memory_type: MemoryType) -> List[MemoryEntry]:
        return list(self._storage.get(memory_type, OrderedDict()).values())

    def get_all_entries(self) -> Dict[MemoryType, List[MemoryEntry]]:
        return {mt: list(storage.values()) for mt, storage in self._storage.items()}