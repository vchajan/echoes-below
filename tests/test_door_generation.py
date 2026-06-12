import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.assets import AssetManager
from game.entities.door import DoorType
from game.world.door_generation import create_doors_for_floor
from game.world.generator import FloorGenerator


class DoorGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = AssetManager(audio_available=False)
        cls.generator = FloorGenerator()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def create(self, seed: int, floor_number: int):
        floor = self.generator.generate(seed, floor_number)
        result = create_doors_for_floor(floor, self.assets, settings.TILE_SIZE)
        return floor, result.doors, result.blockers

    def test_every_generated_door_references_valid_doorway_candidate(self) -> None:
        floor, doors, _ = self.create(12345, 2)
        candidates = set(floor.doorway_candidates)
        self.assertTrue(doors)
        for door in doors:
            self.assertIn(door.tile, candidates)

    def test_door_orientation_matches_doorway_metadata(self) -> None:
        floor, doors, _ = self.create(12345, 2)
        orientation_by_tile = {record.tile: record.orientation for record in floor.doorway_data}
        for door in doors:
            self.assertEqual(door.orientation, orientation_by_tile[door.tile])

    def test_door_collision_aligns_with_passage(self) -> None:
        _, doors, _ = self.create(12345, 2)
        for door in doors:
            tile_center = ((door.tile[0] + 0.5) * settings.TILE_SIZE, (door.tile[1] + 0.5) * settings.TILE_SIZE)
            self.assertEqual(door.collision_rect.center, (round(tile_center[0]), round(tile_center[1])))
            if door.orientation == "vertical_door_plane":
                self.assertLess(door.collision_rect.width, door.collision_rect.height)
            else:
                self.assertGreater(door.collision_rect.width, door.collision_rect.height)

    def test_no_duplicate_door_ids(self) -> None:
        _, doors, _ = self.create(12345, 3)
        self.assertEqual(len({door.door_id for door in doors}), len(doors))

    def test_no_duplicate_door_on_same_doorway(self) -> None:
        _, doors, _ = self.create(12345, 3)
        self.assertEqual(len({door.tile for door in doors}), len(doors))

    def test_same_seed_creates_same_door_types_and_placements(self) -> None:
        _, first_doors, _ = self.create(2468, 3)
        _, second_doors, _ = self.create(2468, 3)
        first = [(door.door_id, door.door_type, door.tile, door.orientation) for door in first_doors]
        second = [(door.door_id, door.door_type, door.tile, door.orientation) for door in second_doors]
        self.assertEqual(first, second)

    def test_floor1_uses_only_powered_temporary_doors(self) -> None:
        _, doors, _ = self.create(12345, 1)
        self.assertTrue(doors)
        self.assertTrue(all(door.door_type is DoorType.POWERED for door in doors))
        self.assertTrue(all(not door.is_locked for door in doors))

    def test_floor2_has_security_door_from_gate_candidate(self) -> None:
        floor, doors, _ = self.create(12345, 2)
        security_doors = [door for door in doors if door.door_type is DoorType.SECURITY]
        self.assertEqual(len(security_doors), 1)
        gate_tiles = set(floor.gate_candidates[0].doorway_tiles)
        self.assertIn(security_doors[0].tile, gate_tiles)

    def test_floor3_has_containment_door_candidate(self) -> None:
        floor, doors, _ = self.create(12345, 3)
        containment_doors = [door for door in doors if door.door_type is DoorType.CONTAINMENT]
        self.assertEqual(len(containment_doors), 1)
        all_gate_tiles = {tile for gate in floor.gate_candidates for tile in gate.doorway_tiles}
        self.assertIn(containment_doors[0].tile, all_gate_tiles)

    def test_door_does_not_overlap_player_spawn(self) -> None:
        floor, doors, _ = self.create(12345, 1)
        self.assertNotIn(floor.player_spawn, {door.tile for door in doors})

    def test_door_does_not_overlap_elevator(self) -> None:
        floor, doors, _ = self.create(12345, 1)
        self.assertNotIn(floor.elevator_tile, {door.tile for door in doors})

    def test_blocker_registry_uses_generated_doors(self) -> None:
        _, doors, blockers = self.create(12345, 2)
        self.assertEqual(blockers.doors, doors)
        self.assertTrue(blockers.blocks_tile(*doors[0].tile))


if __name__ == "__main__":
    unittest.main()
