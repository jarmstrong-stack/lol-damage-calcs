"""Damage calculation helpers for champions, item builds, and rune pages."""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Union

from ..models.champion import Ability, Champion
from ..models.item import Item, ItemPassive, ItemRepository
from ..models.rune import Rune, RuneRepository

Number = Union[int, float]


@dataclass(frozen=True)
class BuildRecommendation:
    """Container describing a best-performing build and rune pairing."""

    items: Tuple[str, ...]
    rune: Optional[str]
    metric_value: float


class DamageCalculator:
    """Provides burst and sustained damage calculations for champions."""

    def __init__(
        self,
        *,
        item_repository: Optional[ItemRepository] = None,
        rune_repository: Optional[RuneRepository] = None,
        default_target_health: float = 2000.0,
    ) -> None:
        self.item_repository = item_repository
        self.rune_repository = rune_repository
        self.default_target_health = default_target_health

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def calculate_burst_combo(
        self,
        champion: Champion,
        level: int,
        items: Sequence[Union[Item, str]],
        runes: Optional[Sequence[Union[Rune, str]]] = None,
        *,
        target_health: Optional[Number] = None,
        combo: Optional[Sequence[str]] = None,
    ) -> float:
        """Compute the burst combo damage for a champion with the provided items."""

        item_objects = self._ensure_items(items)
        rune_objects = self._ensure_runes(runes or [])
        stats = self._aggregate_stats(champion, level, item_objects, rune_objects)
        target = float(target_health if target_health is not None else self.default_target_health)
        sequence = combo or champion.combo_sequence or []

        total_damage = 0.0
        passive_sources = self._collect_passives(item_objects, rune_objects)
        spell_burst_available = {
            key: True
            for key, passive in passive_sources
            if passive.type == "spell_burst"
        }

        for action in sequence:
            if action.upper() == "AA":
                total_damage += self._auto_attack_damage(stats, passive_sources)
                continue

            ability = champion.ability(action)
            rank = champion.ability_rank(action, level)
            if rank <= 0:
                continue
            damage = self._ability_damage(ability, stats, rank)
            damage += self._burst_passive_damage(passive_sources, stats, target, ability, spell_burst_available)
            total_damage += damage

        return total_damage

    def calculate_sustained_dps(
        self,
        champion: Champion,
        level: int,
        items: Sequence[Union[Item, str]],
        runes: Optional[Sequence[Union[Rune, str]]] = None,
        *,
        duration: float = 10.0,
        target_health: Optional[Number] = None,
    ) -> float:
        """Compute sustained DPS over a fixed duration."""

        item_objects = self._ensure_items(items)
        rune_objects = self._ensure_runes(runes or [])
        stats = self._aggregate_stats(champion, level, item_objects, rune_objects)
        target = float(target_health if target_health is not None else self.default_target_health)
        total_damage = 0.0
        ability_haste = stats.get("ability_haste", 0.0)
        passive_sources = self._collect_passives(item_objects, rune_objects)

        for ability_key, ability in champion.abilities.items():
            rank = champion.ability_rank(ability_key, level)
            if rank <= 0:
                continue
            base_cooldown = ability.cooldown_at_rank(rank)
            if math.isinf(base_cooldown):
                continue
            effective_cooldown = self._apply_ability_haste(base_cooldown, ability_haste)
            casts = self._casts_in_duration(effective_cooldown, duration)
            if casts <= 0:
                continue
            damage_per_cast = self._ability_damage(ability, stats, rank)
            total_damage += casts * damage_per_cast
            total_damage += self._sustained_passive_damage(
                passive_sources,
                stats,
                target,
                ability,
                casts=casts,
                duration=duration,
            )

        total_damage += self._sustained_auto_damage(stats, passive_sources, duration)
        return total_damage / duration if duration > 0 else 0.0

    def find_best_builds(
        self,
        champion: Champion,
        level: int,
        *,
        item_pool: Iterable[Union[Item, str]],
        build_size: int,
        metric: str = "burst",
        top_n: int = 1,
        duration: float = 10.0,
        target_health: Optional[Number] = None,
        rune_pool: Optional[Iterable[Union[Rune, str]]] = None,
    ) -> List[BuildRecommendation]:
        """Return the highest-damage builds from the provided item pool."""

        pool_items = [self._ensure_item(item) for item in item_pool]
        combos = itertools.combinations(pool_items, build_size)
        scores: List[BuildRecommendation] = []
        target = target_health
        runes = self._prepare_rune_pool(rune_pool)

        for combo_items in combos:
            names = tuple(item.name for item in combo_items)
            best_value = float("-inf")
            best_rune_name: Optional[str] = None
            for rune in runes:
                rune_list: Sequence[Rune] = [rune] if rune is not None else []
                if metric == "burst":
                    score = self.calculate_burst_combo(
                        champion,
                        level,
                        combo_items,
                        runes=rune_list,
                        target_health=target,
                    )
                elif metric == "dps":
                    score = self.calculate_sustained_dps(
                        champion,
                        level,
                        combo_items,
                        runes=rune_list,
                        duration=duration,
                        target_health=target,
                    )
                else:
                    raise ValueError(f"Unsupported metric '{metric}'")
                if score > best_value:
                    best_value = score
                    best_rune_name = rune.name if rune is not None else None
            if best_value > float("-inf"):
                scores.append(BuildRecommendation(items=names, rune=best_rune_name, metric_value=best_value))

        scores.sort(key=lambda entry: entry.metric_value, reverse=True)
        return scores[:top_n]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_items(self, items: Sequence[Union[Item, str]]) -> List[Item]:
        return [self._ensure_item(item) for item in items]

    def _ensure_item(self, item: Union[Item, str]) -> Item:
        if isinstance(item, Item):
            return item
        if not self.item_repository:
            raise ValueError("Item repository is required when passing item identifiers.")
        return self.item_repository.get(item)

    def _ensure_runes(self, runes: Sequence[Union[Rune, str]]) -> List[Rune]:
        return [self._ensure_rune(rune) for rune in runes]

    def _ensure_rune(self, rune: Union[Rune, str]) -> Rune:
        if isinstance(rune, Rune):
            return rune
        if not self.rune_repository:
            raise ValueError("Rune repository is required when passing rune identifiers.")
        return self.rune_repository.get(rune)

    def _prepare_rune_pool(
        self, rune_pool: Optional[Iterable[Union[Rune, str]]]
    ) -> List[Optional[Rune]]:
        if rune_pool is None:
            if self.rune_repository:
                runes: List[Rune] = list(self.rune_repository.all())
            else:
                runes = []
        else:
            runes = [self._ensure_rune(rune) for rune in rune_pool]
        if not runes:
            return [None]
        return [*runes]

    def _aggregate_stats(
        self, champion: Champion, level: int, items: Sequence[Item], runes: Sequence[Rune]
    ) -> MutableMapping[str, float]:
        stats: MutableMapping[str, float] = {
            "attack_damage": champion.attack_damage_at(level),
            "ability_power": champion.ability_power_at(level),
            "attack_speed": champion.attack_speed_at(level),
            "ability_haste": champion.ability_haste_at(level),
        }

        for source_collection in (items, runes):
            for source in source_collection:
                for stat, value in source.stats.items():
                    stats[stat] = stats.get(stat, 0.0) + value

        # Apply multiplicative stat modifiers (e.g., Rabadon's Deathcap, Rabadon-like runes)
        for source_collection in (items, runes):
            for source in source_collection:
                for passive in source.passives:
                    if passive.type == "stat_multiplier":
                        stat_key = passive.values.get("stat")
                        multiplier = passive.values.get("multiplier", 0.0)
                        if stat_key:
                            stats[stat_key] = stats.get(stat_key, 0.0) * (1 + multiplier)

        return stats

    def _collect_passives(
        self, items: Sequence[Item], runes: Sequence[Rune]
    ) -> List[Tuple[str, ItemPassive]]:
        passives: List[Tuple[str, ItemPassive]] = []
        for item in items:
            for index, passive in enumerate(item.passives):
                passives.append((f"item:{item.id}:{index}", passive))
        for rune in runes:
            for index, passive in enumerate(rune.passives):
                passives.append((f"rune:{rune.id}:{index}", passive))
        return passives

    def _ability_damage(self, ability: Ability, stats: Mapping[str, float], rank: int) -> float:
        base_damage = ability.base_damage_at_rank(rank)
        scaling_damage = sum(stats.get(stat, 0.0) * ratio for stat, ratio in ability.scalings.items())
        return base_damage + scaling_damage

    def _auto_attack_damage(
        self, stats: Mapping[str, float], passives: Sequence[Tuple[str, ItemPassive]]
    ) -> float:
        damage = stats.get("attack_damage", 0.0)
        for _, passive in passives:
            if passive.type == "on_hit_magic_damage":
                extra = passive.values.get("base_damage", 0.0)
                scaling = passive.values.get("scaling", {})
                if isinstance(scaling, Mapping):
                    extra += sum(stats.get(stat, 0.0) * ratio for stat, ratio in scaling.items())
                damage += extra
        return damage

    def _burst_passive_damage(
        self,
        passives: Sequence[Tuple[str, ItemPassive]],
        stats: Mapping[str, float],
        target_health: float,
        ability: Ability,
        availability: Mapping[str, bool],
    ) -> float:
        bonus_damage = 0.0
        for key, passive in passives:
            if passive.type == "spell_burst" and availability.get(key, False):
                availability[key] = False
                bonus_damage += self._passive_spell_burst_damage(passive, stats)
            elif passive.type == "dot_percent_max_health":
                bonus_damage += passive.values.get("percent", 0.0) * target_health
        return bonus_damage

    def _sustained_passive_damage(
        self,
        passives: Sequence[Tuple[str, ItemPassive]],
        stats: Mapping[str, float],
        target_health: float,
        ability: Ability,
        *,
        casts: int,
        duration: float,
    ) -> float:
        bonus = 0.0
        for _, passive in passives:
            if passive.type == "spell_burst":
                cooldown = passive.values.get("cooldown", duration)
                procs = min(casts, self._casts_in_duration(cooldown, duration)) if cooldown > 0 else casts
                bonus += procs * self._passive_spell_burst_damage(passive, stats)
            elif passive.type == "dot_percent_max_health":
                bonus += casts * passive.values.get("percent", 0.0) * target_health
        return bonus

    def _passive_spell_burst_damage(self, passive: ItemPassive, stats: Mapping[str, float]) -> float:
        damage = passive.values.get("damage", 0.0)
        damage += sum(stats.get(stat, 0.0) * ratio for stat, ratio in passive.values.get("scaling", {}).items())
        return damage

    def _sustained_auto_damage(
        self, stats: Mapping[str, float], passives: Sequence[Tuple[str, ItemPassive]], duration: float
    ) -> float:
        attacks_per_second = stats.get("attack_speed", 0.0)
        if attacks_per_second <= 0 or duration <= 0:
            return 0.0
        per_attack = self._auto_attack_damage(stats, passives)
        return per_attack * attacks_per_second * duration

    @staticmethod
    def _apply_ability_haste(base_cooldown: float, ability_haste: float) -> float:
        if ability_haste <= 0:
            return base_cooldown
        return base_cooldown / (1 + ability_haste / 100)

    @staticmethod
    def _casts_in_duration(cooldown: float, duration: float) -> int:
        if cooldown <= 0:
            if duration <= 0:
                return 0
            return max(1, int(duration * 10))  # Assume 10 casts per second when no cooldown is provided
        if math.isinf(cooldown):
            return 0
        if duration <= 0:
            return 0
        return max(1, int(math.floor((duration - 1e-9) / cooldown)) + 1)


__all__ = ["DamageCalculator", "BuildRecommendation"]
