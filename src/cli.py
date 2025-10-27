"""Command line interface for the damage calculator."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Sequence

from .calculators.damage import DamageCalculator
from .models.champion import Champion, ChampionRepository
from .models.item import ItemRepository
from .models.rune import RuneRepository


def load_repositories() -> tuple[ChampionRepository, ItemRepository, RuneRepository]:
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    champions = ChampionRepository.from_file(data_dir / "champions.json")
    items = ItemRepository.from_file(data_dir / "items.json")
    runes = RuneRepository.from_file(data_dir / "runes.json")
    return champions, items, runes


def champion_label(champion: Champion) -> str:
    return f"{champion.name} ({champion.role})" if champion.role else champion.name


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="League of Legends damage calculator")
    parser.add_argument("--champion", help="Champion name or id to evaluate", default=None)
    parser.add_argument("--level", type=int, default=13, help="Champion level to evaluate")
    parser.add_argument("--build-size", type=int, default=2, help="Number of items in each build combination")
    parser.add_argument("--top", type=int, default=1, help="Number of top builds to display")
    parser.add_argument("--duration", type=float, default=10.0, help="Duration window for sustained DPS calculations")
    parser.add_argument(
        "--metric",
        choices=["burst", "dps"],
        default="burst",
        help="Metric to sort builds by",
    )
    parser.add_argument(
        "--items",
        nargs="*",
        default=None,
        help="Optional subset of items to evaluate (defaults to all items).",
    )
    parser.add_argument(
        "--runes",
        nargs="*",
        default=None,
        help="Optional subset of rune pages to evaluate (defaults to all runes).",
    )
    parser.add_argument(
        "--target-health",
        type=float,
        default=None,
        help="Override target health used for passives and calculations.",
    )

    args = parser.parse_args(argv)

    champion_repo, item_repo, rune_repo = load_repositories()
    calculator = DamageCalculator(item_repository=item_repo, rune_repository=rune_repo)

    if args.champion:
        champions: Iterable[Champion] = [champion_repo.get(args.champion)]
    else:
        champions = champion_repo.all()

    item_pool: List[str]
    if args.items:
        item_pool = args.items
    else:
        item_pool = [item.name for item in item_repo.all()]

    for champion in champions:
        print(f"=== {champion_label(champion)} ===")
        rune_pool = args.runes if args.runes else None
        builds = calculator.find_best_builds(
            champion,
            args.level,
            item_pool=item_pool,
            build_size=args.build_size,
            metric=args.metric,
            top_n=args.top,
            duration=args.duration,
            target_health=args.target_health,
            rune_pool=rune_pool,
        )
        if not builds:
            print("  No builds evaluated.")
            continue
        for position, build in enumerate(builds, start=1):
            metric_label = "Burst" if args.metric == "burst" else "DPS"
            formatted_value = f"{build.metric_value:.1f}"
            rune_label = build.rune if build.rune else "No Rune"
            print(
                f"  {position}. {', '.join(build.items)} -> {metric_label}: {formatted_value} (Rune: {rune_label})"
            )


if __name__ == "__main__":
    main()
