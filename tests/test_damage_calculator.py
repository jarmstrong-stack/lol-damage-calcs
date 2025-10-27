from pathlib import Path

import pytest

from src.calculators.damage import DamageCalculator
from src.models.champion import ChampionRepository
from src.models.item import ItemRepository


@pytest.fixture(scope="module")
def repositories() -> tuple[ChampionRepository, ItemRepository]:
    root = Path(__file__).resolve().parents[1]
    champion_repo = ChampionRepository.from_file(root / "data" / "champions.json")
    item_repo = ItemRepository.from_file(root / "data" / "items.json")
    return champion_repo, item_repo


def test_ahri_burst_combo(repositories: tuple[ChampionRepository, ItemRepository]) -> None:
    champion_repo, item_repo = repositories
    calculator = DamageCalculator(item_repository=item_repo)
    ahri = champion_repo.get("ahri")
    items = [item_repo.get("Luden's Tempest"), item_repo.get("Rabadon's Deathcap")]

    damage = calculator.calculate_burst_combo(ahri, level=13, items=items, target_health=2000)

    assert damage == pytest.approx(1734.5, rel=0.01)


def test_cassiopeia_sustained_dps(repositories: tuple[ChampionRepository, ItemRepository]) -> None:
    champion_repo, item_repo = repositories
    calculator = DamageCalculator(item_repository=item_repo)
    cassio = champion_repo.get("cassiopeia")
    items = [item_repo.get("Liandry's Anguish"), item_repo.get("Nashor's Tooth")]

    dps = calculator.calculate_sustained_dps(cassio, level=13, items=items, duration=10, target_health=2000)

    assert dps == pytest.approx(667.2, rel=0.05)


def test_best_burst_build_identifies_ludens_rabadons(repositories: tuple[ChampionRepository, ItemRepository]) -> None:
    champion_repo, item_repo = repositories
    calculator = DamageCalculator(item_repository=item_repo)
    ahri = champion_repo.get("ahri")

    builds = calculator.find_best_builds(
        ahri,
        level=13,
        item_pool=["Luden's Tempest", "Rabadon's Deathcap", "Liandry's Anguish"],
        build_size=2,
        metric="burst",
        top_n=1,
        target_health=2000,
    )

    assert builds
    best_build, damage = builds[0]
    assert best_build == ("Luden's Tempest", "Rabadon's Deathcap")
    assert damage == pytest.approx(1734.5, rel=0.01)
