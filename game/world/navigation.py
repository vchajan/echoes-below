from __future__ import annotations

import heapq
from itertools import count

from game.world.blockers import BlockerPurpose, DynamicBlockerRegistry

Tile = tuple[int, int]


def doorway_passable_for_creature(
    blockers: DynamicBlockerRegistry,
    tile: Tile,
) -> bool:
    return not blockers.blocks_tile(tile[0], tile[1], BlockerPurpose.CREATURE_MOVEMENT)


def manhattan_distance(first: Tile, second: Tile) -> int:
    return abs(first[0] - second[0]) + abs(first[1] - second[1])


def in_bounds(generated_floor, tile: Tile) -> bool:
    x, y = tile
    return 0 <= x < generated_floor.width and 0 <= y < generated_floor.height


def is_tile_walkable(
    generated_floor,
    tile: Tile,
    dynamic_blockers: DynamicBlockerRegistry | None = None,
    purpose: BlockerPurpose | str = BlockerPurpose.CREATURE_MOVEMENT,
) -> bool:
    x, y = tile
    if not in_bounds(generated_floor, tile):
        return False
    if not generated_floor.is_walkable(x, y):
        return False
    return not (dynamic_blockers and dynamic_blockers.blocks_tile(x, y, purpose))


def walkable_neighbours(
    generated_floor,
    tile: Tile,
    dynamic_blockers: DynamicBlockerRegistry | None = None,
    purpose: BlockerPurpose | str = BlockerPurpose.CREATURE_MOVEMENT,
) -> list[Tile]:
    neighbours: list[Tile] = []
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        candidate = (tile[0] + dx, tile[1] + dy)
        if is_tile_walkable(generated_floor, candidate, dynamic_blockers, purpose):
            neighbours.append(candidate)
    return neighbours


def reconstruct_path(came_from: dict[Tile, Tile | None], target: Tile) -> list[Tile]:
    path = [target]
    current = target
    while came_from[current] is not None:
        current = came_from[current]  # type: ignore[assignment]
        path.append(current)
    path.reverse()
    return path[1:]


def astar_path(
    generated_floor,
    start: Tile,
    target: Tile,
    dynamic_blockers: DynamicBlockerRegistry | None = None,
    purpose: BlockerPurpose | str = BlockerPurpose.CREATURE_MOVEMENT,
    *,
    max_nodes: int | None = None,
) -> list[Tile]:
    """Return a deterministic start-excluded four-way path ending at target."""
    if start == target:
        return []
    if not in_bounds(generated_floor, start) or not generated_floor.is_walkable(*start):
        return []
    if not is_tile_walkable(generated_floor, target, dynamic_blockers, purpose):
        return []

    serial = count()
    open_heap: list[tuple[int, int, int, int, int, Tile]] = []
    heapq.heappush(
        open_heap,
        (manhattan_distance(start, target), manhattan_distance(start, target), start[1], start[0], next(serial), start),
    )
    came_from: dict[Tile, Tile | None] = {start: None}
    g_score: dict[Tile, int] = {start: 0}
    visited_nodes = 0

    while open_heap:
        _, _, _, _, _, current = heapq.heappop(open_heap)
        visited_nodes += 1
        if max_nodes is not None and visited_nodes > max_nodes:
            return []
        if current == target:
            return reconstruct_path(came_from, target)

        for neighbour in walkable_neighbours(generated_floor, current, dynamic_blockers, purpose):
            tentative = g_score[current] + 1
            if tentative >= g_score.get(neighbour, 1_000_000_000):
                continue
            came_from[neighbour] = current
            g_score[neighbour] = tentative
            heuristic = manhattan_distance(neighbour, target)
            heapq.heappush(
                open_heap,
                (tentative + heuristic, heuristic, neighbour[1], neighbour[0], next(serial), neighbour),
            )
    return []


def is_path_valid(
    generated_floor,
    path: list[Tile] | tuple[Tile, ...],
    dynamic_blockers: DynamicBlockerRegistry | None = None,
    purpose: BlockerPurpose | str = BlockerPurpose.CREATURE_MOVEMENT,
    *,
    start_tile: Tile | None = None,
) -> bool:
    previous = start_tile
    for index, tile in enumerate(path):
        if previous is not None:
            if tile == previous:
                if not (index == 0 and start_tile is not None):
                    return False
            elif manhattan_distance(previous, tile) != 1:
                return False
        if not is_tile_walkable(generated_floor, tile, dynamic_blockers, purpose):
            return False
        previous = tile
    return True


def nearest_reachable_tile(
    generated_floor,
    start: Tile,
    target: Tile,
    dynamic_blockers: DynamicBlockerRegistry | None = None,
    purpose: BlockerPurpose | str = BlockerPurpose.CREATURE_MOVEMENT,
    *,
    max_radius: int = 8,
) -> Tile | None:
    if start == target and in_bounds(generated_floor, start) and generated_floor.is_walkable(*start):
        return start
    if is_tile_walkable(generated_floor, target, dynamic_blockers, purpose):
        if astar_path(generated_floor, start, target, dynamic_blockers, purpose) or start == target:
            return target

    candidates: list[tuple[int, int, int, Tile]] = []
    for radius in range(1, max_radius + 1):
        for y in range(target[1] - radius, target[1] + radius + 1):
            for x in range(target[0] - radius, target[0] + radius + 1):
                candidate = (x, y)
                if manhattan_distance(candidate, target) != radius:
                    continue
                if not is_tile_walkable(generated_floor, candidate, dynamic_blockers, purpose):
                    continue
                candidates.append((radius, manhattan_distance(start, candidate), y, candidate))
        candidates.sort()
        for _, _, _, candidate in candidates:
            if candidate == start or astar_path(generated_floor, start, candidate, dynamic_blockers, purpose):
                return candidate
        candidates.clear()
    return None
