from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import random

import numpy as np

from game.world.floor import Corridor, GeneratedFloor
from game.world.room import Room, RoomRect
from game.world.tiles import TileType, is_walkable


class GenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeneratorConfig:
    width: int = 70
    height: int = 50
    tile_size: int = 48
    target_rooms: int = 9
    minimum_rooms: int = 8
    maximum_rooms: int = 10
    minimum_room_width: int = 6
    maximum_room_width: int = 12
    minimum_room_height: int = 5
    maximum_room_height: int = 10
    room_padding: int = 2
    corridor_width: int = 2
    safe_border: int = 2
    max_room_placement_attempts: int = 300
    max_generation_attempts: int = 20
    max_obstacle_rooms: int = 5


FLOOR_PROFILES: dict[int, dict[str, int]] = {
    1: {"target_rooms": 9, "minimum_rooms": 8, "maximum_rooms": 10},
    2: {"target_rooms": 12, "minimum_rooms": 11, "maximum_rooms": 13},
    3: {"target_rooms": 14, "minimum_rooms": 13, "maximum_rooms": 16},
}


class FloorGenerator:
    def __init__(self, config: GeneratorConfig | None = None) -> None:
        self.base_config = config or GeneratorConfig()

    def config_for_floor(self, floor_number: int) -> GeneratorConfig:
        profile = FLOOR_PROFILES.get(floor_number, FLOOR_PROFILES[1])
        return replace(self.base_config, **profile)

    def generate(self, seed: int, floor_number: int = 1) -> GeneratedFloor:
        config = self.config_for_floor(floor_number)
        last_reason = "unknown"

        for attempt in range(1, config.max_generation_attempts + 1):
            rng = random.Random(f"{seed}:{floor_number}:{attempt}")
            try:
                floor = self._generate_attempt(seed, floor_number, config, attempt, rng)
                if self._validate_floor(floor):
                    return floor
                last_reason = "validation failed"
            except GenerationError as exc:
                last_reason = str(exc)

        raise GenerationError(
            f"Could not generate valid floor after {config.max_generation_attempts} attempts: {last_reason}"
        )

    def _generate_attempt(
        self,
        seed: int,
        floor_number: int,
        config: GeneratorConfig,
        attempt: int,
        rng: random.Random,
    ) -> GeneratedFloor:
        grid = np.full((config.height, config.width), int(TileType.VOID), dtype=np.int16)
        rooms = self._place_rooms(config, rng)
        if len(rooms) < config.minimum_rooms:
            raise GenerationError("not enough rooms placed")

        for room in rooms:
            self._carve_room(grid, room)

        graph_edges = self._build_graph(rooms, rng)
        corridors = self._carve_corridors(grid, rooms, graph_edges, config, rng)
        start_room_id = self._choose_start_room(rooms)
        self._mark_room_roles(rooms, start_room_id)

        doorway_candidates = self._collect_doorways(grid, rooms)
        self._place_start_and_elevator(grid, rooms[start_room_id])
        elevator_tile = rooms[start_room_id].center
        player_spawn = self._choose_player_spawn(grid, rooms[start_room_id], elevator_tile)

        self._generate_walls(grid, rng)
        self._apply_floor_variants(grid, rng)
        self._place_obstacles(grid, rooms, start_room_id, player_spawn, doorway_candidates, config, rng)

        candidate_creature_spawns = self._candidate_creature_spawns(grid, rooms, start_room_id, player_spawn)
        candidate_objective_rooms = self._candidate_objective_rooms(rooms, start_room_id)
        candidate_material_rooms = self._candidate_material_rooms(rooms, start_room_id)

        return GeneratedFloor(
            seed=seed,
            floor_number=floor_number,
            width=config.width,
            height=config.height,
            tiles=grid,
            rooms=rooms,
            graph_edges=graph_edges,
            corridors=corridors,
            start_room_id=start_room_id,
            player_spawn=player_spawn,
            elevator_tile=elevator_tile,
            doorway_candidates=doorway_candidates,
            candidate_creature_spawns=candidate_creature_spawns,
            candidate_objective_rooms=candidate_objective_rooms,
            candidate_material_rooms=candidate_material_rooms,
            generation_attempt=attempt,
            corridor_width=config.corridor_width,
            metadata={
                "max_generation_attempts": config.max_generation_attempts,
                "max_room_placement_attempts": config.max_room_placement_attempts,
            },
        )

    def _place_rooms(self, config: GeneratorConfig, rng: random.Random) -> list[Room]:
        rooms: list[Room] = []
        target = rng.randint(config.minimum_rooms, config.maximum_rooms)
        target = max(config.minimum_rooms, min(config.maximum_rooms, config.target_rooms if rng.random() < 0.5 else target))

        for _ in range(config.max_room_placement_attempts):
            if len(rooms) >= target:
                break

            width = rng.randint(config.minimum_room_width, config.maximum_room_width)
            height = rng.randint(config.minimum_room_height, config.maximum_room_height)
            left = rng.randint(config.safe_border, config.width - config.safe_border - width)
            top = rng.randint(config.safe_border, config.height - config.safe_border - height)
            rect = RoomRect(left, top, width, height)

            if any(rect.intersects(room.rect, padding=config.room_padding) for room in rooms):
                continue

            rooms.append(Room(room_id=len(rooms), rect=rect))

        return rooms

    def _carve_room(self, grid: np.ndarray, room: Room) -> None:
        grid[room.rect.top : room.rect.bottom, room.rect.left : room.rect.right] = int(TileType.FLOOR)

    def _build_graph(self, rooms: list[Room], rng: random.Random) -> set[tuple[int, int]]:
        edges: set[tuple[int, int]] = set()
        connected = {0}
        remaining = set(range(1, len(rooms)))

        while remaining:
            best: tuple[int, int, int] | None = None
            for room_a in sorted(connected):
                for room_b in sorted(remaining):
                    distance = self._distance_squared(rooms[room_a].center, rooms[room_b].center)
                    candidate = (distance, room_a, room_b)
                    if best is None or candidate < best:
                        best = candidate

            assert best is not None
            _, room_a, room_b = best
            self._add_edge(edges, rooms, room_a, room_b)
            connected.add(room_b)
            remaining.remove(room_b)

        if len(rooms) >= 5:
            candidates = [
                (self._distance_squared(room_a.center, room_b.center), room_a.room_id, room_b.room_id)
                for index, room_a in enumerate(rooms)
                for room_b in rooms[index + 1 :]
                if tuple(sorted((room_a.room_id, room_b.room_id))) not in edges
            ]
            candidates.sort(reverse=True)
            if candidates:
                useful_candidates = candidates[: min(6, len(candidates))]
                _, room_a, room_b = useful_candidates[rng.randrange(len(useful_candidates))]
                self._add_edge(edges, rooms, room_a, room_b)

        return edges

    def _add_edge(self, edges: set[tuple[int, int]], rooms: list[Room], room_a: int, room_b: int) -> None:
        edge = tuple(sorted((room_a, room_b)))
        edges.add(edge)
        rooms[room_a].connected_room_ids.add(room_b)
        rooms[room_b].connected_room_ids.add(room_a)

    def _carve_corridors(
        self,
        grid: np.ndarray,
        rooms: list[Room],
        graph_edges: set[tuple[int, int]],
        config: GeneratorConfig,
        rng: random.Random,
    ) -> list[Corridor]:
        corridors: list[Corridor] = []
        for room_a_id, room_b_id in sorted(graph_edges):
            start = rooms[room_a_id].center
            end = rooms[room_b_id].center
            horizontal_first = rng.choice((True, False))
            path = self._corridor_path(start, end, horizontal_first)
            for x, y in path:
                self._carve_corridor_tile(grid, x, y, config.corridor_width)

            corridors.append(Corridor(room_a=room_a_id, room_b=room_b_id, path=tuple(path)))
        return corridors

    def _corridor_path(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        horizontal_first: bool,
    ) -> list[tuple[int, int]]:
        sx, sy = start
        ex, ey = end
        elbow = (ex, sy) if horizontal_first else (sx, ey)
        return self._line_points(start, elbow) + self._line_points(elbow, end)[1:]

    def _line_points(self, start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
        sx, sy = start
        ex, ey = end
        points: list[tuple[int, int]] = []
        if sx != ex:
            step = 1 if ex > sx else -1
            for x in range(sx, ex + step, step):
                points.append((x, sy))
        elif sy != ey:
            step = 1 if ey > sy else -1
            for y in range(sy, ey + step, step):
                points.append((sx, y))
        else:
            points.append(start)
        return points

    def _carve_corridor_tile(self, grid: np.ndarray, x: int, y: int, width: int) -> None:
        for offset_y in range(width):
            for offset_x in range(width):
                tx = x + offset_x
                ty = y + offset_y
                if 0 <= ty < grid.shape[0] and 0 <= tx < grid.shape[1]:
                    grid[ty, tx] = int(TileType.FLOOR)

    def _collect_doorways(self, grid: np.ndarray, rooms: list[Room]) -> list[tuple[int, int]]:
        doorway_set: set[tuple[int, int]] = set()
        for room in rooms:
            for neighbour_id in sorted(room.connected_room_ids):
                neighbour = rooms[neighbour_id]
                tile = self._doorway_for_room(room, neighbour.center)
                if self._in_grid(grid, tile) and is_walkable(int(grid[tile[1], tile[0]])):
                    doorway_set.add(tile)
                    room.doorway_candidates.append(tile)

        for x, y in doorway_set:
            grid[y, x] = int(TileType.DOORWAY)
        return sorted(doorway_set)

    def _doorway_for_room(self, room: Room, target: tuple[int, int]) -> tuple[int, int]:
        tx, ty = target
        cx, cy = room.center
        if abs(tx - cx) >= abs(ty - cy):
            x = room.rect.right - 1 if tx >= cx else room.rect.left
            y = min(max(cy, room.rect.top + 1), room.rect.bottom - 2)
        else:
            x = min(max(cx, room.rect.left + 1), room.rect.right - 2)
            y = room.rect.bottom - 1 if ty >= cy else room.rect.top
        return (x, y)

    def _choose_start_room(self, rooms: list[Room]) -> int:
        candidates = [room for room in rooms if room.rect.area >= 42] or rooms
        return min(candidates, key=lambda room: (room.center[0] + room.center[1], room.center[0], room.center[1])).room_id

    def _mark_room_roles(self, rooms: list[Room], start_room_id: int) -> None:
        rooms[start_room_id].tag = "start"
        rooms[start_room_id].role_flags.add("start")
        rooms[start_room_id].role_flags.add("elevator")

    def _place_start_and_elevator(self, grid: np.ndarray, start_room: Room) -> None:
        elevator = start_room.center
        grid[elevator[1], elevator[0]] = int(TileType.ELEVATOR_FLOOR)

    def _choose_player_spawn(
        self,
        grid: np.ndarray,
        start_room: Room,
        elevator: tuple[int, int],
    ) -> tuple[int, int]:
        preferred = [
            (elevator[0] + 3, elevator[1]),
            (elevator[0] - 3, elevator[1]),
            (elevator[0], elevator[1] + 3),
            (elevator[0], elevator[1] - 3),
        ]
        for tile in preferred + start_room.rect.interior_tiles(margin=1):
            if tile != elevator and start_room.rect.contains(tile) and self._walkable_in_grid(grid, tile):
                return tile
        raise GenerationError("could not place player spawn")

    def _generate_walls(self, grid: np.ndarray, rng: random.Random) -> None:
        wall_tiles: set[tuple[int, int]] = set()
        for y in range(1, grid.shape[0] - 1):
            for x in range(1, grid.shape[1] - 1):
                if is_walkable(int(grid[y, x])):
                    for nx, ny in self._neighbour_tiles_8(x, y):
                        if self._in_grid(grid, (nx, ny)) and TileType(int(grid[ny, nx])) == TileType.VOID:
                            wall_tiles.add((nx, ny))

        for x, y in wall_tiles:
            grid[y, x] = int(TileType.DAMAGED_WALL if rng.random() < 0.08 else TileType.WALL)

    def _apply_floor_variants(self, grid: np.ndarray, rng: random.Random) -> None:
        for y in range(grid.shape[0]):
            for x in range(grid.shape[1]):
                tile = TileType(int(grid[y, x]))
                if tile == TileType.FLOOR:
                    roll = rng.random()
                    if roll < 0.035:
                        grid[y, x] = int(TileType.DAMAGED_FLOOR)
                    elif roll < 0.11:
                        grid[y, x] = int(TileType.FLOOR_ALT)

    def _place_obstacles(
        self,
        grid: np.ndarray,
        rooms: list[Room],
        start_room_id: int,
        player_spawn: tuple[int, int],
        doorway_candidates: list[tuple[int, int]],
        config: GeneratorConfig,
        rng: random.Random,
    ) -> None:
        doorway_set = set(doorway_candidates)
        obstacle_rooms = [
            room
            for room in rooms
            if room.room_id != start_room_id and room.rect.width >= 8 and room.rect.height >= 7
        ]
        rng.shuffle(obstacle_rooms)
        placed_rooms = 0

        for room in obstacle_rooms:
            if placed_rooms >= config.max_obstacle_rooms:
                break

            candidates = [
                tile
                for tile in room.rect.interior_tiles(margin=2)
                if self._valid_obstacle_tile(grid, room, tile, player_spawn, doorway_set)
            ]
            if not candidates:
                continue

            rng.shuffle(candidates)
            for tile in candidates[:8]:
                x, y = tile
                previous = int(grid[y, x])
                grid[y, x] = int(TileType.PILLAR if rng.random() < 0.45 else TileType.OBSTACLE)
                if self._all_walkable_connected(grid, player_spawn):
                    placed_rooms += 1
                    break
                grid[y, x] = previous

    def _valid_obstacle_tile(
        self,
        grid: np.ndarray,
        room: Room,
        tile: tuple[int, int],
        player_spawn: tuple[int, int],
        doorway_set: set[tuple[int, int]],
    ) -> bool:
        x, y = tile
        if tile in doorway_set:
            return False
        if abs(x - player_spawn[0]) <= 3 and abs(y - player_spawn[1]) <= 3:
            return False
        if x == room.center[0] or y == room.center[1]:
            return False
        return self._walkable_in_grid(grid, tile)

    def _candidate_creature_spawns(
        self,
        grid: np.ndarray,
        rooms: list[Room],
        start_room_id: int,
        player_spawn: tuple[int, int],
    ) -> list[tuple[int, int]]:
        candidates: list[tuple[int, int]] = []
        ranked_rooms = sorted(
            (room for room in rooms if room.room_id != start_room_id),
            key=lambda room: (
                -self._distance_squared(room.center, player_spawn),
                -len(room.connected_room_ids),
                room.room_id,
            ),
        )
        for room in ranked_rooms:
            if self._graph_distance(rooms, start_room_id, room.room_id) is not None:
                tile = self._first_walkable_in_room(grid, room)
                if tile is not None and self._distance_squared(tile, player_spawn) >= 18 * 18:
                    candidates.append(tile)
            if len(candidates) >= 8:
                break
        return candidates

    def _candidate_objective_rooms(self, rooms: list[Room], start_room_id: int) -> list[int]:
        return [
            room.room_id
            for room in rooms
            if room.room_id != start_room_id and room.rect.area >= 42
        ]

    def _candidate_material_rooms(self, rooms: list[Room], start_room_id: int) -> list[int]:
        dead_ends = [
            room.room_id
            for room in rooms
            if room.room_id != start_room_id and len(room.connected_room_ids) == 1
        ]
        extras = [
            room.room_id
            for room in rooms
            if room.room_id != start_room_id and room.room_id not in dead_ends
        ]
        return dead_ends + extras[:4]

    def _validate_floor(self, floor: GeneratedFloor) -> bool:
        if len(floor.rooms) < FLOOR_PROFILES.get(floor.floor_number, FLOOR_PROFILES[1])["minimum_rooms"]:
            return False
        if not floor.is_walkable(*floor.player_spawn):
            return False
        if not floor.is_walkable(*floor.elevator_tile):
            return False
        if not self._graph_is_connected(floor.rooms):
            return False
        if not self._all_walkable_connected(floor.tiles, floor.player_spawn):
            return False
        return True

    def _graph_is_connected(self, rooms: list[Room]) -> bool:
        visited = {0}
        queue: deque[int] = deque([0])
        while queue:
            room_id = queue.popleft()
            for neighbour in rooms[room_id].connected_room_ids:
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)
        return len(visited) == len(rooms)

    def _all_walkable_connected(self, grid: np.ndarray, start: tuple[int, int]) -> bool:
        if not self._walkable_in_grid(grid, start):
            return False
        total_walkable = int(np.isin(grid, [int(TileType.FLOOR), int(TileType.FLOOR_ALT), int(TileType.DAMAGED_FLOOR), int(TileType.DOORWAY), int(TileType.ELEVATOR_FLOOR)]).sum())
        visited = {start}
        queue: deque[tuple[int, int]] = deque([start])
        while queue:
            x, y = queue.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                tile = (nx, ny)
                if tile not in visited and self._walkable_in_grid(grid, tile):
                    visited.add(tile)
                    queue.append(tile)
        return len(visited) == total_walkable

    def _first_walkable_in_room(self, grid: np.ndarray, room: Room) -> tuple[int, int] | None:
        for tile in sorted(
            room.rect.interior_tiles(margin=1),
            key=lambda candidate: self._distance_squared(candidate, room.center),
        ):
            if self._walkable_in_grid(grid, tile) and tile not in room.doorway_candidates:
                return tile
        return None

    def _graph_distance(self, rooms: list[Room], start_room_id: int, target_room_id: int) -> int | None:
        visited = {start_room_id}
        queue: deque[tuple[int, int]] = deque([(start_room_id, 0)])
        while queue:
            room_id, distance = queue.popleft()
            if room_id == target_room_id:
                return distance
            for neighbour in rooms[room_id].connected_room_ids:
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append((neighbour, distance + 1))
        return None

    def _walkable_in_grid(self, grid: np.ndarray, tile: tuple[int, int]) -> bool:
        return self._in_grid(grid, tile) and is_walkable(int(grid[tile[1], tile[0]]))

    def _in_grid(self, grid: np.ndarray, tile: tuple[int, int]) -> bool:
        x, y = tile
        return 0 <= y < grid.shape[0] and 0 <= x < grid.shape[1]

    def _neighbour_tiles_8(self, x: int, y: int) -> list[tuple[int, int]]:
        return [
            (x + dx, y + dy)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if not (dx == 0 and dy == 0)
        ]

    def _distance_squared(self, a: tuple[int, int], b: tuple[int, int]) -> int:
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
