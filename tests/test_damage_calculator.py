from pathlib import Path

import pytest

from src.calculators.damage import DamageCalculator
from src.models.champion import ChampionRepository
from src.models.item import ItemRepository
from src.models.rune import RuneRepository


@pytest.fixture(scope="module")
def repositories() -> tuple[ChampionRepository, ItemRepository, RuneRepository]:
    root = Path(__file__).resolve().parents[1]
    champion_repo = ChampionRepository.from_file(root / "data" / "champions.json")
    item_repo = ItemRepository.from_file(root / "data" / "items.json")
    rune_repo = RuneRepository.from_file(root / "data" / "runes.json")
    return champion_repo, item_repo, rune_repo


def test_ahri_burst_combo(
    repositories: tuple[ChampionRepository, ItemRepository, RuneRepository]
) -> None:
    champion_repo, item_repo, rune_repo = repositories
    calculator = DamageCalculator(item_repository=item_repo, rune_repository=rune_repo)
    ahri = champion_repo.get("ahri")
    items = [item_repo.get("Luden's Tempest"), item_repo.get("Rabadon's Deathcap")]
    runes = [rune_repo.get("domination_electrocute")]

    damage = calculator.calculate_burst_combo(
        ahri, level=13, items=items, runes=runes, target_health=2000
    )

    assert damage == pytest.approx(1961.6, rel=0.01)


def test_cassiopeia_sustained_dps(
    repositories: tuple[ChampionRepository, ItemRepository, RuneRepository]
) -> None:
    champion_repo, item_repo, rune_repo = repositories
    calculator = DamageCalculator(item_repository=item_repo, rune_repository=rune_repo)
    cassio = champion_repo.get("cassiopeia")
    items = [item_repo.get("Liandry's Anguish"), item_repo.get("Nashor's Tooth")]
    runes = [rune_repo.get("precision_press_the_attack")]

    dps = calculator.calculate_sustained_dps(
        cassio, level=13, items=items, runes=runes, duration=10, target_health=2000
    )

    assert dps == pytest.approx(771.3, rel=0.05)


def test_best_burst_build_identifies_ludens_rabadons(
    repositories: tuple[ChampionRepository, ItemRepository, RuneRepository]
) -> None:
    champion_repo, item_repo, rune_repo = repositories
    calculator = DamageCalculator(item_repository=item_repo, rune_repository=rune_repo)
    ahri = champion_repo.get("ahri")

    builds = calculator.find_best_builds(
        ahri,
        level=13,
        item_pool=["Luden's Tempest", "Rabadon's Deathcap", "Liandry's Anguish"],
        build_size=2,
        metric="burst",
        top_n=1,
        target_health=2000,
        rune_pool=["Domination - Electrocute", "Sorcery - Arcane Comet"],
    )

    assert builds
    best = builds[0]
    assert best.items == ("Luden's Tempest", "Rabadon's Deathcap")
    assert best.rune == "Domination - Electrocute"
    assert best.metric_value == pytest.approx(1961.6, rel=0.01)
