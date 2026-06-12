import random
import unittest

import numpy as np

from game.world.generator import FloorGenerator, GenerationError, GeneratorConfig
from game.world.room import Room
from game.world.tiles import TileType, blocks_movement, blocks_scan, is_walkable, tile_asset_index


class GeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = FloorGenerator()
        self.floor = self.generator.generate(seed=12345, floor_number=1)
        self.config = self.generator.config_for_floor(1)

    def test_same_seed_produces_same_tile_grid(self) -> None:
        other = self.generator.generate(seed=12345, floor_number=1)
        self.assertTrue(np.array_equal(self.floor.tiles, other.tiles))

    def test_same_seed_produces_same_room_rectangles(self) -> None:
        other = self.generator.generate(seed=12345, floor_number=1)
        rects = [(room.rect.left, room.rect.top, room.rect.width, room.rect.height) for room in self.floor.rooms]
        other_rects = [(room.rect.left, room.rect.top, room.rect.width, room.rect.height) for room in other.rooms]
        self.assertEqual(rects, other_rects)

    def test_same_seed_produces_same_graph_edges(self) -> None:
        other = self.generator.generate(seed=12345, floor_number=1)
        self.assertEqual(self.floor.graph_edges, other.graph_edges)

    def test_different_seeds_normally_produce_different_layouts(self) -> None:
        other = self.generator.generate(seed=54321, floor_number=1)
        self.assertFalse(np.array_equal(self.floor.tiles, other.tiles))

    def test_generated_map_has_expected_dimensions(self) -> None:
        self.assertEqual((self.floor.width, self.floor.height), (self.config.width, self.config.height))
        self.assertEqual(self.floor.tiles.shape, (self.config.height, self.config.width))

    def test_room_count_is_within_configured_bounds(self) -> None:
        self.assertGreaterEqual(len(self.floor.rooms), self.config.minimum_rooms)
        self.assertLessEqual(len(self.floor.rooms), self.config.maximum_rooms)

    def test_accepted_rooms_do_not_overlap(self) -> None:
        for index, room_a in enumerate(self.floor.rooms):
            for room_b in self.floor.rooms[index + 1 :]:
                self.assertFalse(room_a.rect.intersects(room_b.rect))

    def test_room_padding_rule_is_respected(self) -> None:
        for index, room_a in enumerate(self.floor.rooms):
            for room_b in self.floor.rooms[index + 1 :]:
                self.assertFalse(room_a.rect.intersects(room_b.rect, padding=self.config.room_padding))

    def test_every_graph_room_is_connected_to_graph(self) -> None:
        for room in self.floor.rooms:
            self.assertTrue(room.connected_room_ids)
            for neighbour in room.connected_room_ids:
                self.assertIn(tuple(sorted((room.room_id, neighbour))), self.floor.graph_edges)

    def test_every_graph_edge_has_a_carved_corridor(self) -> None:
        corridor_edges = {corridor.edge for corridor in self.floor.corridors}
        self.assertEqual(corridor_edges, self.floor.graph_edges)
        for corridor in self.floor.corridors:
            for tile in corridor.path:
                self.assertTrue(self.floor.is_walkable(*tile), tile)

    def test_player_spawn_is_in_bounds(self) -> None:
        self.assertTrue(self.floor.in_bounds(*self.floor.player_spawn))

    def test_player_spawn_is_walkable(self) -> None:
        self.assertTrue(self.floor.is_walkable(*self.floor.player_spawn))

    def test_elevator_is_in_bounds(self) -> None:
        self.assertTrue(self.floor.in_bounds(*self.floor.elevator_tile))

    def test_elevator_is_walkable(self) -> None:
        self.assertTrue(self.floor.is_walkable(*self.floor.elevator_tile))

    def test_player_spawn_and_elevator_do_not_overlap_obstacles(self) -> None:
        blocked = {TileType.OBSTACLE, TileType.PILLAR}
        self.assertNotIn(self.floor.tile_at(*self.floor.player_spawn), blocked)
        self.assertNotIn(self.floor.tile_at(*self.floor.elevator_tile), blocked)

    def test_doorway_candidates_are_walkable(self) -> None:
        self.assertTrue(self.floor.doorway_candidates)
        for tile in self.floor.doorway_candidates:
            self.assertTrue(self.floor.is_walkable(*tile), tile)

    def test_obstacles_are_non_walkable(self) -> None:
        obstacle_positions = [
            (x, y)
            for y in range(self.floor.height)
            for x in range(self.floor.width)
            if self.floor.tile_at(x, y) in (TileType.OBSTACLE, TileType.PILLAR)
        ]
        self.assertTrue(obstacle_positions)
        for tile in obstacle_positions:
            self.assertFalse(self.floor.is_walkable(*tile))

    def test_obstacles_do_not_occupy_doorway_candidates(self) -> None:
        doorway_set = set(self.floor.doorway_candidates)
        for y in range(self.floor.height):
            for x in range(self.floor.width):
                if self.floor.tile_at(x, y) in (TileType.OBSTACLE, TileType.PILLAR):
                    self.assertNotIn((x, y), doorway_set)

    def test_generator_respects_bounded_attempt_count(self) -> None:
        impossible = GeneratorConfig(
            width=18,
            height=14,
            target_rooms=20,
            minimum_rooms=20,
            maximum_rooms=20,
            minimum_room_width=10,
            maximum_room_width=12,
            minimum_room_height=8,
            maximum_room_height=9,
            max_room_placement_attempts=2,
            max_generation_attempts=3,
        )
        with self.assertRaises(GenerationError):
            FloorGenerator(impossible).generate(seed=1, floor_number=1)

    def test_generation_does_not_modify_global_random_state(self) -> None:
        random.seed(777)
        before = random.getstate()
        self.generator.generate(seed=777, floor_number=1)
        after = random.getstate()
        self.assertEqual(before, after)

    def test_tile_definitions_expose_rules_and_assets(self) -> None:
        self.assertTrue(is_walkable(TileType.FLOOR))
        self.assertFalse(is_walkable(TileType.WALL))
        self.assertTrue(blocks_movement(TileType.OBSTACLE))
        self.assertTrue(blocks_scan(TileType.VOID))
        self.assertEqual(tile_asset_index(TileType.ELEVATOR_FLOOR), 8)

    def test_candidate_positions_are_exposed_for_later_phases(self) -> None:
        self.assertTrue(self.floor.candidate_creature_spawns)
        self.assertTrue(self.floor.candidate_objective_rooms)
        self.assertTrue(self.floor.candidate_material_rooms)
        self.assertNotIn(self.floor.start_room_id, self.floor.candidate_objective_rooms)

    def test_floor_helper_methods_are_safe(self) -> None:
        self.assertTrue(self.floor.in_bounds(0, 0))
        self.assertFalse(self.floor.in_bounds(-1, 0))
        self.assertEqual(self.floor.world_size_pixels(self.config.tile_size), (3360, 2400))
        self.assertIn(self.floor.player_spawn, self.floor.walkable_tiles())


if __name__ == "__main__":
    unittest.main()
