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


@dataclass
class DamageComponents:
    """Tracks separate physical, magic, and true damage totals."""

    physical: float = 0.0
    magic: float = 0.0
    true: float = 0.0

    def __iadd__(self, other: "DamageComponents") -> "DamageComponents":
        self.physical += other.physical
        self.magic += other.magic
        self.true += other.true
        return self

    def scaled(self, factor: float) -> "DamageComponents":
        return DamageComponents(
            physical=self.physical * factor,
            magic=self.magic * factor,
            true=self.true * factor,
        )

    def scaled_total(self, armor: float, magic_resist: float) -> float:
        return (
            self._apply_resistance(self.physical, armor)
            + self._apply_resistance(self.magic, magic_resist)
            + self.true
        )

    @staticmethod
    def _apply_resistance(amount: float, resistance: float) -> float:
        if amount <= 0:
            return 0.0
        if resistance >= 0:
            return amount * (100.0 / (100.0 + resistance))
        return amount * (2.0 - 100.0 / (100.0 - resistance))


class DamageCalculator:
    """Provides burst and sustained damage calculations for champions."""

    def __init__(
        self,
        *,
        item_repository: Optional[ItemRepository] = None,
        rune_repository: Optional[RuneRepository] = None,
        default_target_health: float = 2000.0,
        default_target_armor: float = 0.0,
        default_target_magic_resist: float = 0.0,
    ) -> None:
        self.item_repository = item_repository
        self.rune_repository = rune_repository
        self.default_target_health = default_target_health
        self.default_target_armor = default_target_armor
        self.default_target_magic_resist = default_target_magic_resist

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
        target_armor: Optional[Number] = None,
        target_magic_resist: Optional[Number] = None,
        combo: Optional[Sequence[str]] = None,
    ) -> float:
        """Compute the burst combo damage for a champion with the provided items."""

        item_objects = self._ensure_items(items)
        rune_objects = self._ensure_runes(runes or [])
        stats = self._aggregate_stats(champion, level, item_objects, rune_objects)
        target = float(target_health if target_health is not None else self.default_target_health)
        armor = float(target_armor if target_armor is not None else self.default_target_armor)
        magic_resist = float(
            target_magic_resist
            if target_magic_resist is not None
            else self.default_target_magic_resist
        )
        sequence = combo or champion.combo_sequence or []

        damage_totals = DamageComponents()
        passive_sources = self._collect_passives(item_objects, rune_objects)
        spell_burst_available = {
            key: True
            for key, passive in passive_sources
            if passive.type == "spell_burst"
        }

        for action in sequence:
            if action.upper() == "AA":
                damage_totals += self._auto_attack_damage(stats, passive_sources)
                continue

            ability = champion.ability(action)
            rank = champion.ability_rank(action, level)
            if rank <= 0:
                continue
            damage_totals += self._ability_damage(ability, stats, rank)
            damage_totals += self._burst_passive_damage(
                passive_sources, stats, target, ability, spell_burst_available
            )

        return damage_totals.scaled_total(armor, magic_resist)

    def calculate_sustained_dps(
        self,
        champion: Champion,
        level: int,
        items: Sequence[Union[Item, str]],
        runes: Optional[Sequence[Union[Rune, str]]] = None,
        *,
        duration: float = 10.0,
        target_health: Optional[Number] = None,
        target_armor: Optional[Number] = None,
        target_magic_resist: Optional[Number] = None,
    ) -> float:
        """Compute sustained DPS over a fixed duration."""

        item_objects = self._ensure_items(items)
        rune_objects = self._ensure_runes(runes or [])
        stats = self._aggregate_stats(champion, level, item_objects, rune_objects)
        target = float(target_health if target_health is not None else self.default_target_health)
        armor = float(target_armor if target_armor is not None else self.default_target_armor)
        magic_resist = float(
            target_magic_resist
            if target_magic_resist is not None
            else self.default_target_magic_resist
        )
        damage_totals = DamageComponents()
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
            ability_damage = self._ability_damage(ability, stats, rank)
            damage_totals += ability_damage.scaled(casts)
            damage_totals += self._sustained_passive_damage(
                passive_sources,
                stats,
                target,
                ability,
                casts=casts,
                duration=duration,
            )

        damage_totals += self._sustained_auto_damage(stats, passive_sources, duration)
        total_damage = damage_totals.scaled_total(armor, magic_resist)
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
        target_armor: Optional[Number] = None,
        target_magic_resist: Optional[Number] = None,
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
                        target_armor=target_armor,
                        target_magic_resist=target_magic_resist,
                    )
                elif metric == "dps":
                    score = self.calculate_sustained_dps(
                        champion,
                        level,
                        combo_items,
                        runes=rune_list,
                        duration=duration,
                        target_health=target,
                        target_armor=target_armor,
                        target_magic_resist=target_magic_resist,
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

    def _ability_damage(
        self, ability: Ability, stats: Mapping[str, float], rank: int
    ) -> DamageComponents:
        base_damage = ability.base_damage_at_rank(rank)
        scaling_damage = sum(
            stats.get(stat, 0.0) * ratio for stat, ratio in ability.scalings.items()
        )
        total = base_damage + scaling_damage
        damage_type = ability.damage_type.lower()
        if damage_type == "physical":
            return DamageComponents(physical=total)
        if damage_type == "true":
            return DamageComponents(true=total)
        return DamageComponents(magic=total)

    def _auto_attack_damage(
        self, stats: Mapping[str, float], passives: Sequence[Tuple[str, ItemPassive]]
    ) -> DamageComponents:
        physical = stats.get("attack_damage", 0.0)
        magic = 0.0
        true = 0.0
        for _, passive in passives:
            if passive.type.startswith("on_hit"):
                extra = passive.values.get("base_damage", 0.0)
                scaling = passive.values.get("scaling", {})
                if isinstance(scaling, Mapping):
                    extra += sum(
                        stats.get(stat, 0.0) * ratio for stat, ratio in scaling.items()
                    )
                damage_type = passive.values.get("damage_type") or {
                    "on_hit_magic_damage": "magic",
                    "on_hit_true_damage": "true",
                    "on_hit_physical_damage": "physical",
                }.get(passive.type, "magic")
                if damage_type == "physical":
                    physical += extra
                elif damage_type == "true":
                    true += extra
                else:
                    magic += extra
        return DamageComponents(physical=physical, magic=magic, true=true)

    def _burst_passive_damage(
        self,
        passives: Sequence[Tuple[str, ItemPassive]],
        stats: Mapping[str, float],
        target_health: float,
        ability: Ability,
        availability: Mapping[str, bool],
    ) -> DamageComponents:
        bonus_damage = DamageComponents()
        for key, passive in passives:
            if passive.type == "spell_burst" and availability.get(key, False):
                availability[key] = False
                amount = self._passive_spell_burst_damage(passive, stats)
                damage_type = passive.values.get("damage_type", "magic")
                bonus_damage += self._components_for_damage(amount, damage_type)
            elif passive.type == "dot_percent_max_health":
                amount = passive.values.get("percent", 0.0) * target_health
                damage_type = passive.values.get("damage_type", "magic")
                bonus_damage += self._components_for_damage(amount, damage_type)
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
    ) -> DamageComponents:
        bonus = DamageComponents()
        for _, passive in passives:
            if passive.type == "spell_burst":
                cooldown = passive.values.get("cooldown", duration)
                procs = min(casts, self._casts_in_duration(cooldown, duration)) if cooldown > 0 else casts
                amount = procs * self._passive_spell_burst_damage(passive, stats)
                damage_type = passive.values.get("damage_type", "magic")
                bonus += self._components_for_damage(amount, damage_type)
            elif passive.type == "dot_percent_max_health":
                amount = casts * passive.values.get("percent", 0.0) * target_health
                damage_type = passive.values.get("damage_type", "magic")
                bonus += self._components_for_damage(amount, damage_type)
        return bonus

    def _passive_spell_burst_damage(self, passive: ItemPassive, stats: Mapping[str, float]) -> float:
        damage = passive.values.get("damage", 0.0)
        damage += sum(stats.get(stat, 0.0) * ratio for stat, ratio in passive.values.get("scaling", {}).items())
        return damage

    @staticmethod
    def _components_for_damage(amount: float, damage_type: str) -> DamageComponents:
        if amount <= 0:
            return DamageComponents()
        dtype = damage_type.lower()
        if dtype == "physical":
            return DamageComponents(physical=amount)
        if dtype == "true":
            return DamageComponents(true=amount)
        return DamageComponents(magic=amount)

    def _sustained_auto_damage(
        self,
        stats: Mapping[str, float],
        passives: Sequence[Tuple[str, ItemPassive]],
        duration: float,
    ) -> DamageComponents:
        attacks_per_second = stats.get("attack_speed", 0.0)
        if attacks_per_second <= 0 or duration <= 0:
            return DamageComponents()
        per_attack = self._auto_attack_damage(stats, passives)
        return per_attack.scaled(attacks_per_second * duration)

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
