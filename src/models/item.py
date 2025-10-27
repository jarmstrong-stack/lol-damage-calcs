"""Item model definitions and repository helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping


@dataclass(frozen=True)
class ItemPassive:
    """Represents a passive effect on an item."""

    type: str
    values: Mapping[str, float]


@dataclass(frozen=True)
class Item:
    """Container for an item's stats and passives."""

    id: str
    name: str
    stats: Mapping[str, float]
    passives: List[ItemPassive]

    def stat(self, key: str) -> float:
        return self.stats.get(key, 0.0)


class ItemRepository:
    """Loads items from a JSON file and exposes them for lookup."""

    def __init__(self, items: Mapping[str, Item]):
        self._items: Dict[str, Item] = dict(items)

    @classmethod
    def from_file(cls, path: Path) -> "ItemRepository":
        import json

        data = json.loads(path.read_text())
        items: Dict[str, Item] = {}
        for key, payload in data.items():
            passives = [
                ItemPassive(type=passive["type"], values={k: v for k, v in passive.items() if k != "type"})
                for passive in payload.get("passives", [])
            ]
            items[key.lower()] = Item(
                id=payload["id"],
                name=payload["name"],
                stats=payload.get("stats", {}),
                passives=passives,
            )
        return cls(items)

    def get(self, identifier: str) -> Item:
        key = identifier.lower()
        if key in self._items:
            return self._items[key]
        for item in self._items.values():
            if item.name.lower() == key:
                return item
        raise KeyError(f"Unknown item '{identifier}'")

    def all(self) -> Iterable[Item]:
        return self._items.values()

    def keys(self) -> Iterable[str]:
        return self._items.keys()


__all__ = ["Item", "ItemPassive", "ItemRepository"]
