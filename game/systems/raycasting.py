from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

import pygame

from game.world.blockers import BlockerPurpose, DynamicBlockerRegistry
from game.world.tiles import TileType, blocks_scan

_EPSILON = 1e-9
_CORNER_EPSILON = 1e-7


class TileFloor(Protocol):
    width: int
    height: int

    def tile_at(self, tile_x: int, tile_y: int) -> TileType: ...


@dataclass(frozen=True)
class RayHit:
    scan_id: int
    ray_index: int
    ray_count: int
    angle: float
    world_position: tuple[float, float]
    distance: float
    tile: tuple[int, int]
    category: str
    blocker_id: str | None = None
    side: str = "unknown"


_TILE_CATEGORIES: dict[TileType, str] = {
    TileType.VOID: "void_boundary",
    TileType.WALL: "wall",
    TileType.DAMAGED_WALL: "damaged_wall",
    TileType.OBSTACLE: "obstacle",
    TileType.PILLAR: "pillar",
}


def _in_bounds(floor: TileFloor, tile_x: int, tile_y: int) -> bool:
    return 0 <= tile_x < floor.width and 0 <= tile_y < floor.height


def _tile_at_or_void(floor: TileFloor, tile_x: int, tile_y: int) -> TileType:
    if not _in_bounds(floor, tile_x, tile_y):
        return TileType.VOID
    return TileType(floor.tile_at(tile_x, tile_y))


def _tile_category(tile: TileType) -> str:
    return _TILE_CATEGORIES.get(tile, tile.name.lower())


def _door_category(door: object) -> str:
    door_type = getattr(getattr(door, "door_type", None), "value", None)
    if door_type:
        return f"{door_type}_door"
    return "dynamic_door"


def ray_rect_intersection_distance(
    origin: pygame.Vector2 | tuple[float, float],
    direction: pygame.Vector2 | tuple[float, float],
    rect: pygame.Rect,
    max_distance: float,
) -> float | None:
    """Return the first non-negative distance where a normalised ray enters rect."""
    start = pygame.Vector2(origin)
    ray = pygame.Vector2(direction)
    if ray.length_squared() <= _EPSILON:
        return None
    ray = ray.normalize()

    t_min = -math.inf
    t_max = math.inf
    for position, component, low, high in (
        (start.x, ray.x, float(rect.left), float(rect.right)),
        (start.y, ray.y, float(rect.top), float(rect.bottom)),
    ):
        if abs(component) <= _EPSILON:
            if position < low or position > high:
                return None
            continue
        first = (low - position) / component
        second = (high - position) / component
        if first > second:
            first, second = second, first
        t_min = max(t_min, first)
        t_max = min(t_max, second)
        if t_min - t_max > _EPSILON:
            return None

    if t_max < -_EPSILON:
        return None
    distance = max(0.0, t_min)
    if distance <= max_distance + _EPSILON:
        return distance
    return None


def _dynamic_hit_in_tile(
    origin: pygame.Vector2,
    direction: pygame.Vector2,
    tile: tuple[int, int],
    dynamic_blockers: DynamicBlockerRegistry | None,
    max_distance: float,
    purpose: BlockerPurpose,
) -> tuple[float, object] | None:
    if dynamic_blockers is None:
        return None
    nearest: tuple[float, object] | None = None
    for door in dynamic_blockers.blockers_near_tile(*tile, radius=0):
        if not door.blocks_purpose(purpose):
            continue
        distance = ray_rect_intersection_distance(origin, direction, door.collision_rect, max_distance)
        if distance is None:
            continue
        if nearest is None or distance < nearest[0]:
            nearest = (distance, door)
    return nearest


def _make_static_hit(
    *,
    scan_id: int,
    ray_index: int,
    ray_count: int,
    angle: float,
    origin: pygame.Vector2,
    direction: pygame.Vector2,
    distance: float,
    tile: tuple[int, int],
    tile_type: TileType,
    side: str,
) -> RayHit:
    point = origin + direction * max(0.0, distance)
    return RayHit(
        scan_id=scan_id,
        ray_index=ray_index,
        ray_count=ray_count,
        angle=angle,
        world_position=(float(point.x), float(point.y)),
        distance=max(0.0, float(distance)),
        tile=tile,
        category=_tile_category(tile_type),
        side=side,
    )


def _make_dynamic_hit(
    *,
    scan_id: int,
    ray_index: int,
    ray_count: int,
    angle: float,
    origin: pygame.Vector2,
    direction: pygame.Vector2,
    distance: float,
    tile: tuple[int, int],
    door: object,
) -> RayHit:
    point = origin + direction * max(0.0, distance)
    orientation = getattr(door, "orientation", "unknown")
    side = "vertical" if orientation == "vertical_door_plane" else "horizontal"
    return RayHit(
        scan_id=scan_id,
        ray_index=ray_index,
        ray_count=ray_count,
        angle=angle,
        world_position=(float(point.x), float(point.y)),
        distance=max(0.0, float(distance)),
        tile=tile,
        category=_door_category(door),
        blocker_id=str(getattr(door, "door_id", getattr(door, "unique_id", "door"))),
        side=side,
    )


def cast_ray(
    origin: pygame.Vector2 | tuple[float, float],
    angle: float,
    floor: TileFloor,
    dynamic_blockers: DynamicBlockerRegistry | None,
    tile_size: int,
    max_distance: float,
    *,
    scan_id: int = 0,
    ray_index: int = 0,
    ray_count: int = 1,
    purpose: BlockerPurpose = BlockerPurpose.SCAN,
) -> RayHit | None:
    """Cast one world-space ray with grid DDA and conservative corner blocking."""
    start = pygame.Vector2(origin)
    direction = pygame.Vector2(math.cos(angle), math.sin(angle))
    if max_distance <= 0:
        return None

    map_x = math.floor(start.x / tile_size)
    map_y = math.floor(start.y / tile_size)

    if not _in_bounds(floor, map_x, map_y):
        return _make_static_hit(
            scan_id=scan_id,
            ray_index=ray_index,
            ray_count=ray_count,
            angle=angle,
            origin=start,
            direction=direction,
            distance=0.0,
            tile=(map_x, map_y),
            tile_type=TileType.VOID,
            side="origin",
        )

    origin_tile = _tile_at_or_void(floor, map_x, map_y)
    if blocks_scan(origin_tile):
        return _make_static_hit(
            scan_id=scan_id,
            ray_index=ray_index,
            ray_count=ray_count,
            angle=angle,
            origin=start,
            direction=direction,
            distance=0.0,
            tile=(map_x, map_y),
            tile_type=origin_tile,
            side="origin",
        )

    dynamic_origin_hit = _dynamic_hit_in_tile(
        start, direction, (map_x, map_y), dynamic_blockers, max_distance, purpose
    )
    if dynamic_origin_hit is not None:
        distance, door = dynamic_origin_hit
        return _make_dynamic_hit(
            scan_id=scan_id,
            ray_index=ray_index,
            ray_count=ray_count,
            angle=angle,
            origin=start,
            direction=direction,
            distance=distance,
            tile=(map_x, map_y),
            door=door,
        )

    if direction.x > _EPSILON:
        step_x = 1
        side_x = (((map_x + 1) * tile_size) - start.x) / direction.x
        delta_x = tile_size / direction.x
    elif direction.x < -_EPSILON:
        step_x = -1
        side_x = (start.x - map_x * tile_size) / -direction.x
        delta_x = tile_size / -direction.x
    else:
        step_x = 0
        side_x = math.inf
        delta_x = math.inf

    if direction.y > _EPSILON:
        step_y = 1
        side_y = (((map_y + 1) * tile_size) - start.y) / direction.y
        delta_y = tile_size / direction.y
    elif direction.y < -_EPSILON:
        step_y = -1
        side_y = (start.y - map_y * tile_size) / -direction.y
        delta_y = tile_size / -direction.y
    else:
        step_y = 0
        side_y = math.inf
        delta_y = math.inf

    # A ray can cross at most roughly width + height tiles before leaving the map.
    max_steps = floor.width + floor.height + 8
    for _ in range(max_steps):
        if min(side_x, side_y) > max_distance + _EPSILON:
            return None

        is_corner = abs(side_x - side_y) <= _CORNER_EPSILON
        if is_corner:
            distance = side_x
            adjacent_tiles = ((map_x + step_x, map_y), (map_x, map_y + step_y))
            for adjacent in adjacent_tiles:
                tile_type = _tile_at_or_void(floor, *adjacent)
                if blocks_scan(tile_type):
                    return _make_static_hit(
                        scan_id=scan_id,
                        ray_index=ray_index,
                        ray_count=ray_count,
                        angle=angle,
                        origin=start,
                        direction=direction,
                        distance=distance,
                        tile=adjacent,
                        tile_type=tile_type,
                        side="corner",
                    )
                dynamic_hit = _dynamic_hit_in_tile(
                    start, direction, adjacent, dynamic_blockers, distance + _CORNER_EPSILON, purpose
                )
                if dynamic_hit is not None and dynamic_hit[0] <= distance + _CORNER_EPSILON:
                    dynamic_distance, door = dynamic_hit
                    return _make_dynamic_hit(
                        scan_id=scan_id,
                        ray_index=ray_index,
                        ray_count=ray_count,
                        angle=angle,
                        origin=start,
                        direction=direction,
                        distance=dynamic_distance,
                        tile=adjacent,
                        door=door,
                    )

            map_x += step_x
            map_y += step_y
            side_x += delta_x
            side_y += delta_y
            side = "corner"
        elif side_x < side_y:
            distance = side_x
            map_x += step_x
            side_x += delta_x
            side = "vertical"
        else:
            distance = side_y
            map_y += step_y
            side_y += delta_y
            side = "horizontal"

        tile = (map_x, map_y)
        tile_type = _tile_at_or_void(floor, map_x, map_y)
        if blocks_scan(tile_type):
            return _make_static_hit(
                scan_id=scan_id,
                ray_index=ray_index,
                ray_count=ray_count,
                angle=angle,
                origin=start,
                direction=direction,
                distance=distance,
                tile=tile,
                tile_type=tile_type,
                side=side,
            )

        dynamic_hit = _dynamic_hit_in_tile(
            start, direction, tile, dynamic_blockers, max_distance, purpose
        )
        if dynamic_hit is not None:
            dynamic_distance, door = dynamic_hit
            # A blocker in this tile matters only after entering the tile and before leaving it.
            tile_exit_distance = min(side_x, side_y)
            if distance - _EPSILON <= dynamic_distance <= tile_exit_distance + _EPSILON:
                return _make_dynamic_hit(
                    scan_id=scan_id,
                    ray_index=ray_index,
                    ray_count=ray_count,
                    angle=angle,
                    origin=start,
                    direction=direction,
                    distance=dynamic_distance,
                    tile=tile,
                    door=door,
                )

    return None


def cast_rays(
    origin: pygame.Vector2 | tuple[float, float],
    floor: TileFloor,
    dynamic_blockers: DynamicBlockerRegistry | None,
    tile_size: int,
    max_distance: float,
    ray_count: int,
    *,
    scan_id: int = 0,
    angle_offset: float = 0.0,
) -> list[RayHit]:
    if ray_count <= 0:
        return []
    hits: list[RayHit] = []
    angle_step = math.tau / ray_count
    for ray_index in range(ray_count):
        angle = angle_offset + ray_index * angle_step
        hit = cast_ray(
            origin,
            angle,
            floor,
            dynamic_blockers,
            tile_size,
            max_distance,
            scan_id=scan_id,
            ray_index=ray_index,
            ray_count=ray_count,
        )
        if hit is not None:
            hits.append(hit)
    return hits


def has_line_of_sight(
    start_world: pygame.Vector2 | tuple[float, float],
    end_world: pygame.Vector2 | tuple[float, float],
    floor: TileFloor,
    dynamic_blockers: DynamicBlockerRegistry | None,
    tile_size: int,
) -> bool:
    start = pygame.Vector2(start_world)
    end = pygame.Vector2(end_world)
    delta = end - start
    distance = delta.length()
    if distance <= _EPSILON:
        tile_x = math.floor(start.x / tile_size)
        tile_y = math.floor(start.y / tile_size)
        return _in_bounds(floor, tile_x, tile_y) and not blocks_scan(_tile_at_or_void(floor, tile_x, tile_y))

    end_tile = (math.floor(end.x / tile_size), math.floor(end.y / tile_size))
    if not _in_bounds(floor, *end_tile):
        return False

    hit = cast_ray(
        start,
        math.atan2(delta.y, delta.x),
        floor,
        dynamic_blockers,
        tile_size,
        distance,
        purpose=BlockerPurpose.LINE_OF_SIGHT,
    )
    return hit is None or hit.distance >= distance - 1e-6
