"""Champion model definitions and repository helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional


@dataclass(frozen=True)
class Ability:
    """Represents a single champion ability at various ranks."""

    key: str
    name: str
    base_damage: List[float]
    scalings: Mapping[str, float]
    cooldown: List[float]
    max_rank: int
    rank_levels: List[int]
    damage_type: str = "magic"
    damage_window: str = "instant"
    duration: Optional[float] = None

    def rank_at_level(self, level: int) -> int:
        """Return the ability rank unlocked at the provided champion level."""

        ranks = sum(1 for unlock_level in self.rank_levels if level >= unlock_level)
        return min(ranks, self.max_rank)

    def base_damage_at_rank(self, rank: int) -> float:
        if rank <= 0:
            return 0.0
        return self.base_damage[rank - 1]

    def cooldown_at_rank(self, rank: int) -> float:
        if rank <= 0:
            return float("inf")
        return self.cooldown[rank - 1]


@dataclass(frozen=True)
class Champion:
    """Container for champion stats and abilities."""

    id: str
    name: str
    role: str
    base_stats: Mapping[str, float]
    abilities: Mapping[str, Ability]
    combo_sequence: List[str]

    def ability(self, key: str) -> Ability:
        return self.abilities[key]

    def ability_rank(self, key: str, level: int) -> int:
        return self.abilities[key].rank_at_level(level)

    def attack_damage_at(self, level: int) -> float:
        base = self.base_stats.get("attack_damage", 0.0)
        growth = self.base_stats.get("attack_damage_per_level", 0.0)
        return base + growth * max(level - 1, 0)

    def ability_power_at(self, level: int) -> float:
        base = self.base_stats.get("ability_power", 0.0)
        growth = self.base_stats.get("ability_power_per_level", 0.0)
        return base + growth * max(level - 1, 0)

    def attack_speed_at(self, level: int) -> float:
        base = self.base_stats.get("attack_speed", 0.0)
        growth = self.base_stats.get("attack_speed_per_level", 0.0)
        return base * (1 + growth * max(level - 1, 0))

    def ability_haste_at(self, level: int) -> float:
        base = self.base_stats.get("ability_haste", 0.0)
        growth = self.base_stats.get("ability_haste_per_level", 0.0)
        return base + growth * max(level - 1, 0)


class ChampionRepository:
    """Loads and returns champion definitions from disk."""

    def __init__(self, champions: Mapping[str, Champion]):
        self._champions: Dict[str, Champion] = dict(champions)

    @classmethod
    def from_file(cls, path: Path) -> "ChampionRepository":
        import json

        data = json.loads(path.read_text())
        champions: Dict[str, Champion] = {}
        for key, payload in data.items():
            abilities = {
                ability_key: Ability(
                    key=ability_key,
                    name=ability_data["name"],
                    base_damage=ability_data["base_damage"],
                    scalings=ability_data.get("scalings", {}),
                    cooldown=ability_data.get("cooldown", [float("inf")]),
                    max_rank=ability_data.get("max_rank", len(ability_data.get("base_damage", []))),
                    rank_levels=ability_data.get("rank_levels", []),
                    damage_type=ability_data.get("damage_type", "magic"),
                    damage_window=ability_data.get("damage_window", "instant"),
                    duration=ability_data.get("duration"),
                )
                for ability_key, ability_data in payload["abilities"].items()
            }
            champions[key.lower()] = Champion(
                id=payload["id"],
                name=payload["name"],
                role=payload.get("role", ""),
                base_stats=payload.get("base_stats", {}),
                abilities=abilities,
                combo_sequence=payload.get("combo_sequence", []),
            )
        return cls(champions)

    def get(self, identifier: str) -> Champion:
        key = identifier.lower()
        if key in self._champions:
            return self._champions[key]
        for champion in self._champions.values():
            if champion.name.lower() == key:
                return champion
        raise KeyError(f"Unknown champion '{identifier}'")

    def all(self) -> Iterable[Champion]:
        return self._champions.values()

    def as_mapping(self) -> Mapping[str, Champion]:
        return dict(self._champions)


__all__ = ["Ability", "Champion", "ChampionRepository"]
