from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from game.world.room import Room
from game.world.tiles import TileType, is_walkable


@dataclass(frozen=True)
class Corridor:
    room_a: int
    room_b: int
    path: tuple[tuple[int, int], ...]

    @property
    def edge(self) -> tuple[int, int]:
        return tuple(sorted((self.room_a, self.room_b)))


@dataclass(frozen=True)
class DoorwayCandidate:
    tile: tuple[int, int]
    room_id: int
    connected_room_id: int
    orientation: str

    @property
    def edge(self) -> tuple[int, int]:
        return tuple(sorted((self.room_id, self.connected_room_id)))


@dataclass(frozen=True)
class GateCandidate:
    edge: tuple[int, int]
    key_side_rooms: tuple[int, ...]
    gated_rooms: tuple[int, ...]
    doorway_tiles: tuple[tuple[int, int], ...]
    score: int


@dataclass
class GeneratedFloor:
    seed: int
    floor_number: int
    attempt_seed: int
    width: int
    height: int
    tiles: np.ndarray
    rooms: list[Room]
    graph_edges: set[tuple[int, int]]
    corridors: list[Corridor]
    start_room_id: int
    player_spawn: tuple[int, int]
    elevator_tile: tuple[int, int]
    elevator_approach_tiles: list[tuple[int, int]]
    doorway_candidates: list[tuple[int, int]]
    doorway_data: list[DoorwayCandidate]
    candidate_creature_spawns: list[tuple[int, int]]
    candidate_objective_rooms: list[int]
    objective_room_groups: dict[str, list[int]]
    candidate_material_rooms: list[int]
    material_room_scores: dict[int, int]
    gate_candidates: list[GateCandidate]
    containment_room_candidates: list[int]
    generation_attempt: int
    corridor_width: int
    validation_report: Any | None = None
    metadata: dict[str, int] = field(default_factory=dict)

    def in_bounds(self, tile_x: int, tile_y: int) -> bool:
        return 0 <= tile_x < self.width and 0 <= tile_y < self.height

    def tile_at(self, tile_x: int, tile_y: int) -> TileType:
        if not self.in_bounds(tile_x, tile_y):
            raise IndexError(f"Tile out of bounds: {(tile_x, tile_y)}")
        return TileType(int(self.tiles[tile_y, tile_x]))

    def is_walkable(self, tile_x: int, tile_y: int) -> bool:
        return self.in_bounds(tile_x, tile_y) and is_walkable(self.tile_at(tile_x, tile_y))

    def world_size_pixels(self, tile_size: int) -> tuple[int, int]:
        return (self.width * tile_size, self.height * tile_size)

    def walkable_tiles(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if is_walkable(int(self.tiles[y, x]))
        ]

    def neighbours(self, room_id: int) -> set[int]:
        return set(self.rooms[room_id].connected_room_ids)

    def graph_distance(self, start_room_id: int, target_room_id: int) -> int | None:
        if start_room_id == target_room_id:
            return 0

        visited = {start_room_id}
        queue: deque[tuple[int, int]] = deque([(start_room_id, 0)])
        while queue:
            room_id, distance = queue.popleft()
            for neighbour in self.rooms[room_id].connected_room_ids:
                if neighbour == target_room_id:
                    return distance + 1
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append((neighbour, distance + 1))
        return None

    def has_edge(self, room_a: int, room_b: int) -> bool:
        return tuple(sorted((room_a, room_b))) in self.graph_edges
