"""Damage calculation helpers for champions and item builds."""
from __future__ import annotations

import itertools
import math
from typing import Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Union

from ..models.champion import Ability, Champion
from ..models.item import Item, ItemPassive, ItemRepository

Number = Union[int, float]


class DamageCalculator:
    """Provides burst and sustained damage calculations for champions."""

    def __init__(self, *, item_repository: Optional[ItemRepository] = None, default_target_health: float = 2000.0) -> None:
        self.item_repository = item_repository
        self.default_target_health = default_target_health

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def calculate_burst_combo(
        self,
        champion: Champion,
        level: int,
        items: Sequence[Union[Item, str]],
        *,
        target_health: Optional[Number] = None,
        combo: Optional[Sequence[str]] = None,
    ) -> float:
        """Compute the burst combo damage for a champion with the provided items."""

        item_objects = self._ensure_items(items)
        stats = self._aggregate_stats(champion, level, item_objects)
        target = float(target_health if target_health is not None else self.default_target_health)
        sequence = combo or champion.combo_sequence or []

        total_damage = 0.0
        spell_burst_available = {item.id: True for item in item_objects}

        for action in sequence:
            if action.upper() == "AA":
                total_damage += self._auto_attack_damage(stats, item_objects)
                continue

            ability = champion.ability(action)
            rank = champion.ability_rank(action, level)
            if rank <= 0:
                continue
            damage = self._ability_damage(ability, stats, rank)
            damage += self._burst_passive_damage(item_objects, stats, target, ability, spell_burst_available)
            total_damage += damage

        return total_damage

    def calculate_sustained_dps(
        self,
        champion: Champion,
        level: int,
        items: Sequence[Union[Item, str]],
        *,
        duration: float = 10.0,
        target_health: Optional[Number] = None,
    ) -> float:
        """Compute sustained DPS over a fixed duration."""

        item_objects = self._ensure_items(items)
        stats = self._aggregate_stats(champion, level, item_objects)
        target = float(target_health if target_health is not None else self.default_target_health)
        total_damage = 0.0
        ability_haste = stats.get("ability_haste", 0.0)

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
                item_objects,
                stats,
                target,
                ability,
                casts=casts,
                duration=duration,
            )

        total_damage += self._sustained_auto_damage(stats, item_objects, duration)
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
    ) -> List[Tuple[Tuple[str, ...], float]]:
        """Return the highest-damage builds from the provided item pool."""

        pool_items = [self._ensure_item(item) for item in item_pool]
        combos = itertools.combinations(pool_items, build_size)
        scores: List[Tuple[Tuple[str, ...], float]] = []
        target = target_health

        for combo_items in combos:
            names = tuple(item.name for item in combo_items)
            if metric == "burst":
                score = self.calculate_burst_combo(champion, level, combo_items, target_health=target)
            elif metric == "dps":
                score = self.calculate_sustained_dps(
                    champion,
                    level,
                    combo_items,
                    duration=duration,
                    target_health=target,
                )
            else:
                raise ValueError(f"Unsupported metric '{metric}'")
            scores.append((names, score))

        scores.sort(key=lambda entry: entry[1], reverse=True)
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

    def _aggregate_stats(self, champion: Champion, level: int, items: Sequence[Item]) -> MutableMapping[str, float]:
        stats: MutableMapping[str, float] = {
            "attack_damage": champion.attack_damage_at(level),
            "ability_power": champion.ability_power_at(level),
            "attack_speed": champion.attack_speed_at(level),
            "ability_haste": champion.ability_haste_at(level),
        }

        for item in items:
            for stat, value in item.stats.items():
                stats[stat] = stats.get(stat, 0.0) + value

        # Apply multiplicative stat modifiers (e.g., Rabadon's Deathcap)
        for item in items:
            for passive in item.passives:
                if passive.type == "stat_multiplier":
                    stat_key = passive.values.get("stat")
                    multiplier = passive.values.get("multiplier", 0.0)
                    if stat_key:
                        stats[stat_key] = stats.get(stat_key, 0.0) * (1 + multiplier)

        return stats

    def _ability_damage(self, ability: Ability, stats: Mapping[str, float], rank: int) -> float:
        base_damage = ability.base_damage_at_rank(rank)
        scaling_damage = sum(stats.get(stat, 0.0) * ratio for stat, ratio in ability.scalings.items())
        return base_damage + scaling_damage

    def _auto_attack_damage(self, stats: Mapping[str, float], items: Sequence[Item]) -> float:
        damage = stats.get("attack_damage", 0.0)
        for item in items:
            for passive in item.passives:
                if passive.type == "on_hit_magic_damage":
                    extra = passive.values.get("base_damage", 0.0)
                    extra += sum(stats.get(stat, 0.0) * ratio for stat, ratio in passive.values.get("scaling", {}).items())
                    damage += extra
        return damage

    def _burst_passive_damage(
        self,
        items: Sequence[Item],
        stats: Mapping[str, float],
        target_health: float,
        ability: Ability,
        availability: Mapping[str, bool],
    ) -> float:
        bonus_damage = 0.0
        for item in items:
            for passive in item.passives:
                if passive.type == "spell_burst" and availability.get(item.id, False):
                    availability[item.id] = False
                    bonus_damage += self._passive_spell_burst_damage(passive, stats)
                elif passive.type == "dot_percent_max_health":
                    bonus_damage += passive.values.get("percent", 0.0) * target_health
        return bonus_damage

    def _sustained_passive_damage(
        self,
        items: Sequence[Item],
        stats: Mapping[str, float],
        target_health: float,
        ability: Ability,
        *,
        casts: int,
        duration: float,
    ) -> float:
        bonus = 0.0
        for item in items:
            for passive in item.passives:
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

    def _sustained_auto_damage(self, stats: Mapping[str, float], items: Sequence[Item], duration: float) -> float:
        attacks_per_second = stats.get("attack_speed", 0.0)
        if attacks_per_second <= 0 or duration <= 0:
            return 0.0
        per_attack = self._auto_attack_damage(stats, items)
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


__all__ = ["DamageCalculator"]
