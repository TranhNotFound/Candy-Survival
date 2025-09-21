import math
import random
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import pygame

from core.inventory import Inventory
from core.assets import get_candy_sprite_path, get_factory_frame_paths, get_candy_display_name


def load_sprite(path: str) -> pygame.Surface:
    image = pygame.image.load(path)
    return image.convert_alpha() if image.get_alpha() is not None else image.convert()



_FRAME_INDEX_PATTERN = re.compile(r"(\d+)$")
_ALLOWED_ANIMATION_EXTS = {".png", ".bmp", ".gif"}


def _animation_frame_sort_key(path: Path) -> tuple[int, str]:
    match = _FRAME_INDEX_PATTERN.search(path.stem)
    index = int(match.group(1)) if match else 0
    return index, path.name.lower()


def load_animation_frames(folder: Path) -> List[pygame.Surface]:
    folder_path = Path(folder)
    if not folder_path.exists():
        return []
    frames: List[pygame.Surface] = []
    for candidate in sorted(
        (
            child
            for child in folder_path.iterdir()
            if child.is_file()
            and child.suffix.lower() in _ALLOWED_ANIMATION_EXTS
            and "preview" not in child.stem.lower()
        ),
        key=_animation_frame_sort_key,
    ):
        try:
            frames.append(load_sprite(str(candidate)))
        except pygame.error:
            continue
    return frames


class AnimatedSpriteController:
    def __init__(
        self,
        frame_sets: Dict[str, List[pygame.Surface]],
        target_fps: float,
        speed_scale: float = 6.0,
        flippable_states: Optional[Iterable[str]] = None,
    ) -> None:
        self.frame_sets = {state: frames for state, frames in frame_sets.items() if frames}
        self.current_state: Optional[str] = (
            next(iter(self.frame_sets)) if self.frame_sets else None
        )
        self.frame_index = 0
        self.timer = 0.0
        self.frame_duration = max(0.04, speed_scale / max(1.0, target_fps))
        self.flippable_states = set(flippable_states or [])
        self.facing_left = False

    def get_initial_frame(self) -> Optional[pygame.Surface]:
        if not self.current_state:
            return None
        return self.frame_sets[self.current_state][self.frame_index]

    def update(
        self,
        dt: float,
        state: Optional[str],
        moving: bool,
        facing_left: Optional[bool] = None,
    ) -> Optional[pygame.Surface]:
        if not self.frame_sets or not self.current_state:
            return None
        if state and state in self.frame_sets and state != self.current_state:
            self.current_state = state
            self.frame_index = 0
            self.timer = 0.0
        if facing_left is not None:
            self.facing_left = facing_left
        frames = self.frame_sets.get(self.current_state, [])
        if not frames:
            return None
        if moving and len(frames) > 1:
            self.timer += dt
            while self.timer >= self.frame_duration:
                self.timer -= self.frame_duration
                self.frame_index = (self.frame_index + 1) % len(frames)
        else:
            self.frame_index = 0
            self.timer = 0.0
        frame = frames[self.frame_index]
        if self.current_state in self.flippable_states and self.facing_left:
            frame = pygame.transform.flip(frame, True, False)
        return frame

    @property
    def current_frame(self) -> Optional[pygame.Surface]:
        if not self.frame_sets or not self.current_state:
            return None
        frame = self.frame_sets[self.current_state][self.frame_index]
        if self.current_state in self.flippable_states and self.facing_left:
            return pygame.transform.flip(frame, True, False)
        return frame


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
        target_fps: float = 60.0,
    ):
        self.x = x
        self.y = y
        self.speed = speed
        self.inventory = Inventory(inv_rows, inv_cols, max_stack)
        self.alive = True
        self._target_fps = max(1.0, float(target_fps))
        front_frames = load_animation_frames(Path("assets/sprites/NPC/Player/Front"))
        side_frames = load_animation_frames(Path("assets/sprites/NPC/Player/Side"))
        if front_frames and side_frames:
            self.animator = AnimatedSpriteController(
                {"front": front_frames, "side": side_frames},
                self._target_fps,
                flippable_states={"side"},
            )
            initial_image = self.animator.current_frame or front_frames[0]
        else:
            self.animator = None
            initial_image = load_sprite("assets/sprites/player_test.png")
        self.image = initial_image
        self.rect = self.image.get_rect(center=(int(x), int(y)))

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
        raw_dx = raw_dy = 0.0
        if inputmgr.is_pressed("move_up", keys):
            raw_dy -= 1.0
        if inputmgr.is_pressed("move_down", keys):
            raw_dy += 1.0
        if inputmgr.is_pressed("move_left", keys):
            raw_dx -= 1.0
        if inputmgr.is_pressed("move_right", keys):
            raw_dx += 1.0

        magnitude = math.hypot(raw_dx, raw_dy)
        if magnitude > 0:
            norm_dx = raw_dx / magnitude
            norm_dy = raw_dy / magnitude
        else:
            norm_dx = norm_dy = 0.0

        move_dx = norm_dx * self.speed * dt
        move_dy = norm_dy * self.speed * dt

        if colliders:
            self._move_single_axis(move_dx, "x", colliders)
            self._move_single_axis(move_dy, "y", colliders)
        else:
            self.x += move_dx
            self.y += move_dy
            self.rect.center = (int(self.x), int(self.y))

        self._update_animation(dt, norm_dx, norm_dy, magnitude > 0)


    def _update_animation(self, dt: float, dir_x: float, dir_y: float, moving: bool) -> None:
        if not getattr(self, "animator", None):
            return
        state: Optional[str] = None
        facing_left: Optional[bool] = None
        if moving:
            if abs(dir_y) >= abs(dir_x):
                state = "front"
            else:
                state = "side"
                facing_left = dir_x < 0
        frame = self.animator.update(dt, state, moving, facing_left)
        if frame:
            center = (int(self.x), int(self.y))
            self.image = frame
            self.rect = self.image.get_rect(center=center)


class ItemEntity:
    def __init__(self, item_name: str, x: float, y: float, yield_count: int = 1):
        self.item = item_name
        self.yield_count = yield_count
        sprite_path = get_candy_sprite_path(item_name)
        if not sprite_path:
            sprite_dir = Path("assets/sprites")
            png_candidate = sprite_dir / f"{item_name}.png"
            if png_candidate.exists():
                sprite_path = str(png_candidate)
            else:
                sprite_path = str(sprite_dir / f"{item_name}.bmp")
        self.image = load_sprite(sprite_path)
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
    ANIMATION_INTERVAL_MS = 220

    def __init__(
        self,
        candy_type: str,
        x: float,
        y: float,
        upgrade_costs: Dict[int, int],
        max_level: int,
        bonus_chances: Optional[Dict[int, float]] = None,
        neutral: bool = False,
        item_key: Optional[str] = None,
    ) -> None:
        frame_key = "neutral" if neutral else candy_type
        frame_paths = get_factory_frame_paths(frame_key)

        frames: List[pygame.Surface] = []
        if frame_paths:
            frames = [load_sprite(path) for path in frame_paths]
        else:
            if neutral:
                base = load_sprite("assets/sprites/machine_blue.bmp").copy()
                base.fill((180, 180, 180), special_flags=pygame.BLEND_RGB_MULT)
                frames = [base]
            else:
                frames = [load_sprite(f"assets/sprites/machine_{candy_type}.bmp")]

        super().__init__(frames[0], x, y)
        self.animation_frames = frames
        self._frame_index = 0
        self.animation_interval_ms = self.ANIMATION_INTERVAL_MS
        self._next_frame_at = 0
        self.candy_type = candy_type
        self.item_key = item_key
        self.neutral = neutral
        self.level = 1
        self.max_level = max(1, int(max_level))
        self.upgraded_today = False
        self.chat: Optional[ChatBubble] = None
        self.upgrade_costs = {int(level): int(cost) for level, cost in upgrade_costs.items()}
        self.bonus_chances = {int(level): float(chance) for level, chance in (bonus_chances or {}).items()}
        self.display_name = get_candy_display_name(self.item_key or self.candy_type)

    def update_animation(self, now: Optional[int] = None) -> None:
        if len(self.animation_frames) <= 1:
            return

        if now is None:
            now = pygame.time.get_ticks()

        if self._next_frame_at == 0:
            self._next_frame_at = now + self.animation_interval_ms

        if now < self._next_frame_at:
            return

        self._frame_index = (self._frame_index + 1) % len(self.animation_frames)
        center = self.rect.center
        self.image = self.animation_frames[self._frame_index]
        self.rect = self.image.get_rect(center=center)
        self._next_frame_at = now + self.animation_interval_ms

    def next_upgrade_cost(self) -> Optional[int]:
        next_level = self.level + 1
        if next_level > self.max_level:
            return None
        return self.upgrade_costs.get(next_level)

    def increase_level(self, levels: int = 1) -> int:
        if levels <= 0:
            return 0
        target = min(self.max_level, self.level + levels)
        delta = target - self.level
        if delta > 0:
            self.level = target
            self.upgraded_today = True
        return delta

    def decrease_level(self, levels: int = 1) -> int:
        if levels <= 0:
            return 0
        target = max(1, self.level - levels)
        delta = self.level - target
        if delta > 0:
            self.level = target
        return delta

    def bonus_chance(self) -> float:
        return self.bonus_chances.get(self.level, 0.0)

    def try_upgrade(self, stockpile, msglog, audio, world_progress) -> bool:
        cost = self.next_upgrade_cost()
        if cost is None:
            msglog.add(f"Machine {self.display_name}: already at max level.", (200, 200, 200))
            audio.sfx("fail")
            return False

        if not self.item_key:
            msglog.add(f"Machine {self.display_name}: cannot be upgraded manually.", (200, 200, 200))
            audio.sfx("fail")
            return False

        if not stockpile.consume(self.item_key, cost):
            required_label = get_candy_display_name(self.item_key)
            msglog.add(
                f"Machine {self.display_name}: missing {required_label} x{cost}.",
                (255, 120, 120),
            )
            audio.sfx("fail")
            return False

        added = self.increase_level(1)
        if added <= 0:
            msglog.add(f"Machine {self.display_name}: already at max level.", (200, 200, 200))
            audio.sfx("fail")
            return False

        world_progress.record_upgrade()
        msglog.add(
            f"Machine {self.display_name}: upgraded to level {self.level}!", (0, 255, 0)
        )
        audio.sfx("success")
        return True

    def reset_daily_state(self) -> None:
        self.upgraded_today = False

    def auto_upgrade(self, levels: int) -> int:
        return self.increase_level(max(1, levels))

class Radio(StaticEntity):
    def __init__(self, x: float, y: float):
        super().__init__(load_sprite("assets/Map/InnerWorld/Tileset/Radio.png"), x, y)
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
    def __init__(self, x: float, y: float, speed: float, target_fps: float = 60.0):
        self._target_fps = max(1.0, float(target_fps))
        front_frames = load_animation_frames(Path("assets/sprites/NPC/Boy/Front"))
        side_frames = load_animation_frames(Path("assets/sprites/NPC/Boy/Side"))
        if front_frames and side_frames:
            self.animator = AnimatedSpriteController(
                {"front": front_frames, "side": side_frames},
                self._target_fps,
                flippable_states={"side"},
            )
            initial_image = self.animator.current_frame or front_frames[0]
        else:
            self.animator = None
            placeholder = pygame.Surface((28, 44))
            placeholder.fill((120, 160, 220))
            pygame.draw.rect(placeholder, (80, 120, 180), (0, 24, 28, 20))
            pygame.draw.circle(placeholder, (240, 220, 200), (14, 12), 10)
            initial_image = placeholder.convert_alpha()
        super().__init__(initial_image, x, y)
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

        moving = False
        dir_x = dir_y = 0.0

        if not self.target:
            self._update_animation(dt, dir_x, dir_y, moving)
            return

        tx, ty = self.target
        dx = tx - self.x
        dy = ty - self.y
        distance = math.hypot(dx, dy)
        if distance <= 3:
            self.target = None
            self._update_animation(dt, dir_x, dir_y, False)
            return

        dir_x = dx / distance
        dir_y = dy / distance
        moving = True
        step_x = dir_x * self.speed * dt
        step_y = dir_y * self.speed * dt
        self._move_single_axis(step_x, "x", colliders)
        self._move_single_axis(step_y, "y", colliders)

        min_x, max_x, min_y, max_y = bounds
        self.x = max(min_x, min(max_x, self.x))
        self.y = max(min_y, min(max_y, self.y))
        self.rect.center = (int(self.x), int(self.y))

        self._update_animation(dt, dir_x, dir_y, moving)

    def set_wander_target(self, target: Tuple[float, float], next_wander_ms: int) -> None:
        self.target = target
        self.next_wander_ms = next_wander_ms


    def _update_animation(self, dt: float, dir_x: float, dir_y: float, moving: bool) -> None:
        if not getattr(self, "animator", None):
            return
        state: Optional[str] = None
        facing_left: Optional[bool] = None
        if moving:
            if abs(dir_y) >= abs(dir_x):
                state = "front"
            else:
                state = "side"
                facing_left = dir_x > 0
        frame = self.animator.update(dt, state, moving, facing_left)
        if frame:
            center = (int(self.x), int(self.y))
            self.image = frame
            self.rect = self.image.get_rect(center=center)


class DayChaser(StaticEntity):
    def __init__(self, x: float, y: float, speed: float, target_fps: float = 60.0):
        self._target_fps = max(1.0, float(target_fps))
        hunter_frames = load_animation_frames(Path("assets/sprites/NPC/Hunter"))
        if hunter_frames:
            self.animator = AnimatedSpriteController(
                {"front": hunter_frames},
                self._target_fps,
                speed_scale=40.0,
            )
            initial_image = self.animator.current_frame or hunter_frames[0]
        else:
            self.animator = None
            surface = pygame.Surface((30, 46))
            surface.fill((180, 80, 80))
            pygame.draw.rect(surface, (220, 220, 220), (6, 10, 18, 18), border_radius=4)
            pygame.draw.rect(surface, (40, 40, 40), (10, 28, 12, 14), border_radius=3)
            initial_image = surface.convert_alpha()
        super().__init__(initial_image, x, y)
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
        safe_bounds: Tuple[float, float, float, float],
    ) -> None:
        tx, ty = target
        dx = tx - self.x
        dy = ty - self.y
        distance = math.hypot(dx, dy)
        moving = distance > 0
        if moving:
            dir_x = dx / distance
            dir_y = dy / distance
            step_x = dir_x * self.speed * dt
            step_y = dir_y * self.speed * dt
            self._move_single_axis(step_x, 'x', colliders)
            self._move_single_axis(step_y, 'y', colliders)
        else:
            dir_x = dir_y = 0.0

        min_x, max_x, min_y, max_y = bounds
        self.x = max(min_x, min(max_x, self.x))
        self.y = max(min_y, min(max_y, self.y))
        self.rect.center = (int(self.x), int(self.y))

        left, top, right, bottom = safe_bounds
        if left <= self.x <= right and top <= self.y <= bottom:
            padding = 6.0
            distances = [
                (self.x - left, 'left'),
                (right - self.x, 'right'),
                (self.y - top, 'top'),
                (bottom - self.y, 'bottom'),
            ]
            side = min(distances, key=lambda item: item[0])[1]
            if side == 'left':
                self.x = left - padding
            elif side == 'right':
                self.x = right + padding
            elif side == 'top':
                self.y = top - padding
            else:
                self.y = bottom + padding
            self.rect.center = (int(self.x), int(self.y))

        self._update_animation(dt, moving)

    def _update_animation(self, dt: float, moving: bool) -> None:
        if not getattr(self, "animator", None):
            return
        frame = self.animator.update(dt, "front", moving)
        if frame:
            center = (int(self.x), int(self.y))
            self.image = frame
            self.rect = self.image.get_rect(center=center)


class Ghost:
    def __init__(self, x: float, y: float, speed: float, target_fps: float = 60.0):
        self._target_fps = max(1.0, float(target_fps))
        ghost_frames = load_animation_frames(Path("assets/sprites/NPC/Ghost"))
        if ghost_frames:
            self.animator = AnimatedSpriteController(
                {"front": ghost_frames},
                self._target_fps,
                speed_scale=40.0,
            )
            initial_image = self.animator.current_frame or ghost_frames[0]
        else:
            self.animator = None
            initial_image = load_sprite("assets/sprites/ghost.bmp")
        self.image = initial_image
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = x
        self.y = y
        self.base_speed = speed
        self.speed = speed
        self.random_target: Optional[Tuple[float, float]] = None
        self.next_random_ms = 0

    def _move_towards(self, target: Tuple[float, float], dt: float) -> bool:
        tx, ty = target
        dx = tx - self.x
        dy = ty - self.y
        distance = math.hypot(dx, dy)
        if distance == 0:
            return False
        dx /= distance
        dy /= distance
        self.x += dx * self.speed * dt
        self.y += dy * self.speed * dt
        self.rect.center = (int(self.x), int(self.y))
        return True

    def update(
        self,
        dt: float,
        now: int,
        target: Optional[Tuple[float, float]] = None,
        random_speed: float = 60.0,
        random_interval: Tuple[int, int] = (800, 2000),
        random_radius: float = 120.0,
    ) -> None:
        moved = False
        if target:
            self.speed = self.base_speed
            moved = self._move_towards(target, dt)
            self.random_target = None
        else:
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
                moved = self._move_towards(self.random_target, dt) or moved

        self._update_animation(dt, moved)


    def _update_animation(self, dt: float, moving: bool) -> None:
        if not getattr(self, "animator", None):
            return
        frame = self.animator.update(dt, "front", moving)
        if frame:
            center = (int(self.x), int(self.y))
            self.image = frame
            self.rect = self.image.get_rect(center=center)



