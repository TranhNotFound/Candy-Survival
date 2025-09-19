from typing import Dict, Iterable


class CandyStockpile:
    def __init__(self, candy_types: Iterable[str]):
        self._counts: Dict[str, int] = {candy: 0 for candy in candy_types}

    def amount(self, candy_type: str) -> int:
        return self._counts.get(candy_type, 0)

    def add(self, candy_type: str, amount: int) -> int:
        current = self._counts.get(candy_type, 0)
        self._counts[candy_type] = current + amount
        return self._counts[candy_type]

    def add_bulk(self, amounts: Dict[str, int]) -> None:
        for candy_type, value in amounts.items():
            self.add(candy_type, value)

    def can_afford(self, recipe: Dict[str, int]) -> bool:
        return all(self.amount(candy_type) >= required for candy_type, required in recipe.items())

    def consume(self, candy_type: str, amount: int) -> bool:
        if self.amount(candy_type) < amount:
            return False
        self._counts[candy_type] -= amount
        return True

    def consume_recipe(self, recipe: Dict[str, int]) -> bool:
        if not self.can_afford(recipe):
            return False
        for candy_type, required in recipe.items():
            self._counts[candy_type] -= required
        return True

    def to_dict(self) -> Dict[str, int]:
        return dict(self._counts)


class WorldProgression:
    def __init__(self, exp_per_upgrade: int, auto_upgrade_levels: int):
        self.exp_per_upgrade = exp_per_upgrade
        self.auto_upgrade_levels = auto_upgrade_levels
        self.world_exp = 0
        self._upgrades_today = 0

    def record_upgrade(self) -> None:
        self._upgrades_today += 1
        self.world_exp += self.exp_per_upgrade

    def end_of_day(self) -> bool:
        no_upgrades = self._upgrades_today == 0
        self._upgrades_today = 0
        return no_upgrades
