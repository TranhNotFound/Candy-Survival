from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ItemStack:
    item: str
    count: int


class Inventory:
    def __init__(self, rows: int, cols: int, max_stack: int):
        self.rows = rows
        self.cols = cols
        self.max_stack = max_stack
        self.slots: List[Optional[ItemStack]] = [None] * (rows * cols)

    def _find_slot(self, item: str) -> Optional[int]:
        empty_idx = None
        for index, stack in enumerate(self.slots):
            if stack and stack.item == item and stack.count < self.max_stack:
                return index
            if stack is None and empty_idx is None:
                empty_idx = index
        return empty_idx

    def add(self, item: str, count: int = 1) -> int:
        remaining = count
        while remaining > 0:
            index = self._find_slot(item)
            if index is None:
                break
            stack = self.slots[index]
            if stack is None:
                take = min(self.max_stack, remaining)
                self.slots[index] = ItemStack(item, take)
                remaining -= take
            else:
                can_take = min(self.max_stack - stack.count, remaining)
                stack.count += can_take
                remaining -= can_take
        return remaining

    def remove(self, item: str, count: int = 1) -> bool:
        if count <= 0:
            return True

        left = count
        while left > 0:
            candidates = [
                (stack.count, index)
                for index, stack in enumerate(self.slots)
                if stack and stack.item == item and stack.count > 0
            ]
            if not candidates:
                return False

            _, index = min(candidates, key=lambda pair: (pair[0], pair[1]))
            stack = self.slots[index]
            take = min(stack.count, left)
            stack.count -= take
            left -= take
            if stack.count == 0:
                self.slots[index] = None

        return True

    def clear_slot(self, index: int) -> Optional[ItemStack]:
        if 0 <= index < len(self.slots):
            stack = self.slots[index]
            self.slots[index] = None
            return stack
        return None

    def count(self, item: str) -> int:
        total = 0
        for stack in self.slots:
            if stack and stack.item == item:
                total += stack.count
        return total

    def has(self, item: str, count: int = 1) -> bool:
        return self.count(item) >= count

    def take_recipe(self, recipe: dict) -> bool:
        for item, need in recipe.items():
            if self.count(item) < need:
                return False
        for item, need in recipe.items():
            self.remove(item, need)
        return True

    def can_add(self, item: str, count: int = 1) -> bool:
        remaining = count
        for stack in self.slots:
            if stack and stack.item == item and stack.count < self.max_stack:
                remaining -= min(self.max_stack - stack.count, remaining)
            elif stack is None:
                remaining -= min(self.max_stack, remaining)
            if remaining <= 0:
                return True
        return remaining <= 0

    def is_full(self) -> bool:
        for stack in self.slots:
            if stack is None or stack.count < self.max_stack:
                return False
        return True


