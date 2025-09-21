import json
import random
from typing import Iterable, List, Optional, Tuple


class TileMap:
    def __init__(self, path: str, tile_size: int):
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.tile_size = tile_size
        self.width: int = data["width"]
        self.height: int = data["height"]
        self.tiles: List[List[str]] = data["tiles"]
        self.safe_center: Tuple[int, int] = tuple(data["safe_zone_center"])
        self.safe_radius: int = data["safe_zone_radius"]
        self.candy_spawn_count: int = data.get("random_candy_spawns", 0)
        self.battery_spawn_count: int = data.get("random_battery_spawns", 0)

        self.safe_rect: Optional[Tuple[int, int, int, int]] = None
        rect_data = data.get("safe_zone_rect")
        if isinstance(rect_data, dict):
            try:
                sx = int(rect_data.get("x"))
                sy = int(rect_data.get("y"))
                sw = int(rect_data.get("width"))
                sh = int(rect_data.get("height"))
            except (TypeError, ValueError):
                pass
            else:
                if sw > 0 and sh > 0:
                    self.safe_rect = (sx, sy, sw, sh)

    def is_safe_tile(self, tile_x: int, tile_y: int) -> bool:
        return self.tiles[tile_y][tile_x] == "safe"

    def world_to_tile(self, x: float, y: float) -> Tuple[int, int]:
        return int(x // self.tile_size), int(y // self.tile_size)

    def tile_to_world_center(self, tile_x: int, tile_y: int) -> Tuple[int, int]:
        center_x = tile_x * self.tile_size + self.tile_size // 2
        center_y = tile_y * self.tile_size + self.tile_size // 2
        return center_x, center_y

    def random_positions(self, count: int, avoid_safe_zone: bool = True) -> List[Tuple[int, int]]:
        positions: List[Tuple[int, int]] = []
        attempted = 0
        max_attempts = max(2000, count * 10)
        while len(positions) < count and attempted < max_attempts:
            attempted += 1
            tile_x = random.randint(0, self.width - 1)
            tile_y = random.randint(0, self.height - 1)
            if avoid_safe_zone and self._inside_safe_zone(tile_x, tile_y):
                continue
            world = self.tile_to_world_center(tile_x, tile_y)
            if world not in positions:
                positions.append(world)
        return positions

    def _inside_safe_zone(self, tile_x: int, tile_y: int) -> bool:
        if self.safe_rect:
            sx, sy, sw, sh = self.safe_rect
            return sx <= tile_x < sx + sw and sy <= tile_y < sy + sh
        center_x, center_y = self.safe_center
        return (tile_x - center_x) ** 2 + (tile_y - center_y) ** 2 < (self.safe_radius + 1) ** 2

    @property
    def world_width(self) -> int:
        return self.width * self.tile_size

    @property
    def world_height(self) -> int:
        return self.height * self.tile_size

    def all_tile_centers(self) -> Iterable[Tuple[int, int]]:
        for tile_y in range(self.height):
            for tile_x in range(self.width):
                yield self.tile_to_world_center(tile_x, tile_y)

    @property
    def safe_rect_tiles(self) -> Optional[Tuple[int, int, int, int]]:
        return self.safe_rect

