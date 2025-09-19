import math
import random
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

import pygame

from core.inventory import Inventory


def load_sprite(path: str) -> pygame.Surface:
    image = pygame.image.load(path)
    surface = image.convert_alpha() if image.get_alpha() is not None else image.convert()
    if path.endswith("candy_purple.bmp"):
        surface = surface.copy()
        surface.fill((160, 160, 160), special_flags=pygame.BLEND_RGB_MULT)
    return surface


CANDY_TYPES = [
    "candy_red",
    "candy_blue",
    "candy_green",
    "candy_yellow",
    "candy_purple",
]


@dataclass
class ChatBubble:
    text: str
    color: Tuple[int, int, int]
    until: int


class Player:
    def __init__(
        self,
        x: float,
        y: float,
        speed: float,
        inv_rows: int,
        inv_cols: int,
        max_stack: int,
    ):
        self.x = x
        self.y = y
        self.speed = speed
        self.image = load_sprite("assets/sprites/player_test.png")
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.inventory = Inventory(inv_rows, inv_cols, max_stack)
        self.alive = True

    def _move_single_axis(self, delta: float, axis: str, colliders: Iterable[pygame.Rect]) -> None:
        if delta == 0:
            return

        if axis == "x":
            self.x += delta
            self.rect.centerx = int(self.x)
        else:
            self.y += delta
            self.rect.centery = int(self.y)

        for collider in colliders:
            if self.rect.colliderect(collider):
                if axis == "x":
                    if delta > 0:
                        self.rect.right = collider.left
                    else:
                        self.rect.left = collider.right
                    self.x = float(self.rect.centerx)
                else:
                    if delta > 0:
                        self.rect.bottom = collider.top
                    else:
                        self.rect.top = collider.bottom
                    self.y = float(self.rect.centery)

    def update(self, dt: float, inputmgr, keys, colliders: Iterable[pygame.Rect] = ()) -> None:
        dx = dy = 0.0
        if inputmgr.is_pressed("move_up", keys):
            dy -= 1
        if inputmgr.is_pressed("move_down", keys):
            dy += 1
        if inputmgr.is_pressed("move_left", keys):
            dx -= 1
        if inputmgr.is_pressed("move_right", keys):
            dx += 1

        magnitude = math.hypot(dx, dy)
        if magnitude > 0:
            dx /= magnitude
            dy /= magnitude

        dx *= self.speed * dt
        dy *= self.speed * dt

        if colliders:
            self._move_single_axis(dx, "x", colliders)
            self._move_single_axis(dy, "y", colliders)
        else:
            self.x += dx
            self.y += dy
            self.rect.center = (int(self.x), int(self.y))


class ItemEntity:
    def __init__(self, item_name: str, x: float, y: float, yield_count: int = 1):
        self.item = item_name
        self.yield_count = yield_count
        sprite = load_sprite(f"assets/sprites/{item_name}.bmp")
        if item_name == "candy_purple":
            sprite = sprite.copy()
            sprite.fill((160, 160, 160), special_flags=pygame.BLEND_RGB_MULT)
        self.image = sprite
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.alive = True
        self.spawn_position: Optional[Tuple[int, int]] = None


class StaticEntity:
    def __init__(self, surface: pygame.Surface, x: float, y: float):
        self.image = surface
        self.rect = self.image.get_rect(center=(int(x), int(y)))

    def draw(self, surface: pygame.Surface, offset: Tuple[int, int]) -> None:
        ox, oy = offset
        surface.blit(self.image, self.rect.move(-ox, -oy))


class Machine(StaticEntity):
    def __init__(self, candy_type: str, x: float, y: float, cost: int, neutral: bool = False):
        if neutral:
            base = load_sprite("assets/sprites/machine_blue.bmp").copy()
            base.fill((180, 180, 180), special_flags=pygame.BLEND_RGB_MULT)
            sprite = base
        else:
            sprite = load_sprite(f"assets/sprites/machine_{candy_type}.bmp")
        super().__init__(sprite, x, y)
        self.candy_type = candy_type
        self.item_key = None if neutral else f"candy_{candy_type}"
        self.cost = cost
        self.neutral = neutral
        self.level = 1
        self.upgraded_today = False
        self.chat: Optional[ChatBubble] = None

    def try_upgrade(self, stockpile, msglog, audio, world_progress) -> bool:
        if self.item_key is None:
            msglog.add("Neutral machine cannot be upgraded manually.", (200, 200, 200))
            audio.sfx("fail")
            return False

        if not stockpile.consume_recipe({self.item_key: self.cost}):
            msglog.add(
                f"Machine {self.candy_type}: missing {self.item_key} x{self.cost}.",
                (255, 120, 120),
            )
            audio.sfx("fail")
            return False

        self.level += 1
        self.upgraded_today = True
        world_progress.record_upgrade()
        msglog.add(
            f"Machine {self.candy_type}: upgraded to level {self.level}!", (0, 255, 0)
        )
        audio.sfx("success")
        return True

    def reset_daily_state(self) -> None:
        self.upgraded_today = False

    def auto_upgrade(self, levels: int) -> None:
        self.level += max(1, levels)


class Radio(StaticEntity):
    def __init__(self, x: float, y: float):
        super().__init__(load_sprite("assets/sprites/radio.bmp"), x, y)
        self.batteries = 0
        self.chat: Optional[ChatBubble] = None


class CraftingTable(StaticEntity):
    def __init__(self, x: float, y: float):
        super().__init__(load_sprite("assets/sprites/craft_table.bmp"), x, y)


class WallSegment(StaticEntity):
    def __init__(self, width: int, height: int, x: float, y: float):
        surface = pygame.Surface((width, height))
        surface.fill((60, 60, 70))
        super().__init__(surface.convert(), x, y)


class CandyGiver(StaticEntity):
    def __init__(self, x: float, y: float):
        surface = pygame.Surface((32, 48))
        surface.fill((50, 30, 90))
        pygame.draw.circle(surface, (180, 100, 210), (16, 16), 12)
        pygame.draw.rect(surface, (240, 200, 80), (8, 28, 16, 16), border_radius=4)
        super().__init__(surface.convert_alpha(), x, y)
        self.cooldown_until = 0
        self.used_today = False
        self.chat: Optional[ChatBubble] = None

    def ready(self, now: int) -> bool:
        return (not self.used_today) and now >= self.cooldown_until

    def reset_daily(self) -> None:
        self.used_today = False


class TrashCan(StaticEntity):
    def __init__(self, x: float, y: float):
        super().__init__(load_sprite("assets/sprites/chest.bmp"), x, y)


class NPC(StaticEntity):
    def __init__(self, x: float, y: float, speed: float):
        surface = pygame.Surface((28, 44))
        surface.fill((120, 160, 220))
        pygame.draw.rect(surface, (80, 120, 180), (0, 24, 28, 20))
        pygame.draw.circle(surface, (240, 220, 200), (14, 12), 10)
        super().__init__(surface.convert_alpha(), x, y)
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.speed = speed
        self.target: Optional[Tuple[float, float]] = None
        self.next_wander_ms = 0
        self.chat: Optional[ChatBubble] = None

    def _move_single_axis(self, delta: float, axis: str, colliders: Iterable[pygame.Rect]) -> None:
        if delta == 0:
            return
        if axis == "x":
            self.x += delta
            self.rect.centerx = int(self.x)
        else:
            self.y += delta
            self.rect.centery = int(self.y)
        for collider in colliders:
            if self.rect.colliderect(collider):
                if axis == "x":
                    if delta > 0:
                        self.rect.right = collider.left
                    else:
                        self.rect.left = collider.right
                    self.x = float(self.rect.centerx)
                else:
                    if delta > 0:
                        self.rect.bottom = collider.top
                    else:
                        self.rect.top = collider.bottom
                    self.y = float(self.rect.centery)

    def update(
        self,
        dt: float,
        now: int,
        colliders: Iterable[pygame.Rect],
        bounds: Tuple[float, float, float, float],
    ) -> None:
        if self.target is None or now >= self.next_wander_ms:
            self.target = None

        if not self.target:
            return

        tx, ty = self.target
        dx = tx - self.x
        dy = ty - self.y
        distance = math.hypot(dx, dy)
        if distance <= 3:
            self.target = None
            return

        dx /= distance
        dy /= distance
        step_x = dx * self.speed * dt
        step_y = dy * self.speed * dt
        self._move_single_axis(step_x, "x", colliders)
        self._move_single_axis(step_y, "y", colliders)

        min_x, max_x, min_y, max_y = bounds
        self.x = max(min_x, min(max_x, self.x))
        self.y = max(min_y, min(max_y, self.y))
        self.rect.center = (int(self.x), int(self.y))

    def set_wander_target(self, target: Tuple[float, float], next_wander_ms: int) -> None:
        self.target = target
        self.next_wander_ms = next_wander_ms


class DayChaser(StaticEntity):
    def __init__(self, x: float, y: float, speed: float):
        surface = pygame.Surface((30, 46))
        surface.fill((180, 80, 80))
        pygame.draw.rect(surface, (220, 220, 220), (6, 10, 18, 18), border_radius=4)
        pygame.draw.rect(surface, (40, 40, 40), (10, 28, 12, 14), border_radius=3)
        super().__init__(surface.convert_alpha(), x, y)
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.speed = speed

    def _move_single_axis(self, delta: float, axis: str, colliders: Iterable[pygame.Rect]) -> None:
        if delta == 0:
            return
        if axis == 'x':
            self.x += delta
            self.rect.centerx = int(self.x)
        else:
            self.y += delta
            self.rect.centery = int(self.y)
        for collider in colliders:
            if self.rect.colliderect(collider):
                if axis == 'x':
                    if delta > 0:
                        self.rect.right = collider.left
                    else:
                        self.rect.left = collider.right
                    self.x = float(self.rect.centerx)
                else:
                    if delta > 0:
                        self.rect.bottom = collider.top
                    else:
                        self.rect.top = collider.bottom
                    self.y = float(self.rect.centery)

    def update(
        self,
        dt: float,
        target: Tuple[float, float],
        colliders: Iterable[pygame.Rect],
        bounds: Tuple[float, float, float, float],
        safe_center: Tuple[float, float],
        safe_radius: float,
    ) -> None:
        tx, ty = target
        dx = tx - self.x
        dy = ty - self.y
        distance = math.hypot(dx, dy)
        if distance == 0:
            return
        dx /= distance
        dy /= distance
        step_x = dx * self.speed * dt
        step_y = dy * self.speed * dt
        self._move_single_axis(step_x, 'x', colliders)
        self._move_single_axis(step_y, 'y', colliders)
        min_x, max_x, min_y, max_y = bounds
        self.x = max(min_x, min(max_x, self.x))
        self.y = max(min_y, min(max_y, self.y))
        self.rect.center = (int(self.x), int(self.y))

        cx, cy = safe_center
        radius = max(1.0, safe_radius)
        dist_to_center = math.hypot(self.x - cx, self.y - cy)
        if dist_to_center < radius:
            angle = math.atan2(self.y - cy, self.x - cx)
            push_radius = radius + 4
            self.x = cx + math.cos(angle) * push_radius
            self.y = cy + math.sin(angle) * push_radius
            self.rect.center = (int(self.x), int(self.y))

class Ghost:
    def __init__(self, x: float, y: float, speed: float):
        self.image = load_sprite("assets/sprites/ghost.bmp")
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = x
        self.y = y
        self.base_speed = speed
        self.speed = speed
        self.random_target: Optional[Tuple[float, float]] = None
        self.next_random_ms = 0

    def _move_towards(self, target: Tuple[float, float], dt: float) -> None:
        tx, ty = target
        dx = tx - self.x
        dy = ty - self.y
        distance = math.hypot(dx, dy)
        if distance == 0:
            return
        dx /= distance
        dy /= distance
        self.x += dx * self.speed * dt
        self.y += dy * self.speed * dt
        self.rect.center = (int(self.x), int(self.y))

    def update(
        self,
        dt: float,
        now: int,
        target: Optional[Tuple[float, float]] = None,
        random_speed: float = 60.0,
        random_interval: Tuple[int, int] = (800, 2000),
        random_radius: float = 120.0,
    ) -> None:
        if target:
            self.speed = self.base_speed
            self._move_towards(target, dt)
            self.random_target = None
            return

        if self.random_target:
            rx, ry = self.random_target
            if math.hypot(rx - self.x, ry - self.y) <= 4:
                self.random_target = None

        min_interval, max_interval = random_interval
        if self.random_target is None or now >= self.next_random_ms:
            angle = random.uniform(0, math.tau)
            radius = random.uniform(max(20.0, random_radius * 0.3), random_radius)
            ox = math.cos(angle) * radius
            oy = math.sin(angle) * radius
            self.random_target = (self.x + ox, self.y + oy)
            if max_interval <= min_interval:
                max_interval = min_interval + 1
            self.next_random_ms = now + random.randint(min_interval, max_interval)

        self.speed = random_speed
        if self.random_target:
            self._move_towards(self.random_target, dt)




