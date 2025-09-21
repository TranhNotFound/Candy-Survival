from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, List, Optional

ASSETS_ROOT = Path("assets") / "sprites"
CANDY_SPRITES_DIR = ASSETS_ROOT / "candy_sprites"
FACTORY_SPRITES_DIR = ASSETS_ROOT / "candy_factories_sprites"

CANDY_SPRITE_PATHS: Dict[str, str] = {
    "candy_red": str(CANDY_SPRITES_DIR / "cay.png"),
    "candy_blue": str(CANDY_SPRITES_DIR / "m\u1eb7n.png"),
    "candy_green": str(CANDY_SPRITES_DIR / "chua.png"),
    "candy_yellow": str(CANDY_SPRITES_DIR / "ng\u1ecdt.png"),
    "candy_purple": str(CANDY_SPRITES_DIR / "vovi.png"),
}

FACTORY_STATIC_PATHS: Dict[str, str] = {
    "red": str(FACTORY_SPRITES_DIR / "cay.png"),
    "green": str(FACTORY_SPRITES_DIR / "chua.png"),
    "neutral": str(FACTORY_SPRITES_DIR / "Vovi.png"),
    "purple": str(FACTORY_SPRITES_DIR / "Vovi.png"),
}

FACTORY_ANIMATION_FOLDERS: Dict[str, Path] = {
    "blue": FACTORY_SPRITES_DIR / "M\u1eb7n",
    "yellow": FACTORY_SPRITES_DIR / "Ng\u1ecdt",
}

DISPLAY_NAME_OVERRIDES: Dict[str, str] = {
    "candy_red": "Spicy",
    "red": "Spicy",
    "candy_green": "Sour",
    "green": "Sour",
    "candy_yellow": "Sweet",
    "yellow": "Sweet",
    "candy_blue": "Salty",
    "blue": "Salty",
    "candy_purple": "Tasteless",
    "purple": "Tasteless",
    "neutral": "Tasteless",
}

_FRAME_INDEX_PATTERN = re.compile(r"(\d+)(?=\.[^.]+$)")


def get_candy_sprite_path(item: str) -> Optional[str]:
    return CANDY_SPRITE_PATHS.get(item)


def get_candy_display_name(identifier: str) -> str:
    if not identifier:
        return ""

    key = identifier.lower()
    if key in DISPLAY_NAME_OVERRIDES:
        return DISPLAY_NAME_OVERRIDES[key]

    if not key.startswith("candy_"):
        candy_key = f"candy_{key}"
        if candy_key in DISPLAY_NAME_OVERRIDES:
            return DISPLAY_NAME_OVERRIDES[candy_key]
    else:
        base_key = key[6:]
        if base_key in DISPLAY_NAME_OVERRIDES:
            return DISPLAY_NAME_OVERRIDES[base_key]

    return identifier.title()


def _frame_sort_key(path: Path) -> tuple[int, str]:
    match = _FRAME_INDEX_PATTERN.search(path.name)
    index = int(match.group(1)) if match else 0
    return index, path.name


def get_factory_frame_paths(machine_type: str) -> List[str]:
    folder = FACTORY_ANIMATION_FOLDERS.get(machine_type)
    if folder and folder.exists():
        frames = sorted(folder.glob("*.png"), key=_frame_sort_key)
        if frames:
            return [str(path) for path in frames]

    static_path = FACTORY_STATIC_PATHS.get(machine_type)
    if static_path:
        return [static_path]

    return []
