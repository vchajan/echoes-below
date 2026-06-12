from __future__ import annotations

import math

import pygame

from game.world.tiles import blocks_movement


def world_to_tile(position: tuple[float, float] | pygame.Vector2, tile_size: int) -> tuple[int, int]:
    x, y = position
    return (math.floor(x / tile_size), math.floor(y / tile_size))


def tile_to_world_rect(tile_x: int, tile_y: int, tile_size: int) -> pygame.Rect:
    return pygame.Rect(tile_x * tile_size, tile_y * tile_size, tile_size, tile_size)


def tile_in_bounds(generated_floor, tile_x: int, tile_y: int) -> bool:
    return 0 <= tile_x < generated_floor.width and 0 <= tile_y < generated_floor.height


def is_blocking_tile(generated_floor, tile_x: int, tile_y: int) -> bool:
    if not tile_in_bounds(generated_floor, tile_x, tile_y):
        return True
    return blocks_movement(generated_floor.tile_at(tile_x, tile_y))


def tiles_overlapping_rect(rect: pygame.Rect, tile_size: int) -> list[tuple[int, int]]:
    left = math.floor(rect.left / tile_size)
    right = math.floor((rect.right - 1) / tile_size)
    top = math.floor(rect.top / tile_size)
    bottom = math.floor((rect.bottom - 1) / tile_size)
    return [(x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)]


def blocking_rects_for_rect(generated_floor, rect: pygame.Rect, tile_size: int) -> list[pygame.Rect]:
    blockers: list[pygame.Rect] = []
    for tile_x, tile_y in tiles_overlapping_rect(rect, tile_size):
        if is_blocking_tile(generated_floor, tile_x, tile_y):
            blockers.append(tile_to_world_rect(tile_x, tile_y, tile_size))
    return blockers


def all_blocking_rects_for_rect(
    generated_floor,
    rect: pygame.Rect,
    tile_size: int,
    dynamic_blockers=None,
    purpose: object = "movement",
) -> list[pygame.Rect]:
    blockers = blocking_rects_for_rect(generated_floor, rect, tile_size)
    if dynamic_blockers is not None:
        blockers.extend(dynamic_blockers.blocked_rects_for_rect(rect, purpose))
    return blockers


def resolve_axis(
    rect: pygame.Rect,
    delta: float,
    axis: str,
    generated_floor,
    tile_size: int,
    dynamic_blockers=None,
    purpose: object = "movement",
) -> tuple[pygame.Rect, bool]:
    moved = rect.copy()
    if axis == "x":
        moved.x += round(delta)
    elif axis == "y":
        moved.y += round(delta)
    else:
        raise ValueError("axis must be 'x' or 'y'")

    collided = False
    for blocker in all_blocking_rects_for_rect(generated_floor, moved, tile_size, dynamic_blockers, purpose):
        if not moved.colliderect(blocker):
            continue
        collided = True
        if axis == "x":
            if delta > 0:
                moved.right = blocker.left
            elif delta < 0:
                moved.left = blocker.right
        else:
            if delta > 0:
                moved.bottom = blocker.top
            elif delta < 0:
                moved.top = blocker.bottom
    return moved, collided
