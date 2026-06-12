import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.app import Game
from game.assets import AssetManager
from game.entities.scan_objects import ElevatorState, MaterialType
from game.world.content_generation import create_floor_content
from game.world.generator import FloorGenerator


class FloorContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((320, 240))
        cls.assets = AssetManager(audio_available=False)
        cls.generator = FloorGenerator()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def create(self, seed: int = 12345, floor_number: int = 1):
        floor = self.generator.generate(seed, floor_number)
        return floor, create_floor_content(floor, self.assets, settings.TILE_SIZE)

    def test_content_placement_is_deterministic(self) -> None:
        _, first = self.create(12345, 2)
        _, second = self.create(12345, 2)
        self.assertEqual(
            [(pickup.unique_id, pickup.tile, pickup.material_type) for pickup in first.materials],
            [(pickup.unique_id, pickup.tile, pickup.material_type) for pickup in second.materials],
        )
        self.assertEqual(first.elevator.unique_id, second.elevator.unique_id)

    def test_floor_one_contains_three_materials(self) -> None:
        _, content = self.create(12345, 1)
        self.assertEqual(len(content.materials), 3)
        self.assertEqual({pickup.material_type for pickup in content.materials}, set(MaterialType))

    def test_materials_are_on_walkable_unreserved_tiles(self) -> None:
        floor, content = self.create(12345, 3)
        reserved = {floor.player_spawn, floor.elevator_tile, *floor.elevator_approach_tiles, *floor.doorway_candidates}
        tiles = [pickup.tile for pickup in content.materials]
        self.assertEqual(len(tiles), len(set(tiles)))
        for tile in tiles:
            self.assertTrue(floor.is_walkable(*tile))
            self.assertNotIn(tile, reserved)

    def test_material_collect_is_idempotent(self) -> None:
        _, content = self.create()
        pickup = content.materials[0]
        self.assertTrue(pickup.collect())
        self.assertFalse(pickup.collect())
        self.assertTrue(pickup.collected)
        self.assertFalse(pickup.scan_active)

    def test_elevator_state_changes_outline_frame(self) -> None:
        _, content = self.create()
        elevator = content.elevator
        locked = pygame.image.tobytes(elevator.capture_scan_outline(), "RGBA")
        elevator.unlock()
        unlocked = pygame.image.tobytes(elevator.capture_scan_outline(), "RGBA")
        self.assertEqual(elevator.state, ElevatorState.UNLOCKED)
        self.assertNotEqual(locked, unlocked)

    def test_elevator_interaction_rect_contains_approach(self) -> None:
        floor, content = self.create()
        for tile in [floor.elevator_tile, *floor.elevator_approach_tiles]:
            point = ((tile[0] + 0.5) * settings.TILE_SIZE, (tile[1] + 0.5) * settings.TILE_SIZE)
            self.assertTrue(content.elevator.interaction_rect.collidepoint(point))


class GameContentIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game()
        self.game.start_new_run()

    def tearDown(self) -> None:
        self.game.shutdown()

    def test_new_run_creates_materials_and_elevator(self) -> None:
        self.assertIsNotNone(self.game.floor_content)
        self.assertGreaterEqual(len(self.game.material_pickups), 3)
        self.assertIsNotNone(self.game.elevator_entity)

    def test_player_collects_material_once_and_updates_run(self) -> None:
        pickup = self.game.material_pickups[0]
        material = pickup.material_type.value
        self.game.player.place_at_tile(pickup.tile)
        self.game.camera.update(self.game.player.world_position)
        self.game.update_gameplay(0.0, pygame.Vector2())
        self.assertEqual(self.game.placeholder_run.material_counts[material], 1)
        self.assertEqual(self.game.placeholder_run.score, settings.MATERIAL_PICKUP_SCORE)
        self.game.update_gameplay(0.0, pygame.Vector2())
        self.assertEqual(self.game.placeholder_run.material_counts[material], 1)
        self.assertEqual(self.game.placeholder_run.score, settings.MATERIAL_PICKUP_SCORE)

    def test_scan_at_pickup_creates_historical_snapshot_before_collection(self) -> None:
        pickup = self.game.material_pickups[0]
        self.game.player.place_at_tile(pickup.tile)
        self.game.camera.update(self.game.player.world_position)
        self.assertTrue(self.game.trigger_scan())
        self.game.update_gameplay(0.01, pygame.Vector2())
        snapshots = self.game.snapshot_system.snapshots_for_source(pickup.unique_id)
        self.assertEqual(len(snapshots), 1)
        self.assertFalse(pickup.scan_active)

    def test_restart_resets_materials_and_snapshots(self) -> None:
        pickup = self.game.material_pickups[0]
        self.game.player.place_at_tile(pickup.tile)
        self.game.trigger_scan()
        self.game.update_gameplay(0.01, pygame.Vector2())
        self.assertTrue(self.game.snapshot_system.snapshots)
        old_pickups = list(self.game.material_pickups)
        self.game.restart_placeholder_run()
        self.assertEqual(self.game.placeholder_run.material_counts, {"scrap": 0, "circuit": 0, "power_cell": 0})
        self.assertEqual(self.game.snapshot_system.snapshots, [])
        self.assertTrue(all(pickup not in self.game.material_pickups for pickup in old_pickups))


if __name__ == "__main__":
    unittest.main()
