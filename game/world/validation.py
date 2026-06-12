from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from game.world.floor import GeneratedFloor
from game.world.room import Room
from game.world.tiles import TileType, is_walkable


@dataclass
class ValidationReport:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    room_count: int = 0
    reachable_walkable_tiles: int = 0
    total_walkable_tiles: int = 0
    graph_cycle_rank: int = 0
    minimum_spawn_distance: int | None = None
    generation_attempt: int = 0
    connectivity_ratio: float = 0.0


def normalize_edge(room_a: int, room_b: int) -> tuple[int, int]:
    if room_a == room_b:
        raise ValueError("Graph edge cannot connect a room to itself.")
    return tuple(sorted((room_a, room_b)))


def unique_edges(edges: Iterable[tuple[int, int]]) -> set[tuple[int, int]]:
    return {normalize_edge(room_a, room_b) for room_a, room_b in edges}


def walkable_tiles(grid: np.ndarray) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y in range(grid.shape[0])
        for x in range(grid.shape[1])
        if is_walkable(int(grid[y, x]))
    }


def in_bounds(grid: np.ndarray, tile: tuple[int, int]) -> bool:
    x, y = tile
    return 0 <= y < grid.shape[0] and 0 <= x < grid.shape[1]


def is_walkable_at(grid: np.ndarray, tile: tuple[int, int]) -> bool:
    x, y = tile
    return in_bounds(grid, tile) and is_walkable(int(grid[y, x]))


def cardinal_neighbours(tile: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    x, y = tile
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def flood_fill(grid: np.ndarray, start: tuple[int, int]) -> set[tuple[int, int]]:
    if not is_walkable_at(grid, start):
        return set()

    visited = {start}
    queue: deque[tuple[int, int]] = deque([start])
    while queue:
        tile = queue.popleft()
        for neighbour in cardinal_neighbours(tile):
            if neighbour not in visited and is_walkable_at(grid, neighbour):
                visited.add(neighbour)
                queue.append(neighbour)
    return visited


def connected_components(grid: np.ndarray) -> list[set[tuple[int, int]]]:
    remaining = walkable_tiles(grid)
    components: list[set[tuple[int, int]]] = []
    while remaining:
        start = min(remaining)
        component = flood_fill(grid, start)
        components.append(component)
        remaining -= component
    return components


def shortest_tile_path(
    grid: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]]:
    if not is_walkable_at(grid, start) or not is_walkable_at(grid, goal):
        return []
    if start == goal:
        return [start]

    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    queue: deque[tuple[int, int]] = deque([start])
    while queue:
        tile = queue.popleft()
        for neighbour in cardinal_neighbours(tile):
            if neighbour in came_from or not is_walkable_at(grid, neighbour):
                continue
            came_from[neighbour] = tile
            if neighbour == goal:
                path = [goal]
                current = tile
                while current is not None:
                    path.append(current)
                    current = came_from[current]
                path.reverse()
                return path
            queue.append(neighbour)
    return []


def tile_distance(grid: np.ndarray, start: tuple[int, int], goal: tuple[int, int]) -> int | None:
    path = shortest_tile_path(grid, start, goal)
    if not path:
        return None
    return len(path) - 1


def graph_adjacency(room_count: int, edges: Iterable[tuple[int, int]]) -> dict[int, set[int]]:
    adjacency = {room_id: set() for room_id in range(room_count)}
    for room_a, room_b in unique_edges(edges):
        if room_a not in adjacency or room_b not in adjacency:
            continue
        adjacency[room_a].add(room_b)
        adjacency[room_b].add(room_a)
    return adjacency


def graph_bfs(room_count: int, edges: Iterable[tuple[int, int]], start_room_id: int) -> set[int]:
    if start_room_id < 0 or start_room_id >= room_count:
        return set()

    adjacency = graph_adjacency(room_count, edges)
    visited = {start_room_id}
    queue: deque[int] = deque([start_room_id])
    while queue:
        room_id = queue.popleft()
        for neighbour in adjacency[room_id]:
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append(neighbour)
    return visited


def graph_shortest_path(
    room_count: int,
    edges: Iterable[tuple[int, int]],
    start_room_id: int,
    target_room_id: int,
) -> list[int]:
    if start_room_id == target_room_id:
        return [start_room_id]

    adjacency = graph_adjacency(room_count, edges)
    came_from: dict[int, int | None] = {start_room_id: None}
    queue: deque[int] = deque([start_room_id])
    while queue:
        room_id = queue.popleft()
        for neighbour in adjacency.get(room_id, set()):
            if neighbour in came_from:
                continue
            came_from[neighbour] = room_id
            if neighbour == target_room_id:
                path = [target_room_id]
                current = room_id
                while current is not None:
                    path.append(current)
                    current = came_from[current]
                path.reverse()
                return path
            queue.append(neighbour)
    return []


def graph_distance(room_count: int, edges: Iterable[tuple[int, int]], start_room_id: int, target_room_id: int) -> int | None:
    path = graph_shortest_path(room_count, edges, start_room_id, target_room_id)
    if not path:
        return None
    return len(path) - 1


def graph_component_count(room_count: int, edges: Iterable[tuple[int, int]]) -> int:
    remaining = set(range(room_count))
    components = 0
    while remaining:
        start = min(remaining)
        reached = graph_bfs(room_count, edges, start)
        remaining -= reached
        components += 1
    return components


def cycle_rank(room_count: int, edges: Iterable[tuple[int, int]]) -> int:
    normalised = unique_edges(edges)
    return len(normalised) - room_count + graph_component_count(room_count, normalised)


def validate_room_graph(rooms: list[Room], edges: Iterable[tuple[int, int]], corridors: object, start_room_id: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    room_ids = {room.room_id for room in rooms}
    edge_list = list(edges)
    normalised_edges: set[tuple[int, int]] = set()

    for edge in edge_list:
        room_a, room_b = edge
        if room_a == room_b:
            errors.append(f"self edge {edge}")
            continue
        if room_a not in room_ids or room_b not in room_ids:
            errors.append(f"edge references unknown room {edge}")
            continue
        normalised_edges.add(tuple(sorted(edge)))

    if len(normalised_edges) != len(edge_list):
        warnings.append("duplicate graph edge was normalised")

    adjacency = graph_adjacency(len(rooms), normalised_edges)
    for room in rooms:
        for neighbour in room.connected_room_ids:
            if neighbour not in room_ids:
                errors.append(f"room {room.room_id} references unknown neighbour {neighbour}")
            elif room.room_id not in rooms[neighbour].connected_room_ids:
                errors.append(f"adjacency is not symmetrical between {room.room_id} and {neighbour}")
            elif neighbour not in adjacency[room.room_id]:
                errors.append(f"adjacency missing graph edge {room.room_id}-{neighbour}")

    if start_room_id not in room_ids:
        errors.append("start room does not exist")
    elif len(graph_bfs(len(rooms), normalised_edges, start_room_id)) != len(rooms):
        errors.append("room graph is disconnected")

    corridor_edges = {corridor.edge for corridor in corridors}
    for edge in normalised_edges:
        if edge not in corridor_edges:
            errors.append(f"graph edge {edge} has no corridor")
    for corridor in corridors:
        if corridor.edge not in normalised_edges:
            errors.append(f"corridor edge {corridor.edge} is not in graph")

    return errors, warnings


def has_clearance(grid: np.ndarray, tile: tuple[int, int], radius: int = 1, minimum_walkable_neighbours: int = 2) -> bool:
    if not is_walkable_at(grid, tile):
        return False
    x, y = tile
    for ty in range(y - radius, y + radius + 1):
        for tx in range(x - radius, x + radius + 1):
            if not in_bounds(grid, (tx, ty)):
                return False
    return walkable_neighbour_count(grid, tile) >= minimum_walkable_neighbours


def walkable_neighbour_count(grid: np.ndarray, tile: tuple[int, int]) -> int:
    return sum(1 for neighbour in cardinal_neighbours(tile) if is_walkable_at(grid, neighbour))


def is_player_spawn_safe(
    grid: np.ndarray,
    spawn: tuple[int, int],
    start_room: Room,
    elevator_tile: tuple[int, int],
    doorway_tiles: Iterable[tuple[int, int]],
    clearance_radius: int = 1,
) -> bool:
    if spawn == elevator_tile:
        return False
    if spawn in set(doorway_tiles):
        return False
    if not start_room.rect.contains(spawn):
        return False
    return has_clearance(grid, spawn, radius=clearance_radius, minimum_walkable_neighbours=2)


def elevator_approach_tiles(grid: np.ndarray, elevator_tile: tuple[int, int]) -> list[tuple[int, int]]:
    return [tile for tile in cardinal_neighbours(elevator_tile) if is_walkable_at(grid, tile)]


def is_elevator_safe(
    grid: np.ndarray,
    elevator_tile: tuple[int, int],
    start_room: Room,
    player_spawn: tuple[int, int],
    doorway_tiles: Iterable[tuple[int, int]],
) -> bool:
    if elevator_tile == player_spawn or elevator_tile in set(doorway_tiles):
        return False
    if not start_room.rect.contains(elevator_tile):
        return False
    return is_walkable_at(grid, elevator_tile) and len(elevator_approach_tiles(grid, elevator_tile)) >= 1


def is_creature_spawn_safe(
    grid: np.ndarray,
    spawn: tuple[int, int],
    player_spawn: tuple[int, int],
    start_room: Room,
    doorway_tiles: Iterable[tuple[int, int]],
    elevator_tile: tuple[int, int],
    minimum_distance: int,
) -> bool:
    if spawn == elevator_tile or spawn in set(doorway_tiles):
        return False
    if start_room.rect.contains(spawn):
        return False
    if not has_clearance(grid, spawn, radius=1, minimum_walkable_neighbours=2):
        return False
    distance = tile_distance(grid, player_spawn, spawn)
    return distance is not None and distance >= minimum_distance


def select_separated_spawns(
    grid: np.ndarray,
    candidates: Iterable[tuple[int, int]],
    count: int,
    minimum_pairwise_distance: int,
) -> list[tuple[int, int]]:
    selected: list[tuple[int, int]] = []
    for candidate in candidates:
        if all((tile_distance(grid, candidate, other) or 0) >= minimum_pairwise_distance for other in selected):
            selected.append(candidate)
        if len(selected) >= count:
            break
    return selected


def is_obstacle_placement_safe(
    grid: np.ndarray,
    obstacle_tile: tuple[int, int],
    start: tuple[int, int],
    forbidden_tiles: Iterable[tuple[int, int]] = (),
) -> bool:
    if obstacle_tile in set(forbidden_tiles):
        return False
    if not is_walkable_at(grid, obstacle_tile):
        return False
    trial = grid.copy()
    x, y = obstacle_tile
    trial[y, x] = int(TileType.OBSTACLE)
    total_before = len(walkable_tiles(grid)) - 1
    reached_after = flood_fill(trial, start)
    return len(reached_after) == total_before


def doorway_orientation(grid: np.ndarray, tile: tuple[int, int]) -> str | None:
    x, y = tile
    horizontal = is_walkable_at(grid, (x - 1, y)) and is_walkable_at(grid, (x + 1, y))
    vertical = is_walkable_at(grid, (x, y - 1)) and is_walkable_at(grid, (x, y + 1))
    if horizontal and not vertical:
        return "vertical_door_plane"
    if vertical and not horizontal:
        return "horizontal_door_plane"
    if horizontal:
        return "vertical_door_plane"
    if vertical:
        return "horizontal_door_plane"
    return None


def is_doorway_valid(grid: np.ndarray, tile: tuple[int, int]) -> bool:
    return is_walkable_at(grid, tile) and doorway_orientation(grid, tile) is not None


def corridor_width_problems(grid: np.ndarray, corridor_paths: Iterable[Iterable[tuple[int, int]]], corridor_width: int) -> list[str]:
    problems: list[str] = []
    if corridor_width < 2:
        problems.append("configured corridor width is below two tiles")
    for index, path in enumerate(corridor_paths):
        previous: tuple[int, int] | None = None
        for tile in path:
            if previous is not None:
                dx = abs(tile[0] - previous[0])
                dy = abs(tile[1] - previous[1])
                if dx + dy != 1:
                    problems.append(f"corridor {index} has non-cardinal step {previous}->{tile}")
                    break
            previous = tile
            if not is_walkable_at(grid, tile):
                problems.append(f"corridor {index} contains blocked tile {tile}")
                break
    return problems


def validate_floor(floor: GeneratedFloor, profile: object | None = None) -> ValidationReport:
    report = ValidationReport(
        is_valid=True,
        room_count=len(floor.rooms),
        graph_cycle_rank=cycle_rank(len(floor.rooms), floor.graph_edges),
        generation_attempt=floor.generation_attempt,
    )

    all_walkable = walkable_tiles(floor.tiles)
    reachable = flood_fill(floor.tiles, floor.player_spawn)
    report.total_walkable_tiles = len(all_walkable)
    report.reachable_walkable_tiles = len(reachable)
    report.connectivity_ratio = len(reachable) / len(all_walkable) if all_walkable else 0.0

    graph_errors, graph_warnings = validate_room_graph(floor.rooms, floor.graph_edges, floor.corridors, floor.start_room_id)
    report.errors.extend(graph_errors)
    report.warnings.extend(graph_warnings)

    minimum_rooms = getattr(profile, "minimum_rooms", 1)
    maximum_rooms = getattr(profile, "maximum_rooms", 999)
    required_cycle_rank = getattr(profile, "required_cycle_rank", 0)
    preferred_cycle_rank = getattr(profile, "preferred_cycle_rank", 0)
    minimum_creature_candidates = getattr(profile, "minimum_creature_candidates", 1)
    minimum_objective_candidates = getattr(profile, "minimum_objective_candidates", 1)
    minimum_material_candidates = getattr(profile, "minimum_material_candidates", 1)
    creature_minimum_distance = getattr(profile, "creature_minimum_distance", 12)

    if not (minimum_rooms <= len(floor.rooms) <= maximum_rooms):
        report.errors.append(f"room count {len(floor.rooms)} outside profile bounds {minimum_rooms}-{maximum_rooms}")

    if report.graph_cycle_rank < required_cycle_rank:
        report.errors.append(f"cycle rank {report.graph_cycle_rank} below required {required_cycle_rank}")
    elif report.graph_cycle_rank < preferred_cycle_rank:
        report.warnings.append(f"cycle rank {report.graph_cycle_rank} below preferred {preferred_cycle_rank}")

    if floor.player_spawn not in reachable:
        report.errors.append("player spawn is not reachable")
    if floor.elevator_tile not in reachable:
        report.errors.append("elevator is not reachable from player spawn")
    if not floor.is_walkable(*floor.player_spawn):
        report.errors.append("player spawn is not walkable")
    if not floor.is_walkable(*floor.elevator_tile):
        report.errors.append("elevator is not walkable")
    if report.reachable_walkable_tiles != report.total_walkable_tiles:
        report.errors.append("walkable map contains disconnected islands")

    start_room = floor.rooms[floor.start_room_id]
    if not is_player_spawn_safe(floor.tiles, floor.player_spawn, start_room, floor.elevator_tile, floor.doorway_candidates):
        report.errors.append("player spawn failed safety checks")
    if not is_elevator_safe(floor.tiles, floor.elevator_tile, start_room, floor.player_spawn, floor.doorway_candidates):
        report.errors.append("elevator failed safety checks")

    for room in floor.rooms:
        if not any(tile in reachable for tile in room.rect.interior_tiles(margin=1)):
            report.errors.append(f"room {room.room_id} has no reachable interior tile")

    for corridor in floor.corridors:
        if not any(tile in reachable for tile in corridor.path):
            report.errors.append(f"corridor {corridor.edge} is not reachable")

    for room_id in floor.candidate_objective_rooms:
        if room_id < 0 or room_id >= len(floor.rooms):
            report.errors.append(f"objective candidate room {room_id} is invalid")
        elif not any(tile in reachable for tile in floor.rooms[room_id].rect.interior_tiles(margin=1)):
            report.errors.append(f"objective candidate room {room_id} is unreachable")

    for room_id in floor.candidate_material_rooms:
        if room_id < 0 or room_id >= len(floor.rooms):
            report.errors.append(f"material candidate room {room_id} is invalid")
        elif not any(tile in reachable for tile in floor.rooms[room_id].rect.interior_tiles(margin=1)):
            report.errors.append(f"material candidate room {room_id} is unreachable")

    for candidate in floor.candidate_creature_spawns:
        if candidate not in reachable:
            report.errors.append(f"creature candidate {candidate} is unreachable")
        if not is_creature_spawn_safe(
            floor.tiles,
            candidate,
            floor.player_spawn,
            start_room,
            floor.doorway_candidates,
            floor.elevator_tile,
            creature_minimum_distance,
        ):
            report.errors.append(f"creature candidate {candidate} failed safety checks")

    if len(floor.candidate_creature_spawns) < minimum_creature_candidates:
        report.errors.append("not enough creature spawn candidates")
    if len(floor.candidate_objective_rooms) < minimum_objective_candidates:
        report.errors.append("not enough objective room candidates")
    if len(floor.candidate_material_rooms) < minimum_material_candidates:
        report.errors.append("not enough material room candidates")

    spawn_distances = [
        tile_distance(floor.tiles, floor.player_spawn, candidate)
        for candidate in floor.candidate_creature_spawns
    ]
    known_distances = [distance for distance in spawn_distances if distance is not None]
    report.minimum_spawn_distance = min(known_distances) if known_distances else None

    for doorway in floor.doorway_candidates:
        if not is_doorway_valid(floor.tiles, doorway):
            report.errors.append(f"doorway candidate {doorway} is invalid")
        if doorway in (floor.player_spawn, floor.elevator_tile):
            report.errors.append(f"doorway candidate {doorway} overlaps reserved start tile")

    for problem in corridor_width_problems(floor.tiles, (corridor.path for corridor in floor.corridors), floor.corridor_width):
        report.errors.append(problem)

    obstacle_tiles = {
        (x, y)
        for y in range(floor.height)
        for x in range(floor.width)
        if TileType(int(floor.tiles[y, x])) in (TileType.OBSTACLE, TileType.PILLAR)
    }
    reserved_tiles = set(floor.doorway_candidates) | {floor.player_spawn, floor.elevator_tile}
    if obstacle_tiles & reserved_tiles:
        report.errors.append("obstacle overlaps reserved tile")

    for gate in floor.gate_candidates:
        if floor.start_room_id in gate.gated_rooms:
            report.errors.append(f"gate {gate.edge} would trap the start room")
        if not gate.gated_rooms:
            report.errors.append(f"gate {gate.edge} has no gated rooms")

    for room_id in floor.containment_room_candidates:
        if room_id == floor.start_room_id:
            report.errors.append("containment candidate includes start room")

    report.is_valid = not report.errors
    return report
