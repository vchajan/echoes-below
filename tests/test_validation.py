import random
import unittest

import numpy as np

from game.world.floor import Corridor, GeneratedFloor
from game.world.generator import FloorGenerator, GenerationError, GeneratorConfig
from game.world.room import Room, RoomRect
from game.world.tiles import TileType
from game.world.validation import (
    cycle_rank,
    flood_fill,
    graph_bfs,
    is_creature_spawn_safe,
    is_doorway_valid,
    is_elevator_safe,
    is_obstacle_placement_safe,
    is_player_spawn_safe,
    normalize_edge,
    select_separated_spawns,
    shortest_tile_path,
    unique_edges,
    validate_floor,
)


def grid_from_rows(rows: list[list[TileType]]) -> np.ndarray:
    return np.array([[int(tile) for tile in row] for row in rows], dtype=np.int16)


def make_room(room_id: int, left: int, top: int, width: int, height: int) -> Room:
    return Room(room_id=room_id, rect=RoomRect(left, top, width, height))


def make_minimal_floor(grid: np.ndarray, edges: set[tuple[int, int]]) -> GeneratedFloor:
    rooms = [
        make_room(0, 1, 1, 3, 3),
        make_room(1, 5, 1, 3, 3),
        make_room(2, 5, 5, 3, 3),
    ]
    for room_a, room_b in edges:
        rooms[room_a].connected_room_ids.add(room_b)
        rooms[room_b].connected_room_ids.add(room_a)
    return GeneratedFloor(
        seed=1,
        floor_number=2,
        attempt_seed=123,
        width=grid.shape[1],
        height=grid.shape[0],
        tiles=grid,
        rooms=rooms,
        graph_edges=edges,
        corridors=[Corridor(room_a=a, room_b=b, path=((rooms[a].center), (rooms[b].center))) for a, b in edges],
        start_room_id=0,
        player_spawn=(2, 2),
        elevator_tile=(3, 2),
        elevator_approach_tiles=[(2, 2)],
        doorway_candidates=[(4, 2)],
        doorway_data=[],
        candidate_creature_spawns=[(6, 6)],
        candidate_objective_rooms=[1],
        objective_room_groups={"near": [1], "middle": [], "far": []},
        candidate_material_rooms=[2],
        material_room_scores={2: 10},
        gate_candidates=[],
        containment_room_candidates=[2],
        generation_attempt=1,
        corridor_width=2,
    )


class ValidationFunctionTests(unittest.TestCase):
    def test_bfs_reaches_all_tiles_in_connected_map(self) -> None:
        grid = grid_from_rows(
            [
                [TileType.FLOOR, TileType.FLOOR, TileType.FLOOR],
                [TileType.FLOOR, TileType.FLOOR, TileType.FLOOR],
            ]
        )
        self.assertEqual(len(flood_fill(grid, (0, 0))), 6)

    def test_bfs_detects_disconnected_walkable_island(self) -> None:
        grid = grid_from_rows(
            [[TileType.FLOOR, TileType.WALL, TileType.FLOOR]]
        )
        self.assertEqual(len(flood_fill(grid, (0, 0))), 1)

    def test_graph_bfs_detects_disconnected_room(self) -> None:
        self.assertEqual(graph_bfs(3, {(0, 1)}, 0), {0, 1})

    def test_cycle_rank_is_zero_for_tree(self) -> None:
        self.assertEqual(cycle_rank(3, {(0, 1), (1, 2)}), 0)

    def test_cycle_rank_is_one_for_single_cycle(self) -> None:
        self.assertEqual(cycle_rank(3, {(0, 1), (1, 2), (0, 2)}), 1)

    def test_duplicate_edge_is_normalised(self) -> None:
        self.assertEqual(unique_edges([(0, 1), (1, 0)]), {(0, 1)})

    def test_self_edge_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_edge(1, 1)

    def test_safe_player_spawn_passes_clearance_check(self) -> None:
        grid = np.full((5, 5), int(TileType.FLOOR), dtype=np.int16)
        room = make_room(0, 0, 0, 5, 5)
        self.assertTrue(is_player_spawn_safe(grid, (2, 2), room, (1, 1), []))

    def test_unsafe_player_spawn_near_blocked_neighbours_fails(self) -> None:
        grid = grid_from_rows(
            [
                [TileType.WALL, TileType.WALL, TileType.WALL],
                [TileType.WALL, TileType.FLOOR, TileType.WALL],
                [TileType.WALL, TileType.FLOOR, TileType.WALL],
            ]
        )
        room = make_room(0, 0, 0, 3, 3)
        self.assertFalse(is_player_spawn_safe(grid, (1, 1), room, (1, 2), []))

    def test_elevator_approach_area_is_valid(self) -> None:
        grid = np.full((5, 5), int(TileType.FLOOR), dtype=np.int16)
        room = make_room(0, 0, 0, 5, 5)
        self.assertTrue(is_elevator_safe(grid, (2, 2), room, (1, 2), []))

    def test_creature_spawn_too_close_to_player_is_rejected(self) -> None:
        grid = np.full((6, 6), int(TileType.FLOOR), dtype=np.int16)
        start_room = make_room(0, 0, 0, 2, 2)
        self.assertFalse(is_creature_spawn_safe(grid, (2, 1), (1, 1), start_room, [], (0, 0), 8))

    def test_creature_spawn_with_enough_bfs_distance_is_accepted(self) -> None:
        grid = np.full((3, 12), int(TileType.FLOOR), dtype=np.int16)
        start_room = make_room(0, 0, 0, 2, 3)
        self.assertTrue(is_creature_spawn_safe(grid, (10, 1), (1, 1), start_room, [], (0, 0), 8))

    def test_pairwise_creature_spawn_separation_works(self) -> None:
        grid = np.full((3, 20), int(TileType.FLOOR), dtype=np.int16)
        selected = select_separated_spawns(grid, [(2, 1), (4, 1), (12, 1)], 2, 6)
        self.assertEqual(selected, [(2, 1), (12, 1)])

    def test_obstacle_that_disconnects_corridor_is_rejected(self) -> None:
        grid = grid_from_rows([[TileType.FLOOR, TileType.FLOOR, TileType.FLOOR]])
        self.assertFalse(is_obstacle_placement_safe(grid, (1, 0), (0, 0)))

    def test_safe_obstacle_remains_connected(self) -> None:
        grid = np.full((3, 3), int(TileType.FLOOR), dtype=np.int16)
        self.assertTrue(is_obstacle_placement_safe(grid, (1, 1), (0, 0)))

    def test_doorway_candidate_has_walkable_tiles_on_both_sides(self) -> None:
        grid = grid_from_rows([[TileType.FLOOR, TileType.DOORWAY, TileType.FLOOR]])
        self.assertTrue(is_doorway_valid(grid, (1, 0)))

    def test_invalid_diagonal_doorway_is_rejected(self) -> None:
        grid = grid_from_rows(
            [
                [TileType.FLOOR, TileType.WALL, TileType.FLOOR],
                [TileType.WALL, TileType.DOORWAY, TileType.WALL],
                [TileType.FLOOR, TileType.WALL, TileType.FLOOR],
            ]
        )
        self.assertFalse(is_doorway_valid(grid, (1, 1)))

    def test_floor2_without_cycle_fails_profile_validation(self) -> None:
        grid = np.full((9, 9), int(TileType.FLOOR), dtype=np.int16)
        floor = make_minimal_floor(grid, {(0, 1), (1, 2)})
        profile = GeneratorConfig(minimum_rooms=3, maximum_rooms=3, required_cycle_rank=1)
        report = validate_floor(floor, profile)
        self.assertFalse(report.is_valid)
        self.assertTrue(any("cycle rank" in error for error in report.errors))

    def test_floor3_without_enough_candidate_rooms_fails_validation(self) -> None:
        grid = np.full((9, 9), int(TileType.FLOOR), dtype=np.int16)
        floor = make_minimal_floor(grid, {(0, 1), (1, 2), (0, 2)})
        profile = GeneratorConfig(
            minimum_rooms=3,
            maximum_rooms=3,
            required_cycle_rank=1,
            minimum_objective_candidates=3,
        )
        report = validate_floor(floor, profile)
        self.assertFalse(report.is_valid)
        self.assertTrue(any("objective" in error for error in report.errors))

    def test_same_base_seed_and_attempt_sequence_remain_deterministic(self) -> None:
        generator = FloorGenerator()
        first = generator.generate(2468, 3)
        second = generator.generate(2468, 3)
        self.assertEqual(first.generation_attempt, second.generation_attempt)
        self.assertEqual(first.attempt_seed, second.attempt_seed)
        self.assertTrue(np.array_equal(first.tiles, second.tiles))

    def test_impossible_generator_configuration_raises_bounded_custom_exception(self) -> None:
        config = GeneratorConfig(
            width=15,
            height=12,
            minimum_rooms=20,
            maximum_rooms=20,
            target_rooms=20,
            minimum_room_width=10,
            maximum_room_width=12,
            minimum_room_height=8,
            maximum_room_height=9,
            max_room_placement_attempts=2,
            max_generation_attempts=2,
        )
        with self.assertRaises(GenerationError):
            FloorGenerator(config).generate(1, 1)

    def test_global_random_state_remains_unaffected(self) -> None:
        random.seed(444)
        before = random.getstate()
        FloorGenerator().generate(444, 2)
        after = random.getstate()
        self.assertEqual(before, after)

    def test_shortest_tile_path_reconstructs_route(self) -> None:
        grid = np.full((1, 4), int(TileType.FLOOR), dtype=np.int16)
        self.assertEqual(shortest_tile_path(grid, (0, 0), (3, 0)), [(0, 0), (1, 0), (2, 0), (3, 0)])


if __name__ == "__main__":
    unittest.main()
