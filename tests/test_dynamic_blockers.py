import os
import unittest

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.assets import AssetManager
from game.entities.door import DoorType, DynamicDoor
from game.entities.player import Player
from game.world import collision
from game.world.blockers import BlockerPurpose, DynamicBlockerRegistry
from game.world.floor import DoorwayCandidate
from game.world.navigation import doorway_passable_for_creature
from game.world.tiles import TileType


class FakeFloor:
    def __init__(self, width: int = 10, height: int = 8) -> None:
        self.width = width
        self.height = height
        self.tiles = np.full((height, width), int(TileType.FLOOR), dtype=np.int16)

    def set_tile(self, tile: tuple[int, int], tile_type: TileType) -> None:
        self.tiles[tile[1], tile[0]] = int(tile_type)

    def tile_at(self, tile_x: int, tile_y: int) -> TileType:
        if not (0 <= tile_x < self.width and 0 <= tile_y < self.height):
            raise IndexError((tile_x, tile_y))
        return TileType(int(self.tiles[tile_y, tile_x]))


class DynamicBlockerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = AssetManager(audio_available=False)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def make_door(
        self,
        tile: tuple[int, int] = (4, 3),
        door_type: DoorType = DoorType.POWERED,
    ) -> DynamicDoor:
        doorway = DoorwayCandidate(tile=tile, room_id=0, connected_room_id=1, orientation="vertical_door_plane")
        return DynamicDoor(f"door-{tile[0]}-{tile[1]}", door_type, doorway, self.assets, settings.TILE_SIZE)

    def test_movement_query_returns_correct_state(self) -> None:
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        self.assertEqual(registry.query_rect(door.collision_rect, BlockerPurpose.MOVEMENT), [door])

    def test_scan_query_returns_correct_state(self) -> None:
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        self.assertEqual(registry.query_rect(door.collision_rect, BlockerPurpose.SCAN), [door])

    def test_line_of_sight_query_returns_correct_state(self) -> None:
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        self.assertTrue(registry.blocks_tile(4, 3, BlockerPurpose.LINE_OF_SIGHT))

    def test_creature_navigation_query_returns_correct_state(self) -> None:
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        self.assertFalse(doorway_passable_for_creature(registry, door.tile))
        door.force_open()
        self.assertTrue(doorway_passable_for_creature(registry, door.tile))

    def test_dynamic_passability_changes_when_door_opens(self) -> None:
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        self.assertTrue(registry.blocks_tile(4, 3, BlockerPurpose.MOVEMENT))
        door.force_open()
        self.assertFalse(registry.blocks_tile(4, 3, BlockerPurpose.MOVEMENT))

    def test_nearby_dynamic_blocker_lookup_works(self) -> None:
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        self.assertIn(door, registry.blockers_near_tile(4, 3))

    def test_unrelated_distant_door_is_not_returned_as_overlapping(self) -> None:
        near = self.make_door((4, 3))
        far = self.make_door((8, 6))
        registry = DynamicBlockerRegistry([near, far], settings.TILE_SIZE)
        self.assertEqual(registry.query_rect(near.collision_rect, BlockerPurpose.MOVEMENT), [near])

    def test_tile_transition_reports_closed_door(self) -> None:
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        self.assertTrue(registry.blocks_tile_transition((3, 3), (4, 3), BlockerPurpose.MOVEMENT))

    def test_segment_tile_query_reports_closed_door(self) -> None:
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        self.assertTrue(registry.blocks_segment_tiles([(2, 3), (3, 3), (4, 3)], BlockerPurpose.SCAN))

    def test_player_cannot_pass_closed_door(self) -> None:
        floor = FakeFloor()
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        player = Player((3, 3), self.assets, settings.TILE_SIZE, speed=180.0)

        player.update(pygame.Vector2(1, 0), 0.6, floor, registry)

        self.assertLessEqual(player.collision_rect.right, door.collision_rect.left)

    def test_player_can_pass_open_door(self) -> None:
        floor = FakeFloor()
        door = self.make_door()
        door.force_open()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        player = Player((3, 3), self.assets, settings.TILE_SIZE, speed=180.0)

        player.update(pygame.Vector2(1, 0), 0.6, floor, registry)

        self.assertGreater(player.collision_rect.left, door.collision_rect.right)

    def test_diagonal_movement_cannot_clip_around_door_edge(self) -> None:
        floor = FakeFloor()
        floor.set_tile((4, 2), TileType.WALL)
        floor.set_tile((4, 4), TileType.WALL)
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        player = Player((3, 3), self.assets, settings.TILE_SIZE, speed=240.0)

        player.update(pygame.Vector2(1, 1).normalize(), 0.5, floor, registry)

        self.assertLessEqual(player.collision_rect.right, door.collision_rect.left)

    def test_door_collision_does_not_modify_static_tile_grid(self) -> None:
        floor = FakeFloor()
        before = floor.tiles.copy()
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        player = Player((3, 3), self.assets, settings.TILE_SIZE, speed=180.0)

        player.update(pygame.Vector2(1, 0), 0.6, floor, registry)

        self.assertTrue(np.array_equal(floor.tiles, before))

    def test_open_door_is_absent_from_all_blocking_purposes(self) -> None:
        door = self.make_door()
        door.force_open()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        for purpose in BlockerPurpose:
            with self.subTest(purpose=purpose):
                self.assertFalse(registry.blocks_tile(4, 3, purpose))

    def test_closed_door_is_present_for_all_blocking_purposes(self) -> None:
        door = self.make_door()
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        for purpose in BlockerPurpose:
            with self.subTest(purpose=purpose):
                self.assertTrue(registry.blocks_tile(4, 3, purpose))

    def test_static_and_dynamic_blockers_are_combined(self) -> None:
        floor = FakeFloor()
        floor.set_tile((1, 1), TileType.WALL)
        door = self.make_door((4, 3))
        registry = DynamicBlockerRegistry([door], settings.TILE_SIZE)
        static_rect = collision.tile_to_world_rect(1, 1, settings.TILE_SIZE)

        blockers = collision.all_blocking_rects_for_rect(floor, static_rect, settings.TILE_SIZE, registry)

        self.assertIn(static_rect, blockers)


if __name__ == "__main__":
    unittest.main()
