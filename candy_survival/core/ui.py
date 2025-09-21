import pygame
from typing import Callable, Dict, Optional, Tuple
from core.inventory import Inventory, ItemStack
from core.assets import get_candy_sprite_path, get_candy_display_name


def load_sprite(path: str) -> pygame.Surface:
    try:
        image = pygame.image.load(path)
    except (pygame.error, FileNotFoundError):
        placeholder = pygame.Surface((32, 32), pygame.SRCALPHA)
        placeholder.fill((70, 70, 80, 255))
        pygame.draw.rect(placeholder, (180, 180, 200, 255), placeholder.get_rect(), 2)
        return placeholder
    return image.convert_alpha() if image.get_alpha() is not None else image.convert()


class UIAssets:
    def __init__(self, slot_path: str, font: pygame.font.Font):
        self.slot = load_sprite(slot_path)
        self.font = font


class InfoUI:
    def __init__(
        self,
        font: pygame.font.Font,
        day: int,
        time_minutes: float,
        world_exp: int,
        pos: Tuple[int, int] = (10, 10),
    ):
        self.font = font
        self.pos = pos
        self.day = day
        self.time_minutes = time_minutes
        self.world_exp = world_exp
        self.event_countdown: Optional[int] = None

    def update(
        self,
        day: int,
        time_minutes: float,
        world_exp: int,
        event_countdown: Optional[int] = None,
    ) -> None:
        self.day = day
        self.time_minutes = time_minutes
        self.world_exp = world_exp
        self.event_countdown = event_countdown

    def draw(self, surface: pygame.Surface) -> None:
        x, y = self.pos
        width, height = 260, 96 if self.event_countdown is not None else 72
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((30, 30, 30, 200))
        surface.blit(overlay, (x, y))

        total_minutes = max(0, int(self.time_minutes))
        hours = (total_minutes // 60) % 24
        minutes = total_minutes % 60
        am_pm = "AM" if hours < 12 else "PM"
        display_hour = hours % 12 or 12
        time_text = f"{display_hour:02d}:{minutes:02d} {am_pm}"

        lines = [
            f"Day: {self.day}",
            f"Time: {time_text}",
            f"World exp: {self.world_exp}",
        ]
        if self.event_countdown is not None:
            lines.append(f"Next event in: {self.event_countdown}s")

        cursor_y = y + 10
        for line in lines:
            text = self.font.render(line, True, (255, 255, 255))
            surface.blit(text, (x + 12, cursor_y))
            cursor_y += text.get_height() + 4


class InventoryUI:
    def __init__(
        self,
        inventory: Inventory,
        ui_assets: UIAssets,
        pos: Tuple[int, int] = (20, 20),
        slot_size: int = 32,
        pad: int = 6,
    ):
        self.inventory = inventory
        self.ui_assets = ui_assets
        self.pos = pos
        self.slot_size = slot_size
        self.pad = pad

    def draw(self, surface: pygame.Surface) -> None:
        x0, y0 = self.pos
        index = 0
        for row in range(self.inventory.rows):
            for col in range(self.inventory.cols):
                x = x0 + col * (self.slot_size + self.pad)
                y = y0 + row * (self.slot_size + self.pad)
                surface.blit(self.ui_assets.slot, (x, y))
                stack = self.inventory.slots[index]
                if stack:
                    try:
                        icon_path = get_candy_sprite_path(stack.item) or f"assets/sprites/{stack.item}.bmp"
                        icon = load_sprite(icon_path)
                        surface.blit(icon, (x, y))
                    except Exception:
                        pass
                    count_text = self.ui_assets.font.render(str(stack.count), True, (255, 255, 255))
                    surface.blit(count_text, (x + 2, y + 2))
                index += 1


class CraftingUI:
    def __init__(
        self,
        recipes: Dict[str, Dict[str, int]],
        ui_assets: UIAssets,
        center: Tuple[int, int],
        craft_callback: Callable[[str, Dict[str, int]], bool],
        requirement_formatter: Optional[Callable[[str, Dict[str, int]], str]] = None,
    ):
        self.recipes = recipes
        self.ui_assets = ui_assets
        self.center = center
        self.visible = False
        self._craft_callback = craft_callback
        self._requirement_formatter = requirement_formatter

    def toggle(self) -> None:
        self.visible = not self.visible

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return

        width, height = 520, 340
        top_left_x = self.center[0] - width // 2
        top_left_y = self.center[1] - height // 2

        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((20, 20, 20, 220))
        surface.blit(overlay, (top_left_x, top_left_y))

        title = self.ui_assets.font.render("CRAFTING", True, (255, 255, 0))
        surface.blit(title, (top_left_x + 20, top_left_y + 20))

        cursor_y = top_left_y + 60
        for index, (result, recipe) in enumerate(self.recipes.items()):
            parts = []
            for item, amount in recipe.items():
                label = get_candy_display_name(item) if item.startswith("candy_") else item
                parts.append(f"{label} x{amount}")
            need_text = ", ".join(parts)
            status = ""
            if self._requirement_formatter:
                status = f" ({self._requirement_formatter(result, recipe)})"
            line = f"[{index + 1}] {result} <= {need_text}{status}"
            text_surface = self.ui_assets.font.render(line, True, (230, 230, 230))
            surface.blit(text_surface, (top_left_x + 20, cursor_y))
            cursor_y += 28

    def craft_index(self, index: int) -> bool:
        keys = list(self.recipes.keys())
        if index < 0 or index >= len(keys):
            return False
        result = keys[index]
        recipe = self.recipes[result]
        return self._craft_callback(result, recipe)




class TrashUI:
    def __init__(
        self,
        inventory: Inventory,
        ui_assets: UIAssets,
        center: Tuple[int, int],
    ):
        self.inventory = inventory
        self.ui_assets = ui_assets
        self.center = center
        self.visible = False

    def toggle(self) -> None:
        self.visible = not self.visible

    def hide(self) -> None:
        self.visible = False

    def drop_index(self, index: int) -> Optional[ItemStack]:
        return self.inventory.clear_slot(index)

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return

        width = 380
        slot_count = len(self.inventory.slots)
        line_height = self.ui_assets.font.get_height() + 6
        height = 90 + slot_count * line_height
        top_left_x = self.center[0] - width // 2
        top_left_y = self.center[1] - height // 2

        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((25, 25, 25, 220))
        surface.blit(overlay, (top_left_x, top_left_y))

        title = self.ui_assets.font.render("TRASH CAN", True, (255, 180, 80))
        surface.blit(title, (top_left_x + 20, top_left_y + 20))
        hint = self.ui_assets.font.render(
            "Press number to discard, Esc to close",
            True,
            (200, 200, 200),
        )
        surface.blit(hint, (top_left_x + 20, top_left_y + 24 + title.get_height()))

        cursor_y = top_left_y + 60 + title.get_height()
        for index, stack in enumerate(self.inventory.slots):
            label = f"[{index + 1}] "
            if stack:
                name = get_candy_display_name(stack.item) if stack.item.startswith("candy_") else stack.item
                label += f"{name} x{stack.count}"
                color = (230, 230, 230)
            else:
                label += "Empty"
                color = (140, 140, 140)
            text_surface = self.ui_assets.font.render(label, True, color)
            surface.blit(text_surface, (top_left_x + 20, cursor_y))
            cursor_y += line_height

class MessageLog:
    def __init__(self, font: pygame.font.Font):
        self.font = font
        self.lines = []

    def add(self, text: str, color: Tuple[int, int, int] = (255, 255, 255)) -> None:
        timestamp = pygame.time.get_ticks()
        self.lines.append((text, color, timestamp))
        if len(self.lines) > 6:
            self.lines.pop(0)

    def draw(self, surface: pygame.Surface, pos: Tuple[int, int] = (20, 20)) -> None:
        x, y = pos
        for text, color, _ in self.lines:
            img = self.font.render(text, True, color)
            surface.blit(img, (x, y))
            y += img.get_height() + 2

