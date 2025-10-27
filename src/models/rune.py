"""Rune model definitions and repository helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from .item import ItemPassive


@dataclass(frozen=True)
class Rune:
    """Represents a rune page snapshot with aggregated bonuses."""

    id: str
    name: str
    stats: Mapping[str, float]
    passives: List[ItemPassive]


class RuneRepository:
    """Loads rune configurations from a JSON file."""

    def __init__(self, runes: Mapping[str, Rune]):
        self._runes: Dict[str, Rune] = dict(runes)

    @classmethod
    def from_file(cls, path: Path) -> "RuneRepository":
        import json

        data = json.loads(path.read_text())
        runes: Dict[str, Rune] = {}
        for key, payload in data.items():
            passives = [
                ItemPassive(type=passive["type"], values={k: v for k, v in passive.items() if k != "type"})
                for passive in payload.get("passives", [])
            ]
            runes[key.lower()] = Rune(
                id=payload["id"],
                name=payload["name"],
                stats=payload.get("stats", {}),
                passives=passives,
            )
        return cls(runes)

    def get(self, identifier: str) -> Rune:
        key = identifier.lower()
        if key in self._runes:
            return self._runes[key]
        for rune in self._runes.values():
            if rune.name.lower() == key:
                return rune
        raise KeyError(f"Unknown rune '{identifier}'")

    def all(self) -> Iterable[Rune]:
        return self._runes.values()


__all__ = ["Rune", "RuneRepository"]
