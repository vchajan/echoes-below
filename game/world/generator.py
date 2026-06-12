from __future__ import annotations

from dataclasses import dataclass, replace
import random

import numpy as np

from game.world.floor import Corridor, DoorwayCandidate, GateCandidate, GeneratedFloor
from game.world.room import Room, RoomRect
from game.world.tiles import TileType, is_walkable
from game.world.validation import (
    cycle_rank,
    doorway_orientation,
    elevator_approach_tiles,
    graph_bfs,
    graph_distance,
    is_creature_spawn_safe,
    is_obstacle_placement_safe,
    select_separated_spawns,
    shortest_tile_path,
    tile_distance,
    validate_floor,
)


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
    max_generation_attempts: int = 25
    max_obstacle_rooms: int = 4
    required_cycle_rank: int = 0
    preferred_cycle_rank: int = 1
    extra_graph_edges: int = 1
    minimum_creature_candidates: int = 1
    minimum_objective_candidates: int = 4
    minimum_material_candidates: int = 2
    creature_minimum_distance: int = 12
    creature_pairwise_distance: int = 8
    player_clearance_radius: int = 1


FLOOR_PROFILES: dict[int, dict[str, int]] = {
    1: {
        "target_rooms": 9,
        "minimum_rooms": 8,
        "maximum_rooms": 10,
        "max_obstacle_rooms": 3,
        "required_cycle_rank": 0,
        "preferred_cycle_rank": 1,
        "extra_graph_edges": 1,
        "minimum_creature_candidates": 1,
        "minimum_objective_candidates": 4,
        "minimum_material_candidates": 2,
        "creature_minimum_distance": 12,
    },
    2: {
        "target_rooms": 12,
        "minimum_rooms": 11,
        "maximum_rooms": 13,
        "max_obstacle_rooms": 5,
        "required_cycle_rank": 1,
        "preferred_cycle_rank": 1,
        "extra_graph_edges": 2,
        "minimum_creature_candidates": 2,
        "minimum_objective_candidates": 6,
        "minimum_material_candidates": 3,
        "creature_minimum_distance": 14,
    },
    3: {
        "target_rooms": 14,
        "minimum_rooms": 13,
        "maximum_rooms": 16,
        "max_obstacle_rooms": 6,
        "required_cycle_rank": 1,
        "preferred_cycle_rank": 2,
        "extra_graph_edges": 2,
        "minimum_creature_candidates": 2,
        "minimum_objective_candidates": 7,
        "minimum_material_candidates": 3,
        "creature_minimum_distance": 14,
    },
}


class FloorGenerator:
    def __init__(self, config: GeneratorConfig | None = None) -> None:
        self.base_config = config or GeneratorConfig()

    def config_for_floor(self, floor_number: int) -> GeneratorConfig:
        profile = FLOOR_PROFILES.get(floor_number, FLOOR_PROFILES[1])
        return replace(self.base_config, **profile)

    def derive_attempt_seed(self, seed: int, floor_number: int, attempt: int) -> int:
        # Stable integer mix; avoids process-randomised hash() and OS entropy.
        modulus = 2**63 - 1
        mixed = (abs(seed) * 1_000_003 + floor_number * 100_913 + attempt * 9_176 + 0x5EED) % modulus
        return mixed if seed >= 0 else (modulus - mixed)

    def generate(self, seed: int, floor_number: int = 1) -> GeneratedFloor:
        config = self.config_for_floor(floor_number)
        validation_errors: list[str] = []

        for attempt in range(1, config.max_generation_attempts + 1):
            attempt_seed = self.derive_attempt_seed(seed, floor_number, attempt)
            rng = random.Random(attempt_seed)
            try:
                floor = self._generate_attempt(seed, floor_number, attempt_seed, config, attempt, rng)
            except GenerationError as exc:
                validation_errors = [str(exc)]
                continue

            report = validate_floor(floor, config)
            floor.validation_report = report
            if report.is_valid:
                if floor_number >= 2 and not floor.gate_candidates:
                    validation_errors = ["floor requires at least one gate candidate"]
                    continue
                return floor
            validation_errors = report.errors

        final_errors = "; ".join(validation_errors[:5]) if validation_errors else "unknown validation failure"
        raise GenerationError(
            f"Could not generate valid floor for seed={seed}, floor={floor_number} "
            f"after {config.max_generation_attempts} attempts: {final_errors}"
        )

    def _generate_attempt(
        self,
        seed: int,
        floor_number: int,
        attempt_seed: int,
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

        graph_edges = self._build_graph(rooms, config, rng)
        corridors = self._carve_corridors(grid, rooms, graph_edges, config, rng)
        start_room_id = self._choose_start_room(rooms)
        self._mark_room_roles(rooms, start_room_id)

        doorway_candidates, doorway_data = self._collect_doorways(grid, rooms)
        elevator_tile = rooms[start_room_id].center
        self._place_start_and_elevator(grid, elevator_tile)
        player_spawn = self._choose_player_spawn(grid, rooms[start_room_id], elevator_tile, doorway_candidates)

        self._generate_walls(grid, rng)
        self._apply_floor_variants(grid, rng)
        self._place_obstacles(grid, rooms, start_room_id, player_spawn, elevator_tile, doorway_candidates, config, rng)

        elevator_approaches = elevator_approach_tiles(grid, elevator_tile)
        candidate_creature_spawns = self._candidate_creature_spawns(
            grid,
            rooms,
            graph_edges,
            start_room_id,
            player_spawn,
            elevator_tile,
            doorway_candidates,
            config,
        )
        objective_groups = self._objective_room_groups(grid, rooms, graph_edges, start_room_id)
        candidate_objective_rooms = objective_groups["far"] + objective_groups["middle"] + objective_groups["near"]
        material_scores = self._material_room_scores(rooms, graph_edges, start_room_id, candidate_objective_rooms)
        candidate_material_rooms = [room_id for room_id, _ in sorted(material_scores.items(), key=lambda item: (-item[1], item[0]))]
        gate_candidates = self._gate_candidates(rooms, graph_edges, doorway_data, start_room_id)
        containment_candidates = self._containment_room_candidates(rooms, graph_edges, start_room_id, gate_candidates)
        self._apply_candidate_role_flags(
            rooms,
            objective_groups,
            candidate_material_rooms,
            gate_candidates,
            containment_candidates,
            candidate_creature_spawns,
        )

        return GeneratedFloor(
            seed=seed,
            floor_number=floor_number,
            attempt_seed=attempt_seed,
            width=config.width,
            height=config.height,
            tiles=grid,
            rooms=rooms,
            graph_edges=graph_edges,
            corridors=corridors,
            start_room_id=start_room_id,
            player_spawn=player_spawn,
            elevator_tile=elevator_tile,
            elevator_approach_tiles=elevator_approaches,
            doorway_candidates=doorway_candidates,
            doorway_data=doorway_data,
            candidate_creature_spawns=candidate_creature_spawns,
            candidate_objective_rooms=candidate_objective_rooms,
            objective_room_groups=objective_groups,
            candidate_material_rooms=candidate_material_rooms,
            material_room_scores=material_scores,
            gate_candidates=gate_candidates,
            containment_room_candidates=containment_candidates,
            generation_attempt=attempt,
            corridor_width=config.corridor_width,
            metadata={
                "max_generation_attempts": config.max_generation_attempts,
                "max_room_placement_attempts": config.max_room_placement_attempts,
                "required_cycle_rank": config.required_cycle_rank,
                "preferred_cycle_rank": config.preferred_cycle_rank,
            },
        )

    def _place_rooms(self, config: GeneratorConfig, rng: random.Random) -> list[Room]:
        available_width = config.width - config.safe_border * 2
        available_height = config.height - config.safe_border * 2
        if (
            available_width < config.minimum_room_width
            or available_height < config.minimum_room_height
        ):
            raise GenerationError("map is too small for configured room sizes")

        rooms: list[Room] = []
        target = rng.randint(config.minimum_rooms, config.maximum_rooms)

        for _ in range(config.max_room_placement_attempts):
            if len(rooms) >= target:
                break

            width = rng.randint(config.minimum_room_width, min(config.maximum_room_width, available_width))
            height = rng.randint(config.minimum_room_height, min(config.maximum_room_height, available_height))
            left = rng.randint(config.safe_border, config.width - config.safe_border - width)
            top = rng.randint(config.safe_border, config.height - config.safe_border - height)
            rect = RoomRect(left, top, width, height)

            if any(rect.intersects(room.rect, padding=config.room_padding) for room in rooms):
                continue

            rooms.append(Room(room_id=len(rooms), rect=rect))

        return rooms

    def _carve_room(self, grid: np.ndarray, room: Room) -> None:
        grid[room.rect.top : room.rect.bottom, room.rect.left : room.rect.right] = int(TileType.FLOOR)

    def _build_graph(self, rooms: list[Room], config: GeneratorConfig, rng: random.Random) -> set[tuple[int, int]]:
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

        extra_candidates = [
            (self._distance_squared(room_a.center, room_b.center), room_a.room_id, room_b.room_id)
            for index, room_a in enumerate(rooms)
            for room_b in rooms[index + 1 :]
            if tuple(sorted((room_a.room_id, room_b.room_id))) not in edges
        ]
        extra_candidates.sort(reverse=True)
        rng.shuffle(extra_candidates)
        extra_candidates.sort(reverse=True)

        for _, room_a, room_b in extra_candidates:
            if cycle_rank(len(rooms), edges) >= config.preferred_cycle_rank and len(edges) >= len(rooms) - 1 + config.extra_graph_edges:
                break
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

    def _collect_doorways(self, grid: np.ndarray, rooms: list[Room]) -> tuple[list[tuple[int, int]], list[DoorwayCandidate]]:
        doorway_tiles: set[tuple[int, int]] = set()
        doorway_data: dict[tuple[tuple[int, int], tuple[int, int]], DoorwayCandidate] = {}

        for room in rooms:
            for neighbour_id in sorted(room.connected_room_ids):
                neighbour = rooms[neighbour_id]
                tile = self._doorway_for_room(room, neighbour.center)
                if self._in_grid(grid, tile) and is_walkable(int(grid[tile[1], tile[0]])):
                    grid[tile[1], tile[0]] = int(TileType.DOORWAY)
                    orientation = doorway_orientation(grid, tile) or "unknown"
                    edge = tuple(sorted((room.room_id, neighbour_id)))
                    doorway_tiles.add(tile)
                    candidate = DoorwayCandidate(
                        tile=tile,
                        room_id=room.room_id,
                        connected_room_id=neighbour_id,
                        orientation=orientation,
                    )
                    doorway_data[(tile, edge)] = candidate
                    room.doorway_candidates.append(tile)

        return sorted(doorway_tiles), sorted(doorway_data.values(), key=lambda item: (item.tile, item.edge))

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

    def _place_start_and_elevator(self, grid: np.ndarray, elevator: tuple[int, int]) -> None:
        grid[elevator[1], elevator[0]] = int(TileType.ELEVATOR_FLOOR)

    def _choose_player_spawn(
        self,
        grid: np.ndarray,
        start_room: Room,
        elevator: tuple[int, int],
        doorway_candidates: list[tuple[int, int]],
    ) -> tuple[int, int]:
        preferred = [
            (elevator[0] + 3, elevator[1]),
            (elevator[0] - 3, elevator[1]),
            (elevator[0], elevator[1] + 3),
            (elevator[0], elevator[1] - 3),
        ]
        for tile in preferred + start_room.rect.interior_tiles(margin=2):
            if (
                tile != elevator
                and tile not in doorway_candidates
                and start_room.rect.contains(tile)
                and self._walkable_in_grid(grid, tile)
            ):
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
        elevator_tile: tuple[int, int],
        doorway_candidates: list[tuple[int, int]],
        config: GeneratorConfig,
        rng: random.Random,
    ) -> None:
        forbidden = set(doorway_candidates) | {player_spawn, elevator_tile}
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
                if self._valid_obstacle_tile(grid, room, tile, player_spawn, forbidden)
            ]
            rng.shuffle(candidates)
            for tile in candidates[:12]:
                if not is_obstacle_placement_safe(grid, tile, player_spawn, forbidden):
                    continue
                x, y = tile
                grid[y, x] = int(TileType.PILLAR if rng.random() < 0.45 else TileType.OBSTACLE)
                placed_rooms += 1
                break

    def _valid_obstacle_tile(
        self,
        grid: np.ndarray,
        room: Room,
        tile: tuple[int, int],
        player_spawn: tuple[int, int],
        forbidden: set[tuple[int, int]],
    ) -> bool:
        x, y = tile
        if tile in forbidden:
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
        graph_edges: set[tuple[int, int]],
        start_room_id: int,
        player_spawn: tuple[int, int],
        elevator_tile: tuple[int, int],
        doorway_candidates: list[tuple[int, int]],
        config: GeneratorConfig,
    ) -> list[tuple[int, int]]:
        start_room = rooms[start_room_id]
        ranked_rooms = sorted(
            (room for room in rooms if room.room_id != start_room_id),
            key=lambda room: (
                -(graph_distance(len(rooms), graph_edges, start_room_id, room.room_id) or 0),
                -self._distance_squared(room.center, player_spawn),
                room.room_id,
            ),
        )
        raw_candidates: list[tuple[int, int]] = []
        for room in ranked_rooms:
            for tile in sorted(room.rect.interior_tiles(margin=2), key=lambda candidate: self._distance_squared(candidate, room.center)):
                if is_creature_spawn_safe(
                    grid,
                    tile,
                    player_spawn,
                    start_room,
                    doorway_candidates,
                    elevator_tile,
                    config.creature_minimum_distance,
                ):
                    raw_candidates.append(tile)
                    break
        return select_separated_spawns(
            grid,
            raw_candidates,
            max(config.minimum_creature_candidates + 2, 4),
            config.creature_pairwise_distance,
        )

    def _objective_room_groups(
        self,
        grid: np.ndarray,
        rooms: list[Room],
        graph_edges: set[tuple[int, int]],
        start_room_id: int,
    ) -> dict[str, list[int]]:
        groups: dict[str, list[int]] = {"near": [], "middle": [], "far": []}
        distances = {
            room.room_id: graph_distance(len(rooms), graph_edges, start_room_id, room.room_id)
            for room in rooms
            if room.room_id != start_room_id and room.rect.area >= 42
        }
        known = [distance for distance in distances.values() if distance is not None]
        if not known:
            return groups
        far_threshold = max(3, max(known) - 1)
        for room_id, distance in sorted(distances.items(), key=lambda item: (item[1] or 0, item[0])):
            if distance is None:
                continue
            room = rooms[room_id]
            if not any(self._walkable_in_grid(grid, tile) for tile in room.rect.interior_tiles(margin=1)):
                continue
            if distance <= 1:
                groups["near"].append(room_id)
            elif distance >= far_threshold:
                groups["far"].append(room_id)
            else:
                groups["middle"].append(room_id)
        return groups

    def _material_room_scores(
        self,
        rooms: list[Room],
        graph_edges: set[tuple[int, int]],
        start_room_id: int,
        objective_rooms: list[int],
    ) -> dict[int, int]:
        objective_set = set(objective_rooms[:3])
        scores: dict[int, int] = {}
        for room in rooms:
            if room.room_id == start_room_id or room.room_id in objective_set:
                continue
            distance = graph_distance(len(rooms), graph_edges, start_room_id, room.room_id) or 0
            score = distance * 3 + room.rect.area // 12
            if len(room.connected_room_ids) == 1:
                score += 8
                room.role_flags.add("reward_dead_end")
            scores[room.room_id] = score
        return scores

    def _gate_candidates(
        self,
        rooms: list[Room],
        graph_edges: set[tuple[int, int]],
        doorway_data: list[DoorwayCandidate],
        start_room_id: int,
    ) -> list[GateCandidate]:
        candidates: list[GateCandidate] = []
        for edge in sorted(graph_edges):
            remaining_edges = {other for other in graph_edges if other != edge}
            key_side = graph_bfs(len(rooms), remaining_edges, start_room_id)
            if len(key_side) == len(rooms):
                continue
            gated = tuple(sorted(set(range(len(rooms))) - key_side))
            doorways = tuple(sorted(item.tile for item in doorway_data if item.edge == edge))
            distance_score = max((graph_distance(len(rooms), graph_edges, start_room_id, room_id) or 0) for room_id in gated)
            candidates.append(
                GateCandidate(
                    edge=edge,
                    key_side_rooms=tuple(sorted(key_side)),
                    gated_rooms=gated,
                    doorway_tiles=doorways,
                    score=distance_score + len(gated) * 2,
                )
            )
        return sorted(candidates, key=lambda item: (-item.score, item.edge))

    def _containment_room_candidates(
        self,
        rooms: list[Room],
        graph_edges: set[tuple[int, int]],
        start_room_id: int,
        gate_candidates: list[GateCandidate],
    ) -> list[int]:
        gated_rooms = [room_id for gate in gate_candidates[:3] for room_id in gate.gated_rooms]
        ranked = sorted(
            set(gated_rooms) | {room.room_id for room in rooms if room.room_id != start_room_id and room.rect.area >= 56},
            key=lambda room_id: (
                -(graph_distance(len(rooms), graph_edges, start_room_id, room_id) or 0),
                -rooms[room_id].rect.area,
                room_id,
            ),
        )
        return [room_id for room_id in ranked if room_id != start_room_id]

    def _apply_candidate_role_flags(
        self,
        rooms: list[Room],
        objective_groups: dict[str, list[int]],
        material_rooms: list[int],
        gate_candidates: list[GateCandidate],
        containment_candidates: list[int],
        creature_spawns: list[tuple[int, int]],
    ) -> None:
        for group, room_ids in objective_groups.items():
            for room_id in room_ids:
                rooms[room_id].role_flags.add("objective_room")
                rooms[room_id].role_flags.add(f"objective_{group}")
        for room_id in material_rooms:
            rooms[room_id].role_flags.add("material_room")
        for gate in gate_candidates[:3]:
            for room_id in gate.gated_rooms:
                rooms[room_id].role_flags.add("gated_room")
        for room_id in containment_candidates[:3]:
            rooms[room_id].role_flags.add("containment_room")
        for spawn in creature_spawns:
            for room in rooms:
                if room.rect.contains(spawn):
                    room.role_flags.add("creature_spawn_room")
                    break

    def _in_grid(self, grid: np.ndarray, tile: tuple[int, int]) -> bool:
        x, y = tile
        return 0 <= y < grid.shape[0] and 0 <= x < grid.shape[1]

    def _walkable_in_grid(self, grid: np.ndarray, tile: tuple[int, int]) -> bool:
        return self._in_grid(grid, tile) and is_walkable(int(grid[tile[1], tile[0]]))

    def _neighbour_tiles_8(self, x: int, y: int) -> list[tuple[int, int]]:
        return [
            (x + dx, y + dy)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if not (dx == 0 and dy == 0)
        ]

    def _distance_squared(self, a: tuple[int, int], b: tuple[int, int]) -> int:
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
