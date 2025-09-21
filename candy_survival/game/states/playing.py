import json
import math
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

from core.input import InputManager
from core.resources import CandyStockpile, WorldProgression
from core.assets import get_candy_display_name
from core.ui import CraftingUI, InfoUI, InventoryUI, MessageLog, TrashUI, UIAssets
from game.audio import Audio
from game.entities import (
    CANDY_TYPES,
    CandyGiver,
    ChatBubble,
    DayChaser,
    Ghost,
    Machine,
    NPC,
    Player,
    Radio,
    CraftingTable,
    ItemEntity,
    TrashCan,
    WallSegment,
)
from game.events import (
    EventDefinition,
    EventManager,
    derive_counter_items,
    parse_event_definitions,
)
from game.map import TileMap


RECIPES = {
    "Clothes Pin": {"candy_red": 2, "candy_blue": 1, "candy_yellow": 2},
    "Paper Ship": {"candy_blue": 2, "candy_green": 2, "candy_purple": 1},
    "Dollhouse": {"candy_green": 2, "candy_yellow": 2, "candy_red": 1},
    "Umbrella": {"candy_purple": 2, "candy_red": 2, "candy_blue": 1},
}

GIVER_MESSAGES = (
    "Have some candy!",
    "Sharing sweetness!",
    "Grab your treats!",
    "Plenty of sugar for you!",
)

NPC_DIALOGUES = (
    "Lovely weather today!",
    "Have you upgraded any machines?",
    "The safe zone feels cozy!",
    "I am a fan of Sour candy!",
)

RADIO_CHATTER_LINES = (
    "Static tastes like sugar tonight.",
    "Remember to share the sweet signals!",
    "Candy machines humming, all is well.",
    "Tip of the day: keep your treats dry.",
)

CANDY_LABELS = {
    "candy_red": get_candy_display_name("candy_red"),
    "candy_blue": get_candy_display_name("candy_blue"),
    "candy_green": get_candy_display_name("candy_green"),
    "candy_yellow": get_candy_display_name("candy_yellow"),
    "candy_purple": get_candy_display_name("candy_purple"),
}

DAY_START_HOUR = 6
DAY_END_HOUR = 20


class PlayingState:
    def __init__(self, game):
        self.game = game
        self.screen = game.screen

        with open("settings.json", "r", encoding="utf-8") as handle:
            self.settings: Dict[str, float] = json.load(handle)

        self.clock = pygame.time.Clock()
        self.tile_size = self.settings["tile_size"]
        self.font = pygame.font.SysFont(None, 24)
        self.ui_assets = UIAssets("assets/sprites/ui_slot.bmp", self.font)
        self.msglog = MessageLog(self.font)
        self.inputmgr = InputManager("settings.json")

        self.audio = Audio()
        self.audio.load()
        self.audio.play_music()
        self.machine_level_data = self._parse_machine_level_data(self.settings.get("machine_level_data", {}))
        self.machine_upgrade_costs = {level: data["cost"] for level, data in self.machine_level_data.items()}
        self.machine_bonus_chances = {level: data.get("bonus_chance", 0.0) for level, data in self.machine_level_data.items()}
        self.machine_max_level = max([1, *self.machine_level_data.keys(), int(self.settings.get("machine_victory_level", 5))])
        self.event_self_dep_counter_cost = int(self.settings.get("event_self_deprecation_counter_cost", 2))
        raw_counter_items = self.settings.get("event_counter_items", [])
        if not isinstance(raw_counter_items, list):
            raw_counter_items = []
        raw_event_definitions = self.settings.get("event_definitions", [])
        if not isinstance(raw_event_definitions, list):
            raw_event_definitions = []
        self.event_definitions = parse_event_definitions(raw_event_definitions, self.event_self_dep_counter_cost)
        self.event_counter_items = derive_counter_items(raw_counter_items, self.event_definitions)
        self.event_night_delay_ms = int(self.settings.get("event_night_delay_sec", 30) * 1000)
        self.event_success_candy_reward = int(self.settings.get("event_success_candy_reward", 2))
        self.event_failure_neutral_upgrade_levels = int(self.settings.get("event_failure_neutral_upgrade_levels", 1))
        self.neutral_holder_threshold = int(self.settings.get("neutral_holder_threshold", 4))
        self.neutral_holder_min = int(self.settings.get("neutral_holder_min", -4))
        self.neutral_holder_max = int(self.settings.get("neutral_holder_max", 4))
        self.neutral_holder_no_upgrade_bonus = int(self.settings.get("neutral_holder_no_upgrade_bonus", 2))
        self.neutral_holder_upgrade_penalty = int(self.settings.get("neutral_holder_upgrade_penalty", 1))
        self.neutral_machine_upgrade_cost = int(self.settings.get("neutral_machine_upgrade_cost", 6))
        self.neutral_holder = 0

        self.tilemap = TileMap("assets/maps/map01.json", self.tile_size)
        self.safe_center_tiles = tuple(self.tilemap.safe_center)
        raw_safe_rect = self.tilemap.safe_rect_tiles
        if raw_safe_rect:
            self.safe_rect_tiles = tuple(int(value) for value in raw_safe_rect)
        else:
            radius = max(0, int(self.tilemap.safe_radius))
            cx, cy = self.safe_center_tiles
            left = max(0, cx - radius)
            top = max(0, cy - radius)
            width = min(self.tilemap.width - left, radius * 2 + 1)
            height = min(self.tilemap.height - top, radius * 2 + 1)
            self.safe_rect_tiles = (left, top, width, height)
        sx, sy, sw, sh = self.safe_rect_tiles
        self.safe_rect_world = pygame.Rect(
            sx * self.tile_size,
            sy * self.tile_size,
            sw * self.tile_size,
            sh * self.tile_size,
        )
        self.safe_center_world = (
            self.safe_rect_world.left + self.safe_rect_world.width / 2.0,
            self.safe_rect_world.top + self.safe_rect_world.height / 2.0,
        )
        self.safe_half_width = self.safe_rect_world.width / 2.0
        self.safe_half_height = self.safe_rect_world.height / 2.0
        half_tile = self.tile_size // 2
        self.world_min_x = half_tile
        self.world_max_x = self.tilemap.world_width - half_tile
        self.world_min_y = half_tile
        self.world_max_y = self.tilemap.world_height - half_tile

        hunter_tile = (max(2, self.safe_center_tiles[0] - 8), max(2, self.safe_center_tiles[1] - 8))
        self.day_hunter_spawn_world = self.tilemap.tile_to_world_center(*hunter_tile)
        self.day_hunter_home = self.day_hunter_spawn_world
        trigger_width = max(self.tile_size, int(self.safe_center_world[0] - self.tile_size))
        trigger_height = max(self.tile_size, int(self.safe_center_world[1] - self.tile_size))
        self.day_hunter_trigger_rect = pygame.Rect(0, 0, trigger_width, trigger_height)
        self.day_hunter_speed = float(self.settings.get("day_hunter_speed", self.settings["ghost_speed"]))
        self.day_hunter_engaged = False

        self.time_minutes = DAY_START_HOUR * 60
        self.day = 1
        self.game.day = self.day

        daylight_setting = self.settings.get("daylight_duration_sec")
        if daylight_setting is None:
            daylight_setting = self.settings.get("day_duration_sec", 0)
        daylight_target = float(daylight_setting or 0)
        if daylight_target > 0:
            daylight_minutes = (DAY_END_HOUR - DAY_START_HOUR) * 60
            self.base_time_speed = daylight_minutes / max(1.0, daylight_target)
            self.time_speed_multiplier = self.base_time_speed
        else:
            self.base_time_speed = self.settings["time_speed_multiplier"]
            bonus = self.settings.get("time_speed_multiplier_bonus", 1.5)
            self.time_speed_multiplier = self.base_time_speed * bonus
        self.is_night = False
        self.light_level = 0.0
        base_transition = max(1.0, self.settings["lighting_transition_sec"])
        self.night_transition_duration = base_transition * 1.5
        self.lighting_transition_rate = 1.0 / self.night_transition_duration

        self.candy_stockpile = CandyStockpile(CANDY_TYPES)
        self.world_progress = WorldProgression(
            self.settings["world_exp_per_upgrade"],
            self.settings["world_auto_upgrade_levels"],
        )
        self.npc_speed = float(self.settings.get("npc_move_speed", 80.0))

        self.player = self._create_player()
        self.info_ui = InfoUI(self.font, self.day, self.time_minutes, self.world_progress.world_exp)
        self.inv_ui = InventoryUI(self.player.inventory, self.ui_assets, pos=(10, 10))
        self.craft_ui = CraftingUI(
            RECIPES,
            self.ui_assets,
            center=(self.screen.get_width() // 2, self.screen.get_height() // 2),
            craft_callback=self._craft_recipe,
            requirement_formatter=self._format_recipe_requirement,
        )
        self.trash_ui = TrashUI(
            self.player.inventory,
            self.ui_assets,
            center=(self.screen.get_width() // 2, self.screen.get_height() // 2),
        )

        self.radio = None
        self.table = None
        self.trash_can: Optional[TrashCan] = None
        self.day_hunter: Optional[DayChaser] = None
        self.day_hunter_patrol_target: Optional[Tuple[float, float]] = None
        self.machines: List[Machine] = []
        self.machine_by_candy: Dict[str, Machine] = {}
        self.neutral_machine: Optional[Machine] = None
        self.machine_victory_level = min(int(self.settings.get("machine_victory_level", 5)), self.machine_max_level)
        self.victory_triggered = False
        self.machine_level_chat_color = (255, 255, 200)
        self._build_structures()

        self.walls: List[WallSegment] = []
        self.wall_colliders: List[pygame.Rect] = []
        self._build_walls()

        self.items: List[ItemEntity] = []
        self.candy_active_counts: Dict[str, int] = {candy: 0 for candy in CANDY_TYPES}
        self.candy_positions_pool = self.tilemap.random_positions(
            self.tilemap.candy_spawn_count,
            True,
        )
        self.available_candy_positions: List[Tuple[int, int]] = list(self.candy_positions_pool)
        self.candy_respawn_schedule: List[Tuple[int, str]] = []
        self.candy_respawns_enabled = False
        self.candy_respawn_delay_ms = int(
            self.settings["candy_respawn_delay_sec"] * 1000
        )
        self.candy_respawn_batch = max(
            1, int(self.settings["candy_respawn_batch_size"])
        )
        self.candy_max_per_type = self.settings["candy_max_per_type"]

        self.battery_positions_pool = self.tilemap.random_positions(
            self.tilemap.battery_spawn_count,
            True,
        )
        self.available_battery_positions: List[Tuple[int, int]] = list(
            self.battery_positions_pool
        )
        self.battery_respawn_schedule: List[int] = []
        self.battery_respawns_enabled = False
        self.battery_respawn_delay_ms = int(
            self.settings["battery_respawn_delay_sec"] * 1000
        )
        self.battery_respawn_batch = max(
            1, int(self.settings["battery_respawn_batch_size"])
        )
        self.battery_max_count = int(self.settings["battery_max_count"])
        self.battery_active_count = 0

        self._spawn_initial_candies()
        self._spawn_initial_batteries()

        self.givers: List[CandyGiver] = []
        self._spawn_givers()
        self.npcs: List[NPC] = []
        self._spawn_npcs()
        if not self.is_night:
            self._spawn_day_hunter()

        self.ghosts: List[Ghost] = []
        self.ghost_spawn_interval_ms = int(
            self.settings["ghost_spawn_interval_sec"] * 1000
        )
        self.ghost_max_count = int(self.settings["ghost_max_count"])
        self.ghost_random_speed = self.settings["ghost_random_walk_speed"]
        self.ghost_random_interval_ms = int(
            self.settings["ghost_random_walk_interval_sec"] * 1000
        )
        self.ghost_random_radius = (
            self.settings["ghost_random_walk_radius_tiles"] * self.tile_size
        )
        self.next_ghost_spawn_ms = 0

        self.border_shrink_speed_x = 0.0
        self.border_shrink_speed_y = 0.0
        self.border_target_half_width = self.safe_half_width
        self.border_target_half_height = self.safe_half_height
        self.border_half_width, self.border_half_height = self._initial_border_extents()
        self._recalculate_border_shrink_speed()

        self.minimap_visible = True
        self.minimap_size = (180, 140)
        self.cam_x = 0
        self.cam_y = 0

        self._tile_sprite_cache: Dict[str, pygame.Surface] = {}
        self.safe_tile_surfaces = self._load_safe_tile_images()

        self.events = EventManager(
            audio=self.audio,
            msglog=self.msglog,
            definitions=self.event_definitions,
            counter_items=self.event_counter_items,
            radio_hint_long=int(self.settings.get("radio_preannounce_with_battery_sec", 45)),
            radio_hint_short=int(self.settings.get("radio_preannounce_without_battery_sec", 10)),
            on_radio_message=self._radio_chat,
            on_radio_hint=self._on_radio_hint,
        )

        min_chatter = max(5, int(self.settings.get("radio_chatter_interval_min_sec", 35)))
        max_chatter = max(min_chatter, int(self.settings.get("radio_chatter_interval_max_sec", 75)))
        self.radio_chatter_interval_ms = (min_chatter * 1000, max_chatter * 1000)
        self.next_radio_chatter_ms: Optional[int] = None
        self.radio_chatter_color = (180, 220, 255)
        self._schedule_radio_chatter(initial=True)

        self.interaction_radius_px = self.settings["interaction_radius_tiles"] * self.tile_size
        self.crafting_radius_px = self.settings["crafting_close_radius_tiles"] * self.tile_size
        self.cutscene_until = 0

    def _create_player(self) -> Player:
        cx, cy = self.safe_center_world
        player = Player(
            cx,
            cy,
            self.settings["player_speed"],
            self.settings["inventory_rows"],
            self.settings["inventory_cols"],
            self.settings["inventory_max_stack"],
            self.settings.get("fps", 60),
        )
        return player

    def _build_structures(self) -> None:
        sx, sy, sw, sh = self.safe_rect_tiles
        def safe_tile(fx: float, fy: float) -> Tuple[int, int]:
            tile_x = int(round(sx + fx * max(0, sw - 1)))
            tile_y = int(round(sy + fy * max(0, sh - 1)))
            return self.tilemap.tile_to_world_center(tile_x, tile_y)

        machine_layout = [
            ("red", (0.2, 0.25), False, "candy_red"),
            ("blue", (0.8, 0.25), False, "candy_blue"),
            ("green", (0.2, 0.75), False, "candy_green"),
            ("yellow", (0.8, 0.75), False, "candy_yellow"),
            ("neutral", (0.5, 0.5), True, "candy_purple"),
        ]

        for machine_type, (fx, fy), is_neutral, item_key in machine_layout:
            x, y = safe_tile(fx, fy)
            machine = Machine(
                machine_type,
                x,
                y,
                dict(self.machine_upgrade_costs),
                self.machine_max_level,
                dict(self.machine_bonus_chances),
                neutral=is_neutral,
                item_key=item_key,
            )
            if is_neutral:
                machine.display_name = "Neutral"
            self.machines.append(machine)
            if is_neutral:
                self.neutral_machine = machine
                self.machine_by_candy[item_key] = machine
            else:
                self.machine_by_candy[f"candy_{machine_type}"] = machine

        radio_pos = safe_tile(0.5, 0.1)
        table_pos = safe_tile(0.85, 0.5)
        trash_pos = safe_tile(0.5, 0.9)

        self.radio = Radio(*radio_pos)
        self.table = CraftingTable(*table_pos)
        self.trash_can = TrashCan(*trash_pos)

    def _parse_machine_level_data(self, raw) -> Dict[int, Dict[str, float]]:
        data: Dict[int, Dict[str, float]] = {}
        if isinstance(raw, dict):
            for level_key, entry in raw.items():
                try:
                    level = int(level_key)
                except (TypeError, ValueError):
                    continue
                if level <= 1:
                    continue
                if not isinstance(entry, dict):
                    entry = {}
                cost = int(entry.get("cost", 0))
                chance = float(entry.get("bonus_chance", 0.0))
                data[level] = {"cost": cost, "bonus_chance": chance}
        if not data:
            data = {
                2: {"cost": 6, "bonus_chance": 0.25},
                3: {"cost": 10, "bonus_chance": 0.5},
                4: {"cost": 14, "bonus_chance": 0.75},
                5: {"cost": 20, "bonus_chance": 1.0},
            }
        return data

    def _machine_bonus_chance(self, candy_type: str) -> float:
        machine = self.machine_by_candy.get(candy_type)
        if not machine:
            return 0.0
        return machine.bonus_chance()

    def _collect_candy(self, candy_type: str, amount: int) -> Tuple[int, int]:
        total = 0
        bonus = 0
        amount = max(0, int(amount))
        for _ in range(amount):
            self.candy_stockpile.add(candy_type, 1)
            total += 1
            chance = self._machine_bonus_chance(candy_type)
            if chance > 0.0 and random.random() < chance:
                self.candy_stockpile.add(candy_type, 1)
                total += 1
                bonus += 1
        return total, bonus

    def _change_machine_level(
        self,
        machine: Machine,
        delta: int,
        reason: str,
        record_progress: bool = False,
        success_color: Tuple[int, int, int] = (0, 255, 180),
        failure_color: Tuple[int, int, int] = (255, 180, 120),
    ) -> int:
        if not machine or delta == 0:
            return 0
        if delta > 0:
            changed = machine.increase_level(delta)
            if changed and record_progress:
                for _ in range(changed):
                    self.world_progress.record_upgrade()
            if changed:
                self.msglog.add(
                    f"{reason}: {machine.display_name} -> Lv {machine.level}",
                    success_color,
                )
                self._check_machine_victory()
            return changed
        changed = machine.decrease_level(-delta)
        if changed:
            self.msglog.add(
                f"{reason}: {machine.display_name} -> Lv {machine.level}",
                failure_color,
            )
        return -changed

    def _adjust_neutral_holder(self, delta: int, reason: str = "") -> None:
        if not self.neutral_machine:
            return
        threshold = max(1, self.neutral_holder_threshold)
        holder = self.neutral_holder + delta
        leveled = False
        while holder >= threshold and self.neutral_machine.level < self.machine_max_level:
            holder -= threshold
            self._change_machine_level(
                self.neutral_machine,
                1,
                "Neutral holder boost",
                record_progress=False,
                success_color=(200, 220, 255),
            )
            leveled = True
        while holder <= -threshold and self.neutral_machine.level > 1:
            holder += threshold
            self._change_machine_level(
                self.neutral_machine,
                -1,
                "Neutral holder drain",
                record_progress=False,
                failure_color=(255, 160, 140),
            )
            leveled = True
        holder = max(self.neutral_holder_min, min(self.neutral_holder_max, holder))
        self.neutral_holder = holder
        if reason:
            self.msglog.add(
                f"Neutral holder {reason}: {self.neutral_holder}",
                (200, 220, 255),
            )
        elif leveled:
            self.msglog.add(
                f"Neutral holder adjusted: {self.neutral_holder}",
                (200, 220, 255),
            )

    def _apply_holder_day_result(self, no_upgrades: bool) -> None:
        if not self.neutral_machine:
            return
        if no_upgrades:
            delta = self.neutral_holder_no_upgrade_bonus
            if delta:
                self._adjust_neutral_holder(delta, "rose after a calm day")
        else:
            delta = -self.neutral_holder_upgrade_penalty
            if delta:
                self._adjust_neutral_holder(delta, "fell after upgrades")

    def _force_new_day(self) -> None:
        self.events.end_night()
        self.is_night = False
        self.light_level = 0.0
        self.time_minutes = DAY_START_HOUR * 60
        self.day += 1
        self.game.day = self.day
        self._begin_new_day()
        self._on_day_start()

    def _build_walls(self) -> None:
        thickness = max(1, int(self.settings["wall_thickness_tiles"] * self.tile_size))
        cx = int(round(self.safe_center_world[0]))
        cy = int(round(self.safe_center_world[1]))
        safe_gap_x = int(round(self.safe_half_width + thickness / 2))
        safe_gap_y = int(round(self.safe_half_height + thickness / 2))

        def vertical_segment(y_start: int, y_end: int) -> Optional[WallSegment]:
            height = y_end - y_start
            if height <= 0:
                return None
            center_y = y_start + height // 2
            wall = WallSegment(thickness, height, cx, center_y)
            return wall

        def horizontal_segment(x_start: int, x_end: int) -> Optional[WallSegment]:
            width = x_end - x_start
            if width <= 0:
                return None
            center_x = x_start + width // 2
            wall = WallSegment(width, thickness, center_x, cy)
            return wall

        top = vertical_segment(0, cy - safe_gap_y)
        bottom = vertical_segment(cy + safe_gap_y, self.tilemap.world_height)
        left = horizontal_segment(0, cx - safe_gap_x)
        right = horizontal_segment(cx + safe_gap_x, self.tilemap.world_width)

        for wall in (top, bottom, left, right):
            if wall:
                self.walls.append(wall)
                self.wall_colliders.append(wall.rect.copy())

    def _reserve_candy_position(self) -> Optional[Tuple[int, int]]:
        if not self.available_candy_positions:
            return None
        index = random.randrange(len(self.available_candy_positions))
        return self.available_candy_positions.pop(index)

    def _release_candy_position(self, position: Tuple[int, int]) -> None:
        self.available_candy_positions.append(position)

    def _reserve_battery_position(self) -> Optional[Tuple[int, int]]:
        if not self.available_battery_positions:
            return None
        index = random.randrange(len(self.available_battery_positions))
        return self.available_battery_positions.pop(index)

    def _release_battery_position(self, position: Tuple[int, int]) -> None:
        self.available_battery_positions.append(position)

    def _safe_bounds(self, buffer: float = 0.0) -> Tuple[float, float, float, float]:
        return (
            self.safe_rect_world.left - buffer,
            self.safe_rect_world.top - buffer,
            self.safe_rect_world.right + buffer,
            self.safe_rect_world.bottom + buffer,
        )

    @staticmethod
    def _point_in_bounds(x: float, y: float, bounds: Tuple[float, float, float, float]) -> bool:
        left, top, right, bottom = bounds
        return left <= x <= right and top <= y <= bottom

    @staticmethod
    def _push_point_outside_bounds(
        x: float,
        y: float,
        bounds: Tuple[float, float, float, float],
        padding: float,
    ) -> Tuple[float, float, bool]:
        left, top, right, bottom = bounds
        if x < left or x > right or y < top or y > bottom:
            return x, y, False
        distances = [
            (x - left, 'left'),
            (right - x, 'right'),
            (y - top, 'top'),
            (bottom - y, 'bottom'),
        ]
        side = min(distances, key=lambda item: item[0])[1]
        if side == 'left':
            x = left - padding
        elif side == 'right':
            x = right + padding
        elif side == 'top':
            y = top - padding
        else:
            y = bottom + padding
        return x, y, True

    def _is_inside_safe_zone(self, position: Tuple[float, float], buffer: float = 0.0) -> bool:
        left, top, right, bottom = self._safe_bounds(buffer)
        px, py = position
        return left <= px <= right and top <= py <= bottom

    def _keep_entity_outside_safe_zone(self, entity, buffer: float = 0.0) -> None:
        bounds = self._safe_bounds(buffer)
        new_x, new_y, moved = self._push_point_outside_bounds(entity.x, entity.y, bounds, padding=8.0)
        if not moved:
            return
        entity.x = new_x
        entity.y = new_y
        if hasattr(entity, 'rect') and entity.rect:
            entity.rect.center = (int(entity.x), int(entity.y))

    def _position_rect(self, position: Tuple[int, int]) -> pygame.Rect:
        half = self.tile_size // 2
        x = int(position[0] - half)
        y = int(position[1] - half)
        return pygame.Rect(x, y, self.tile_size, self.tile_size)

    def _is_position_blocked(self, position: Tuple[int, int]) -> bool:
        within_x = self.world_min_x <= position[0] <= self.world_max_x
        within_y = self.world_min_y <= position[1] <= self.world_max_y
        if not (within_x and within_y):
            return True
        rect = self._position_rect(position)
        for wall in self.wall_colliders:
            if rect.colliderect(wall):
                return True
        for machine in self.machines:
            if rect.colliderect(machine.rect):
                return True
        for entity in filter(None, [self.radio, self.table, getattr(self, "trash_can", None)]):
            if rect.colliderect(entity.rect):
                return True
        for giver in getattr(self, "givers", []):
            if rect.colliderect(giver.rect):
                return True
        for npc in getattr(self, "npcs", []):
            if rect.colliderect(npc.rect):
                return True
        for item in self.items:
            if item.alive and rect.colliderect(item.rect):
                return True
        return False

    def _clamp_entity_to_world(self, entity) -> None:
        entity.x = max(self.world_min_x, min(self.world_max_x, entity.x))
        entity.y = max(self.world_min_y, min(self.world_max_y, entity.y))
        entity.rect.center = (int(entity.x), int(entity.y))

    def _candy_yield_for_type(self, candy_type: str) -> int:
        machine = self.machine_by_candy.get(candy_type)
        if machine:
            return max(1, machine.level)
        return 1

    def _spawn_candy(self, candy_type: str) -> bool:
        if self.candy_active_counts[candy_type] >= self.candy_max_per_type:
            return False
        attempts = max(1, len(self.available_candy_positions))
        for _ in range(attempts):
            position = self._reserve_candy_position()
            if position is None:
                return False
            if self._is_position_blocked(position):
                self._release_candy_position(position)
                continue
            yield_count = self._candy_yield_for_type(candy_type)
            entity = ItemEntity(candy_type, *position, yield_count)
            entity.spawn_position = position
            self.items.append(entity)
            self.candy_active_counts[candy_type] += 1
            return True
        return False

    def _schedule_candy_respawn(self, candy_type: str) -> None:
        if not self.candy_respawns_enabled:
            return
        spawn_time = pygame.time.get_ticks() + self.candy_respawn_delay_ms
        self.candy_respawn_schedule.append((spawn_time, candy_type))

    def _spawn_initial_candies(self) -> None:
        initial = min(self.candy_max_per_type, self.settings["initial_candy_spawn_per_type"])
        for candy in CANDY_TYPES:
            for _ in range(initial):
                if not self._spawn_candy(candy):
                    break

    def _spawn_battery(self) -> bool:
        if self.battery_active_count >= self.battery_max_count:
            return False
        attempts = max(1, len(self.available_battery_positions))
        for _ in range(attempts):
            position = self._reserve_battery_position()
            if position is None:
                return False
            if self._is_position_blocked(position):
                self._release_battery_position(position)
                continue
            entity = ItemEntity("battery", *position, 1)
            entity.spawn_position = position
            self.items.append(entity)
            self.battery_active_count += 1
            return True
        return False

    def _schedule_battery_respawn(self) -> None:
        if not self.battery_respawns_enabled:
            return
        respawn_time = pygame.time.get_ticks() + self.battery_respawn_delay_ms
        self.battery_respawn_schedule.append(respawn_time)

    def _spawn_initial_batteries(self) -> None:
        initial = min(
            int(self.settings["initial_battery_item_count"]),
            self.battery_max_count,
        )
        for _ in range(initial):
            if not self._spawn_battery():
                break

    def _refresh_day_resources(self) -> None:
        self.candy_respawn_schedule.clear()
        self.battery_respawn_schedule.clear()

        self.available_candy_positions = list(self.candy_positions_pool)
        self.available_battery_positions = list(self.battery_positions_pool)
        self.candy_active_counts = {candy: 0 for candy in CANDY_TYPES}
        self.battery_active_count = 0

        for item in self.items:
            if item.item in CANDY_TYPES:
                self.candy_active_counts[item.item] += 1
                if item.spawn_position and item.spawn_position in self.available_candy_positions:
                    self.available_candy_positions.remove(item.spawn_position)
            elif item.item == "battery":
                self.battery_active_count += 1
                if item.spawn_position and item.spawn_position in self.available_battery_positions:
                    self.available_battery_positions.remove(item.spawn_position)

        initial_candy = min(self.candy_max_per_type, self.settings["initial_candy_spawn_per_type"])
        for candy in CANDY_TYPES:
            needed = max(0, initial_candy - self.candy_active_counts[candy])
            for _ in range(needed):
                if not self._spawn_candy(candy):
                    break

        initial_battery = min(self.battery_max_count, int(self.settings["initial_battery_item_count"]))
        missing_batteries = max(0, initial_battery - self.battery_active_count)
        for _ in range(missing_batteries):
            if not self._spawn_battery():
                break

    def _spawn_givers(self) -> None:
        count = int(self.settings["giver_count"])
        attempts = 0
        max_attempts = max(30, count * 6)
        while len(self.givers) < count and attempts < max_attempts:
            attempts += 1
            position = self.tilemap.random_positions(1, True)[0]
            if self._is_position_blocked(position):
                continue
            giver = CandyGiver(*position)
            self.givers.append(giver)

    def _spawn_npcs(self) -> None:
        count = int(self.settings["npc_max_count"])
        attempts = 0
        max_attempts = max(40, count * 8)
        while len(self.npcs) < count and attempts < max_attempts:
            attempts += 1
            position = self.tilemap.random_positions(1, True)[0]
            if self._is_position_blocked(position):
                continue
            if self._is_inside_safe_zone(position):
                continue
            npc = NPC(position[0], position[1], self.npc_speed, self.settings.get("fps", 60))
            self.npcs.append(npc)

    def _spawn_day_hunter(self) -> None:
        hx, hy = self.day_hunter_home
        if self._is_position_blocked((hx, hy)):
            fallback = self.tilemap.tile_to_world_center(max(2, self.safe_center_tiles[0] - 6), max(2, self.safe_center_tiles[1] - 10))
            if not self._is_position_blocked(fallback):
                hx, hy = fallback
        if self._is_inside_safe_zone((hx, hy)):
            bounds = self._safe_bounds()
            new_x, new_y, moved = self._push_point_outside_bounds(hx, hy, bounds, padding=4.0)
            if moved:
                hx, hy = new_x, new_y
        self.day_hunter_home = (hx, hy)
        self.day_hunter = DayChaser(hx, hy, self.day_hunter_speed, self.settings.get("fps", 60))
        self.day_hunter_patrol_target = None
        self.day_hunter_engaged = False

    def _select_hunter_patrol_target(self) -> Tuple[float, float]:
        base_x, base_y = self.day_hunter_home
        for _ in range(20):
            angle = random.uniform(-math.pi * 0.85, -math.pi * 0.15)
            radius = random.uniform(40, max(80, self.tile_size * 5))
            x = base_x + math.cos(angle) * radius
            y = base_y + math.sin(angle) * radius
            x = max(self.world_min_x, min(self.world_max_x, x))
            y = max(self.world_min_y, min(self.world_max_y, y))
            if x > self.safe_center_world[0] - self.tile_size:
                continue
            if y > self.safe_center_world[1] - self.tile_size:
                continue
            candidate = (x, y)
            if self._is_inside_safe_zone(candidate):
                continue
            if not self._is_position_blocked(candidate):
                return candidate
        return self.day_hunter_home

    def _despawn_day_hunter(self) -> None:
        self.day_hunter = None
        self.day_hunter_patrol_target = None
        self.day_hunter_engaged = False

    def _initial_border_extents(self) -> Tuple[float, float]:
        buffer_tiles = self.settings.get("night_border_start_buffer_tiles", 0.0)
        buffer_px = max(0.0, float(buffer_tiles)) * self.tile_size
        cx, cy = self.safe_center_world
        max_left = cx
        max_right = self.tilemap.world_width - cx
        max_top = cy
        max_bottom = self.tilemap.world_height - cy
        half_width = max(self.safe_half_width, max_left, max_right) + buffer_px
        half_height = max(self.safe_half_height, max_top, max_bottom) + buffer_px
        return half_width, half_height

    def _recalculate_border_shrink_speed(self) -> None:
        duration = max(0.1, self.night_transition_duration)
        diff_x = max(0.0, self.border_half_width - self.border_target_half_width)
        diff_y = max(0.0, self.border_half_height - self.border_target_half_height)
        self.border_shrink_speed_x = diff_x / duration if duration else 0.0
        self.border_shrink_speed_y = diff_y / duration if duration else 0.0

    def _current_border_bounds(self) -> Tuple[float, float, float, float]:
        cx, cy = self.safe_center_world
        half_w = self.border_half_width
        half_h = self.border_half_height
        return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)

    def _current_border_rect(self) -> pygame.Rect:
        left, top, right, bottom = self._current_border_bounds()
        left_i = int(math.floor(left))
        top_i = int(math.floor(top))
        right_i = int(math.ceil(right))
        bottom_i = int(math.ceil(bottom))
        width = max(1, right_i - left_i)
        height = max(1, bottom_i - top_i)
        return pygame.Rect(left_i, top_i, width, height)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if self.trash_ui.visible:
                if event.key == pygame.K_ESCAPE:
                    self.trash_ui.hide()
                    return
                if pygame.K_1 <= event.key <= pygame.K_9:
                    index = event.key - pygame.K_1
                    if index < len(self.player.inventory.slots):
                        removed = self.trash_ui.drop_index(index)
                        if removed:
                            self.msglog.add(
                                f"Discarded {removed.item} x{removed.count}",
                                (200, 200, 200),
                            )
                            self.audio.sfx("fail")
                        else:
                            self.msglog.add("Slot empty.", (160, 160, 160))
                    return
            if event.key == self.inputmgr.keymap.get(
                "pause", pygame.K_ESCAPE
            ) or event.key == pygame.K_ESCAPE:
                self.trash_ui.hide()
                self.game.push_state("pause")
            elif event.key == self.inputmgr.keymap.get("toggle_minimap", pygame.K_m):
                self.minimap_visible = not self.minimap_visible
            elif event.key == pygame.K_e:
                self.try_interact()
            elif self.craft_ui.visible and event.key in (
                pygame.K_1,
                pygame.K_2,
                pygame.K_3,
                pygame.K_4,
            ):
                index = event.key - pygame.K_1
                if self.craft_ui.craft_index(index):
                    self.msglog.add("Crafted successfully!", (0, 255, 0))
                    self.audio.sfx("success")
                else:
                    self.msglog.add("Craft failed!", (255, 120, 120))
                    self.audio.sfx("fail")

    def _within_interaction(self, entity, extra_radius: float = 0.0) -> bool:
        if not entity:
            return False
        px, py = self.player.rect.center
        ex, ey = entity.rect.center
        reach = self.interaction_radius_px + extra_radius + max(entity.rect.width, entity.rect.height) * 0.5
        return math.hypot(px - ex, py - ey) <= reach

    def try_interact(self) -> None:
        now = pygame.time.get_ticks()

        if self.radio and self._within_interaction(self.radio):
            self.trash_ui.hide()
            if self.player.inventory.remove("battery", 1):
                self.radio.batteries += 1
                self.events.set_long_hint(True)
                remaining = self.radio.batteries
                suffix = "s" if remaining != 1 else ""
                self.msglog.add(
                    f"Inserted battery into radio. {remaining} early alert{suffix} ready.",
                    (0, 200, 255),
                )
                self.audio.sfx("success")
                self._radio_chat(
                    f"Radio charged ({remaining} early alert{suffix}).",
                    (0, 200, 255),
                )
            else:
                self.msglog.add("No battery available!", (255, 120, 120))
                self.audio.sfx("fail")
            return

        if self.table and self._within_interaction(self.table):
            self.trash_ui.hide()
            self.craft_ui.toggle()
            return

        if self.trash_can and self._within_interaction(self.trash_can):
            self.craft_ui.visible = False
            self.trash_ui.toggle()
            return

        for machine in self.machines:
            if self._within_interaction(machine):
                self.trash_ui.hide()
                upgraded = machine.try_upgrade(
                    self.candy_stockpile,
                    self.msglog,
                    self.audio,
                    self.world_progress,
                )
                if upgraded:
                    self._check_machine_victory()
                return

        for giver in self.givers:
            if self._within_interaction(giver):
                self.trash_ui.hide()
                if giver.ready(now):
                    candy_type = random.choice(CANDY_TYPES)
                    amount = random.randint(
                        int(self.settings["giver_reward_min"]),
                        int(self.settings["giver_reward_max"]),
                    )
                    gained, bonus = self._collect_candy(candy_type, amount)
                    giver.cooldown_until = now + int(self.settings["giver_cooldown_sec"] * 1000)
                    giver.used_today = True
                    message = random.choice(GIVER_MESSAGES)
                    display = CANDY_LABELS[candy_type]
                    log_text = f"Giver: +{gained} {display} candy"
                    if bonus:
                        log_text += f" (+{bonus} bonus)"
                    self.msglog.add(log_text, (180, 220, 255))
                    self._show_chat(giver, message, (200, 160, 255))
                    self.audio.sfx("success")
                else:
                    self.msglog.add("Giver is resting.", (180, 180, 180))
                return

        for npc in self.npcs:
            if self._within_interaction(npc):
                line = random.choice(NPC_DIALOGUES)
                self._show_chat(npc, line, (255, 255, 255))
                self.msglog.add(f"NPC: {line}", (200, 200, 255))
                return

    def _show_chat(self, entity, text: str, color: Tuple[int, int, int]) -> None:
        duration = int(self.settings["npc_chat_duration_ms"])
        entity.chat = ChatBubble(text, color, pygame.time.get_ticks() + duration)

    def _radio_chat(self, text: str, color: Tuple[int, int, int]) -> None:
        if self.radio:
            self._show_chat(self.radio, text, color)

    def _on_radio_hint(self, long_hint: bool) -> None:
        if not self.radio:
            return
        if not long_hint:
            return
        if self.radio.batteries <= 0:
            self.events.set_long_hint(False)
            return

        self.radio.batteries -= 1
        remaining = self.radio.batteries
        if remaining <= 0:
            self.events.set_long_hint(False)
            self._show_chat(self.radio, "Radio battery depleted.", (200, 200, 200))
        else:
            suffix = "s" if remaining != 1 else ""
            self._show_chat(
                self.radio,
                f"{remaining} early alert{suffix} left.",
                (200, 200, 200),
            )

    def _schedule_radio_chatter(self, initial: bool = False) -> None:
        if not self.radio:
            self.next_radio_chatter_ms = None
            return

        min_ms, max_ms = self.radio_chatter_interval_ms
        if min_ms <= 0 or max_ms <= 0:
            self.next_radio_chatter_ms = None
            return

        min_bound = max(1, min_ms // 2) if initial else min_ms
        min_bound = min(min_bound, max_ms)
        delay = random.randint(min_bound, max_ms)
        self.next_radio_chatter_ms = pygame.time.get_ticks() + delay

    def _update_radio_chatter(self) -> None:
        if not self.radio or self.next_radio_chatter_ms is None:
            return

        now = pygame.time.get_ticks()
        if now < self.next_radio_chatter_ms:
            return

        if self.radio.chat and self.radio.chat.until > now:
            self._schedule_radio_chatter()
            return

        message = random.choice(RADIO_CHATTER_LINES)
        self._show_chat(self.radio, message, self.radio_chatter_color)
        self._schedule_radio_chatter()

    def _format_recipe_requirement(self, _: str, recipe: Dict[str, int]) -> str:
        parts = []
        for item, count in recipe.items():
            have = self.candy_stockpile.amount(item)
            parts.append(f"{have}/{count}")
        return " | ".join(parts)

    def _craft_recipe(self, result: str, recipe: Dict[str, int]) -> bool:
        if not self.candy_stockpile.can_afford(recipe):
            self.msglog.add("Missing ingredients!", (255, 120, 120))
            self.audio.sfx("fail")
            return False

        if (
            self.settings.get("inventory_full_craft_blocks", True)
            and not self.player.inventory.can_add(result, 1)
        ):
            self.msglog.add("Inventory full. Crafting failed!", (255, 120, 120))
            self.audio.sfx("fail")
            return False

        if not self.candy_stockpile.consume_recipe(recipe):
            return False

        leftover = self.player.inventory.add(result, 1)
        if leftover > 0:
            self.candy_stockpile.add_bulk(recipe)
            self.msglog.add("Inventory full. Crafting failed!", (255, 120, 120))
            self.audio.sfx("fail")
            return False

        return True

    def update(self, dt: float) -> None:
        if self.victory_triggered:
            return
        dt = min(dt, 0.1)
        keys = pygame.key.get_pressed()
        self.player.update(dt, self.inputmgr, keys, self.wall_colliders)
        self._clamp_entity_to_world(self.player)

        self._advance_time(dt)
        self._update_lighting(dt)
        self._update_border(dt)
        self._update_candy_respawns()
        self._update_battery_respawns()
        self._update_ghosts(dt)
        self._update_npcs(dt)
        self._update_day_hunter(dt)
        self._check_machine_victory()
        if self.victory_triggered:
            return
        self._update_machine_level_chat()
        self._update_chat_bubbles()
        self._handle_pickups()
        self._enforce_ui_ranges()
        self._update_events()
        self._update_camera()
        self._update_info_panel()

    def _advance_time(self, dt: float) -> None:
        previous_minutes = self.time_minutes
        minutes_per_second = self.time_speed_multiplier
        self.time_minutes += dt * minutes_per_second
        if self.time_minutes >= 24 * 60:
            self.time_minutes -= 24 * 60
            self.day += 1
            self.game.day = self.day
            self._begin_new_day()

        day_time = DAY_START_HOUR * 60 <= self.time_minutes < DAY_END_HOUR * 60
        if day_time and self.is_night:
            self.is_night = False
            self._on_day_start()
        elif not day_time and not self.is_night:
            self.is_night = True
            self._on_night_start()

    def _begin_new_day(self) -> None:
        no_upgrades = self.world_progress.end_of_day()
        for machine in self.machines:
            machine.reset_daily_state()
        self._apply_holder_day_result(no_upgrades)

    def _on_day_start(self) -> None:
        self.is_night = False
        self.events.end_night()
        self.msglog.add(f"Day {self.day} begins!", (200, 255, 200))
        self.ghosts.clear()
        self.border_half_width, self.border_half_height = self._initial_border_extents()
        self._recalculate_border_shrink_speed()
        self._refresh_day_resources()
        for giver in self.givers:
            giver.reset_daily()
        self.npcs = []
        self._spawn_npcs()
        self._spawn_day_hunter()
        if self.events.long_hint_enabled:
            self.events.set_long_hint(False)

    def _on_night_start(self) -> None:
        self.is_night = True
        self.events.begin_night(pygame.time.get_ticks(), self.event_night_delay_ms)
        self.msglog.add("Night falls. Stay alert!", (255, 200, 120))
        self.border_half_width, self.border_half_height = self._initial_border_extents()
        self._recalculate_border_shrink_speed()
        self.npcs = []
        self._despawn_day_hunter()
        self.next_ghost_spawn_ms = pygame.time.get_ticks() + self.ghost_spawn_interval_ms

    def _update_lighting(self, dt: float) -> None:
        target = 1.0 if self.is_night else 0.0
        if self.light_level < target:
            self.light_level = min(target, self.light_level + dt * self.lighting_transition_rate)
        elif self.light_level > target:
            self.light_level = max(target, self.light_level - dt * self.lighting_transition_rate)

    def _update_border(self, dt: float) -> None:
        if not self.is_night:
            return
        progressed = False
        if self.border_half_width > self.border_target_half_width:
            self.border_half_width = max(
                self.border_target_half_width,
                self.border_half_width - self.border_shrink_speed_x * dt,
            )
            progressed = True
        if self.border_half_height > self.border_target_half_height:
            self.border_half_height = max(
                self.border_target_half_height,
                self.border_half_height - self.border_shrink_speed_y * dt,
            )
            progressed = True
        if not progressed:
            self.border_half_width = self.border_target_half_width
            self.border_half_height = self.border_target_half_height

    def _update_candy_respawns(self) -> None:
        if not self.candy_respawns_enabled:
            return
        now = pygame.time.get_ticks()
        ready = [entry for entry in self.candy_respawn_schedule if entry[0] <= now]
        if not ready:
            return
        self.candy_respawn_schedule = [
            entry for entry in self.candy_respawn_schedule if entry[0] > now
        ]
        for _, candy_type in ready:
            spawned = 0
            while spawned < self.candy_respawn_batch and self._spawn_candy(candy_type):
                spawned += 1

    def _update_battery_respawns(self) -> None:
        if not self.battery_respawns_enabled:
            return
        if not self.battery_respawn_schedule:
            return
        now = pygame.time.get_ticks()
        ready = [time for time in self.battery_respawn_schedule if time <= now]
        if not ready:
            return
        self.battery_respawn_schedule = [
            time for time in self.battery_respawn_schedule if time > now
        ]
        for _ in ready:
            spawned = 0
            while spawned < self.battery_respawn_batch and self._spawn_battery():
                spawned += 1
            if spawned == 0:
                break

    def _spawn_ghost(self) -> None:
        left, top, right, bottom = self._current_border_bounds()
        extra = max(40.0, self.tile_size * 2.5)
        side = random.choice(("top", "bottom", "left", "right"))
        if side == "top":
            x = random.uniform(left - extra, right + extra)
            y = top - extra
        elif side == "bottom":
            x = random.uniform(left - extra, right + extra)
            y = bottom + extra
        elif side == "left":
            x = left - extra
            y = random.uniform(top - extra, bottom + extra)
        else:
            x = right + extra
            y = random.uniform(top - extra, bottom + extra)
        ghost = Ghost(x, y, self.settings["ghost_speed"], self.settings.get("fps", 60))
        self.ghosts.append(ghost)

    def _keep_ghost_outside_safe_zone(self, ghost: Ghost, player_outside_border: bool) -> None:
        bounds = self._current_border_bounds() if player_outside_border else self._safe_bounds()
        new_x, new_y, moved = self._push_point_outside_bounds(ghost.x, ghost.y, bounds, padding=4.0)
        if not moved:
            return
        ghost.x = new_x
        ghost.y = new_y
        ghost.rect.center = (int(ghost.x), int(ghost.y))
        ghost.random_target = None

    def _update_ghosts(self, dt: float) -> None:
        if not self.is_night:
            return

        now = pygame.time.get_ticks()
        if len(self.ghosts) < self.ghost_max_count and now >= self.next_ghost_spawn_ms:
            self._spawn_ghost()
            self.next_ghost_spawn_ms = now + self.ghost_spawn_interval_ms

        border_bounds = self._current_border_bounds()
        player_outside_border = not self._point_in_bounds(self.player.x, self.player.y, border_bounds)

        interval_min = max(200, self.ghost_random_interval_ms // 2)
        interval_max = max(interval_min + 1, int(self.ghost_random_interval_ms * 1.5))

        for ghost in self.ghosts:
            target = (self.player.x, self.player.y) if player_outside_border else None
            ghost.update(
                dt,
                now,
                target,
                self.ghost_random_speed,
                (interval_min, interval_max),
                self.ghost_random_radius,
            )
            self._keep_ghost_outside_safe_zone(ghost, player_outside_border)
            if ghost.rect.colliderect(self.player.rect):
                self.msglog.add("Ghost caught you outside the zone!", (255, 80, 80))
                self.audio.sfx("fail")
                self.game.change_state("menu")
                return

        self.ghosts = [
            ghost
            for ghost in self.ghosts
            if 0 <= ghost.x <= self.tilemap.world_width
            and 0 <= ghost.y <= self.tilemap.world_height
        ]

    def _update_npcs(self, dt: float) -> None:
        now = pygame.time.get_ticks()
        interval_ms = int(self.settings["npc_wander_interval_sec"] * 1000)
        radius_px = self.settings["npc_wander_radius_tiles"] * self.tile_size
        bounds = (self.world_min_x, self.world_max_x, self.world_min_y, self.world_max_y)
        for npc in self.npcs:
            if npc.target is None or now >= npc.next_wander_ms:
                attempts = 0
                while attempts < 6:
                    attempts += 1
                    angle = random.uniform(0, math.tau)
                    distance = random.uniform(30, max(40, radius_px))
                    target_x = npc.x + math.cos(angle) * distance
                    target_y = npc.y + math.sin(angle) * distance
                    target_x = max(self.world_min_x, min(self.world_max_x, target_x))
                    target_y = max(self.world_min_y, min(self.world_max_y, target_y))
                    candidate_rect = self._position_rect((target_x, target_y))
                    if any(candidate_rect.colliderect(w) for w in self.wall_colliders):
                        continue
                    npc.set_wander_target((target_x, target_y), now + interval_ms)
                    break
            npc.update(dt, now, self.wall_colliders, bounds)
            self._keep_entity_outside_safe_zone(npc)
            self._clamp_entity_to_world(npc)

    def _update_day_hunter(self, dt: float) -> None:
        if not self.day_hunter:
            return
        if self.is_night:
            self._despawn_day_hunter()
            return

        player_pos = (self.player.x, self.player.y)
        player_in_safe_zone = self._is_inside_safe_zone(player_pos)
        player_in_hunter_zone = False
        if self.day_hunter_trigger_rect.width > 0 and self.day_hunter_trigger_rect.height > 0:
            player_in_hunter_zone = self.day_hunter_trigger_rect.collidepoint(int(player_pos[0]), int(player_pos[1]))

        engaged_now = player_in_hunter_zone and not player_in_safe_zone
        if engaged_now:
            self.day_hunter_engaged = True
            self.day_hunter_patrol_target = None
        elif self.day_hunter_engaged and not engaged_now:
            self.day_hunter_engaged = False

        if self.day_hunter_engaged:
            target = player_pos
        else:
            if (
                self.day_hunter_patrol_target is None
                or math.hypot(
                    self.day_hunter.x - self.day_hunter_patrol_target[0],
                    self.day_hunter.y - self.day_hunter_patrol_target[1],
                ) <= self.tile_size
            ):
                self.day_hunter_patrol_target = self._select_hunter_patrol_target()
            target = self.day_hunter_patrol_target

        bounds = (self.world_min_x, self.world_max_x, self.world_min_y, self.world_max_y)
        self.day_hunter.update(
            dt,
            target,
            self.wall_colliders,
            bounds,
            self._safe_bounds(),
        )
        self._keep_entity_outside_safe_zone(self.day_hunter)

        if self.day_hunter_engaged and self.day_hunter.rect.colliderect(self.player.rect):
            self.msglog.add("Hunter caught you!", (255, 120, 120))
            self.audio.sfx("fail")
            self.game.change_state("menu")


    def _update_machine_level_chat(self) -> None:
        now = pygame.time.get_ticks()
        extra_reach = self.tile_size * 0.5
        for machine in self.machines:
            if machine is None:
                continue
            if self._within_interaction(machine, extra_reach):
                text = f"Lv {machine.level}"
                expires = now + 400
                if machine.chat and machine.chat.text == text:
                    machine.chat.until = expires
                else:
                    machine.chat = ChatBubble(text, self.machine_level_chat_color, expires)
            elif machine.chat and machine.chat.text.startswith("Lv "):
                machine.chat = None

    def _check_machine_victory(self) -> None:
        if self.victory_triggered:
            return

        for machine in (m for m in self.machines if m):
            if machine.level >= self.machine_victory_level:
                self.victory_triggered = True
                message = f"Machine {machine.display_name} reached level {machine.level}!"
                self.msglog.add(message, (0, 255, 180))
                self.audio.sfx("success")
                self._show_chat(machine, "Production maxed!", (0, 255, 180))
                self.game.change_state("menu")
                return

    def _update_chat_bubbles(self) -> None:
        now = pygame.time.get_ticks()
        for entity in [self.radio, *self.givers, *self.npcs, *self.machines]:
            if entity and entity.chat and now >= entity.chat.until:
                entity.chat = None

    def _handle_pickups(self) -> None:
        remaining_items: List[ItemEntity] = []
        for item in self.items:
            if not item.alive:
                continue
            if not self.player.rect.colliderect(item.rect):
                remaining_items.append(item)
                continue

            if item.item in CANDY_TYPES:
                gained, bonus = self._collect_candy(item.item, item.yield_count)
                self.candy_active_counts[item.item] = max(
                    0, self.candy_active_counts[item.item] - 1
                )
                if item.spawn_position:
                    self._release_candy_position(item.spawn_position)
                if bonus:
                    self.msglog.add(
                        f"Machine bonus: +{bonus} {CANDY_LABELS[item.item]} candy",
                        (200, 255, 160),
                    )
                self.audio.sfx("pickup")
                continue

            leftover = self.player.inventory.add(item.item, item.yield_count)
            if leftover == 0:
                if item.item == "battery":
                    self.battery_active_count = max(0, self.battery_active_count - 1)
                    if item.spawn_position:
                        self._release_battery_position(item.spawn_position)
                self.audio.sfx("pickup")
            else:
                remaining_items.append(item)

        self.items = remaining_items


    def _enforce_ui_ranges(self) -> None:
        if self.craft_ui.visible and not (self.table and self._within_interaction(self.table)):
            self.craft_ui.visible = False
        if self.trash_ui.visible and not (self.trash_can and self._within_interaction(self.trash_can)):
            self.trash_ui.hide()

    def _update_events(self) -> None:
        result = self.events.update(self.player.inventory)
        if not result or result[0] != "event":
            return

        _, event_def, success, detail = result
        if success:
            rewards = []
            for candy in CANDY_TYPES:
                gained, bonus = self._collect_candy(candy, self.event_success_candy_reward)
                label = CANDY_LABELS[candy]
                if bonus:
                    rewards.append(f"{label} +{gained} (+{bonus})")
                else:
                    rewards.append(f"{label} +{gained}")
            reward_text = ", ".join(rewards)
            self.msglog.add(
                f"Event '{event_def.label}' resolved! Rewards: {reward_text}.",
                (0, 255, 0),
            )
            self.audio.sfx("success")
        else:
            self.audio.sfx("fail")
            if self.neutral_machine:
                levels = max(1, self.event_failure_neutral_upgrade_levels)
                changed = self._change_machine_level(
                    self.neutral_machine,
                    levels,
                    "Event backlash",
                    record_progress=True,
                    success_color=(255, 200, 120),
                )
                if changed <= 0:
                    self.msglog.add(
                        f"Event '{event_def.label}' could not empower the neutral machine further.",
                        (255, 180, 120),
                    )
        self._force_new_day()

    def _update_camera(self) -> None:
        map_width = self.tilemap.world_width
        map_height = self.tilemap.world_height
        screen_w, screen_h = self.screen.get_size()
        self.cam_x = max(0, min(map_width - screen_w, int(self.player.x - screen_w // 2)))
        self.cam_y = max(0, min(map_height - screen_h, int(self.player.y - screen_h // 2)))

    def _update_info_panel(self) -> None:
        countdown = (
            self.events.seconds_until_event()
            if self.settings.get("radio_event_countdown_display", False)
            else None
        )
        self.info_ui.update(self.day, self.time_minutes, self.world_progress.world_exp, countdown)

    def draw(self, surface: pygame.Surface) -> None:
        camx, camy = self.cam_x, self.cam_y
        screen_w, screen_h = surface.get_size()

        tile_start_x = max(0, camx // self.tile_size)
        tile_start_y = max(0, camy // self.tile_size)
        tile_end_x = min(self.tilemap.width, (camx + screen_w) // self.tile_size + 2)
        tile_end_y = min(self.tilemap.height, (camy + screen_h) // self.tile_size + 2)

        for tile_y in range(tile_start_y, tile_end_y):
            for tile_x in range(tile_start_x, tile_end_x):
                tile = self.tilemap.tiles[tile_y][tile_x]
                sprite = self._get_tile_sprite(tile, tile_x, tile_y)
                surface.blit(
                    sprite,
                    (
                        tile_x * self.tile_size - camx,
                        tile_y * self.tile_size - camy,
                    ),
                )

        for wall in self.walls:
            surface.blit(wall.image, wall.rect.move(-camx, -camy))

        for giver in self.givers:
            surface.blit(giver.image, giver.rect.move(-camx, -camy))
        for npc in self.npcs:
            surface.blit(npc.image, npc.rect.move(-camx, -camy))
        if self.day_hunter and not self.is_night:
            surface.blit(self.day_hunter.image, self.day_hunter.rect.move(-camx, -camy))
        for item in self.items:
            surface.blit(item.image, item.rect.move(-camx, -camy))

        machine_now = pygame.time.get_ticks()
        for machine in self.machines:
            machine.update_animation(machine_now)
            surface.blit(machine.image, machine.rect.move(-camx, -camy))
        surface.blit(self.radio.image, self.radio.rect.move(-camx, -camy))
        surface.blit(self.table.image, self.table.rect.move(-camx, -camy))
        if self.trash_can:
            surface.blit(self.trash_can.image, self.trash_can.rect.move(-camx, -camy))
        surface.blit(self.player.image, self.player.rect.move(-camx, -camy))

        if self.is_night or self.light_level > 0:
            overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            alpha = int(220 * self.light_level)
            overlay.fill((0, 0, 0, alpha))
            safe_rect = pygame.Rect(
                int(self.safe_rect_world.left - camx),
                int(self.safe_rect_world.top - camy),
                self.safe_rect_world.width,
                self.safe_rect_world.height,
            )
            pygame.draw.rect(overlay, (0, 0, 0, 0), safe_rect)
            surface.blit(overlay, (0, 0))

        for ghost in self.ghosts:
            surface.blit(ghost.image, ghost.rect.move(-camx, -camy))

        self._draw_chat_bubbles(surface, camx, camy)
        self._draw_border(surface, camx, camy)

        self._draw_inventory(surface)

        self.craft_ui.center = (screen_w // 2, screen_h // 2)
        self.craft_ui.draw(surface)
        self.trash_ui.center = (screen_w // 2, screen_h // 2)
        self.trash_ui.draw(surface)

        self.msglog.draw(surface, pos=(10, screen_h - 180))
        self._draw_minimap(surface)
        self.info_ui.draw(surface)
        self._draw_candy_panel(surface)

        if self.cutscene_until > pygame.time.get_ticks():
            blackout = pygame.Surface(surface.get_size())
            blackout.fill((0, 0, 0))
            surface.blit(blackout, (0, 0))

    def _draw_inventory(self, surface: pygame.Surface) -> None:
        cols = self.player.inventory.cols
        slot = self.inv_ui.slot_size
        pad = self.inv_ui.pad
        total_width = cols * (slot + pad) - pad
        screen_w, screen_h = surface.get_size()
        x0 = screen_w // 2 - total_width // 2
        y0 = screen_h - slot - 12
        self.inv_ui.pos = (x0, y0)
        self.inv_ui.draw(surface)

    def _draw_minimap(self, surface: pygame.Surface) -> None:
        if not self.minimap_visible:
            return
        mmw, mmh = self.minimap_size
        minimap = pygame.Surface((mmw, mmh))
        minimap.fill((25, 30, 35))
        scale_x = mmw / self.tilemap.world_width
        scale_y = mmh / self.tilemap.world_height
        cx, cy = self.safe_center_world
        safe_rect = pygame.Rect(
            int(self.safe_rect_world.left * scale_x),
            int(self.safe_rect_world.top * scale_y),
            max(1, int(self.safe_rect_world.width * scale_x)),
            max(1, int(self.safe_rect_world.height * scale_y)),
        )
        pygame.draw.rect(minimap, (40, 120, 180), safe_rect, 2)
        if self.is_night:
            left, top, right, bottom = self._current_border_bounds()
            border_rect = pygame.Rect(
                int(left * scale_x),
                int(top * scale_y),
                max(1, int((right - left) * scale_x)),
                max(1, int((bottom - top) * scale_y)),
            )
            pygame.draw.rect(minimap, (200, 50, 50), border_rect, 1)
        pygame.draw.rect(
            minimap,
            (255, 255, 0),
            (
                int(self.player.x * scale_x) - 2,
                int(self.player.y * scale_y) - 2,
                4,
                4,
            ),
        )
        surface.blit(minimap, (surface.get_width() - mmw - 12, 12))

    def _draw_candy_panel(self, surface: pygame.Surface) -> None:
        entries = len(CANDY_TYPES)
        width = 180
        height = 20 + entries * 18
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill((20, 20, 30, 200))
        surface.blit(panel, (surface.get_width() - width - 12, surface.get_height() - height - 12))
        y = surface.get_height() - height - 12 + 8
        x = surface.get_width() - width - 12 + 10
        for candy in CANDY_TYPES:
            count = self.candy_stockpile.amount(candy)
            label = CANDY_LABELS[candy]
            text = self.font.render(f"{label}: {count}", True, (255, 255, 255))
            surface.blit(text, (x, y))
            y += 18

    def _draw_border(self, surface: pygame.Surface, camx: int, camy: int) -> None:
        if not self.is_night:
            return
        border_rect = self._current_border_rect().move(-camx, -camy)
        pygame.draw.rect(surface, (255, 120, 80), border_rect, 1)

    def _draw_chat_bubbles(self, surface: pygame.Surface, camx: int, camy: int) -> None:
        chat_entities = [self.radio, *self.givers, *self.npcs, *self.machines]
        for entity in chat_entities:
            if entity and entity.chat:
                text = self.font.render(entity.chat.text, True, entity.chat.color)
                padding = 6
                bubble = pygame.Surface(
                    (text.get_width() + padding * 2, text.get_height() + padding * 2),
                    pygame.SRCALPHA,
                )
                bubble.fill((20, 20, 20, 220))
                bubble.blit(text, (padding, padding))
                rect = bubble.get_rect(
                    midbottom=(entity.rect.centerx - camx, entity.rect.top - camy - 4)
                )
                surface.blit(bubble, rect)

    def _load_safe_tile_images(self) -> Dict[str, pygame.Surface]:
        tileset_dir = Path("assets/Map/InnerWorld/Tileset/Sàn")
        filenames = {
            "interior": "grass.png",
            "top": "Sàn cỏ - ngang trên.png",
            "bottom": "Sàn cỏ ngang dưới.png",
            "left": "Sàn cỏ - cạnh trái.png",
            "right": "Sàn cỏ - cạnh phải.png",
            "corner_tl": "Sàn cỏ - góc trên trái.png",
            "corner_tr": "Sàn cỏ - góc phải trên.png",
            "corner_bl": "Sàn cỏ - góc trái dưới.png",
            "corner_br": "Sàn cỏ - góc phải dưới.png",
        }
        images: Dict[str, pygame.Surface] = {}
        for key, filename in filenames.items():
            path_obj = tileset_dir / filename
            try:
                surface = pygame.image.load(str(path_obj)).convert_alpha()
            except pygame.error:
                fallback = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
                fallback.fill((80, 160, 80))
                surface = fallback
            else:
                if surface.get_size() != (self.tile_size, self.tile_size):
                    surface = pygame.transform.scale(surface, (self.tile_size, self.tile_size))
            images[key] = surface
        if "interior" not in images:
            fallback = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
            fallback.fill((80, 160, 80))
            images["interior"] = fallback
        return images

    def _safe_tile_sprite(self, tile_x: int, tile_y: int) -> pygame.Surface:
        images = getattr(self, "safe_tile_surfaces", {})
        if not images:
            fallback = pygame.Surface((self.tile_size, self.tile_size))
            fallback.fill((80, 160, 80))
            return fallback.convert()
        interior = images.get("interior")
        if interior is None:
            fallback = pygame.Surface((self.tile_size, self.tile_size))
            fallback.fill((80, 160, 80))
            interior = fallback.convert()
            images["interior"] = interior
        rect = getattr(self, "safe_rect_tiles", None)
        if rect is None:
            return interior
        sx, sy, sw, sh = rect
        ex = sx + sw - 1
        ey = sy + sh - 1
        if tile_x == sx and tile_y == sy:
            key = "corner_tl"
        elif tile_x == ex and tile_y == sy:
            key = "corner_tr"
        elif tile_x == sx and tile_y == ey:
            key = "corner_bl"
        elif tile_x == ex and tile_y == ey:
            key = "corner_br"
        elif tile_y == sy:
            key = "top"
        elif tile_y == ey:
            key = "bottom"
        elif tile_x == sx:
            key = "left"
        elif tile_x == ex:
            key = "right"
        else:
            key = "interior"
        return images.get(key, interior)

    def _get_tile_sprite(self, tile_name: str, tile_x: int, tile_y: int) -> pygame.Surface:
        if tile_name == "safe":
            return self._safe_tile_sprite(tile_x, tile_y)
        sprites_dir = Path("assets/sprites")
        if tile_name == "grass":
            candidate = sprites_dir / "tile_grass.bmp"
        else:
            candidate = sprites_dir / f"{tile_name}.bmp"
            if not candidate.exists():
                candidate = sprites_dir / "tile_grass.bmp"
        cache_key = candidate.as_posix()
        sprite = self._tile_sprite_cache.get(cache_key)
        if sprite is None:
            try:
                sprite = pygame.image.load(str(candidate)).convert()
            except pygame.error:
                fallback = pygame.Surface((self.tile_size, self.tile_size))
                fallback.fill((50, 150, 50))
                sprite = fallback.convert()
            if sprite.get_size() != (self.tile_size, self.tile_size):
                sprite = pygame.transform.scale(sprite, (self.tile_size, self.tile_size))
            self._tile_sprite_cache[cache_key] = sprite
        return sprite
































