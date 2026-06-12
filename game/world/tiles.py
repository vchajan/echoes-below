from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class TileType(IntEnum):
    VOID = 0
    FLOOR = 1
    FLOOR_ALT = 2
    DAMAGED_FLOOR = 3
    WALL = 4
    DAMAGED_WALL = 5
    OBSTACLE = 6
    PILLAR = 7
    DOORWAY = 8
    ELEVATOR_FLOOR = 9


@dataclass(frozen=True)
class TileDefinition:
    walkable: bool
    blocks_movement: bool
    blocks_scan: bool
    asset_index: int
    debug_color: tuple[int, int, int]
    debug_char: str


TILE_DEFINITIONS: dict[TileType, TileDefinition] = {
    TileType.VOID: TileDefinition(False, True, True, 11, (2, 3, 6), " "),
    TileType.FLOOR: TileDefinition(True, False, False, 0, (34, 42, 48), "."),
    TileType.FLOOR_ALT: TileDefinition(True, False, False, 1, (41, 50, 56), ","),
    TileType.DAMAGED_FLOOR: TileDefinition(True, False, False, 2, (48, 44, 45), ";"),
    TileType.WALL: TileDefinition(False, True, True, 3, (85, 92, 96), "#"),
    TileType.DAMAGED_WALL: TileDefinition(False, True, True, 4, (96, 82, 75), "%"),
    TileType.OBSTACLE: TileDefinition(False, True, True, 5, (70, 82, 82), "X"),
    TileType.PILLAR: TileDefinition(False, True, True, 6, (92, 98, 100), "O"),
    TileType.DOORWAY: TileDefinition(True, False, False, 7, (42, 93, 101), "+"),
    TileType.ELEVATOR_FLOOR: TileDefinition(True, False, False, 8, (54, 128, 132), "E"),
}


def tile_definition(tile: TileType | int) -> TileDefinition:
    return TILE_DEFINITIONS[TileType(tile)]


def is_walkable(tile: TileType | int) -> bool:
    return tile_definition(tile).walkable


def blocks_movement(tile: TileType | int) -> bool:
    return tile_definition(tile).blocks_movement


def blocks_scan(tile: TileType | int) -> bool:
    return tile_definition(tile).blocks_scan


def tile_asset_index(tile: TileType | int) -> int:
    return tile_definition(tile).asset_index


def debug_color(tile: TileType | int) -> tuple[int, int, int]:
    return tile_definition(tile).debug_color
