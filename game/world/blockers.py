from __future__ import annotations

from collections import defaultdict
from enum import Enum
from typing import Iterable

import pygame

from game.entities.door import DynamicDoor


class BlockerPurpose(Enum):
    MOVEMENT = "movement"
    CREATURE_MOVEMENT = "creature_movement"
    SCAN = "scan"
    LINE_OF_SIGHT = "line_of_sight"


def _purpose_value(purpose: BlockerPurpose | str) -> str:
    return purpose.value if isinstance(purpose, BlockerPurpose) else purpose


class DynamicBlockerRegistry:
    def __init__(self, doors: Iterable[DynamicDoor] = (), tile_size: int = 48) -> None:
        self.tile_size = tile_size
        self.doors: list[DynamicDoor] = list(doors)
        self._door_tiles: dict[tuple[int, int], list[DynamicDoor]] = defaultdict(list)
        self.rebuild()

    def rebuild(self) -> None:
        self._door_tiles.clear()
        for door in self.doors:
            for tile in self._tiles_overlapping_rect(door.collision_rect):
                self._door_tiles[tile].append(door)

    def replace_doors(self, doors: Iterable[DynamicDoor]) -> None:
        self.doors = list(doors)
        self.rebuild()

    def query_rect(
        self,
        rect: pygame.Rect,
        purpose: BlockerPurpose | str = BlockerPurpose.MOVEMENT,
    ) -> list[DynamicDoor]:
        candidates: dict[str, DynamicDoor] = {}
        for tile in self._tiles_overlapping_rect(rect):
            for door in self._door_tiles.get(tile, []):
                candidates[door.door_id] = door
        return [
            door
            for door in candidates.values()
            if door.blocks_purpose(_purpose_value(purpose)) and rect.colliderect(door.collision_rect)
        ]

    def blocked_rects_for_rect(
        self,
        rect: pygame.Rect,
        purpose: BlockerPurpose | str = BlockerPurpose.MOVEMENT,
    ) -> list[pygame.Rect]:
        return [door.collision_rect for door in self.query_rect(rect, purpose)]

    def blocks_tile(
        self,
        tile_x: int,
        tile_y: int,
        purpose: BlockerPurpose | str = BlockerPurpose.MOVEMENT,
    ) -> bool:
        tile_rect = pygame.Rect(tile_x * self.tile_size, tile_y * self.tile_size, self.tile_size, self.tile_size)
        return bool(self.query_rect(tile_rect, purpose))

    def blockers_near_tile(self, tile_x: int, tile_y: int, radius: int = 1) -> list[DynamicDoor]:
        found: dict[str, DynamicDoor] = {}
        for y in range(tile_y - radius, tile_y + radius + 1):
            for x in range(tile_x - radius, tile_x + radius + 1):
                for door in self._door_tiles.get((x, y), []):
                    found[door.door_id] = door
        return list(found.values())

    def blocks_tile_transition(
        self,
        from_tile: tuple[int, int],
        to_tile: tuple[int, int],
        purpose: BlockerPurpose | str = BlockerPurpose.MOVEMENT,
    ) -> bool:
        return self.blocks_tile(*from_tile, purpose=purpose) or self.blocks_tile(*to_tile, purpose=purpose)

    def blocks_segment_tiles(
        self,
        tiles: Iterable[tuple[int, int]],
        purpose: BlockerPurpose | str = BlockerPurpose.LINE_OF_SIGHT,
    ) -> bool:
        return any(self.blocks_tile(tile_x, tile_y, purpose) for tile_x, tile_y in tiles)

    def _tiles_overlapping_rect(self, rect: pygame.Rect) -> list[tuple[int, int]]:
        left = rect.left // self.tile_size
        right = (rect.right - 1) // self.tile_size
        top = rect.top // self.tile_size
        bottom = (rect.bottom - 1) // self.tile_size
        return [(x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)]
