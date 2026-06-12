import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game.assets import AssetManager
from game.entities.creature import Creature
from game.world.blockers import DynamicBlockerRegistry
from game.world.tiles import TileType, is_walkable


TILE = 48


class GridFloor:
    def __init__(self, width=9, height=7):
        self.width = width
        self.height = height
        self._tiles = [[TileType.WALL for _ in range(width)] for _ in range(height)]
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                self._tiles[y][x] = TileType.FLOOR

    def tile_at(self, x, y):
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError
        return self._tiles[y][x]

    def is_walkable(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height and is_walkable(self._tiles[y][x])

    def walkable_tiles(self):
        return [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if self.is_walkable(x, y)
        ]

    def set_tile(self, tile, kind):
        self._tiles[tile[1]][tile[0]] = kind


class FakeDoor:
    def __init__(self, tile, *, open_state=False):
        self.door_id = f"door-{tile[0]}-{tile[1]}"
        self.tile = tile
        self.collision_rect = pygame.Rect(tile[0] * TILE, tile[1] * TILE, TILE, TILE)
        self.open_state = open_state

    def blocks_purpose(self, _purpose):
        return not self.open_state


class CreatureMovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = AssetManager(audio_available=False)

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def make_creature(self, tile=(2, 3), seed=7, speed=120.0):
        creature = Creature("test-creature", tile, self.assets, TILE, random.Random(seed), speed=speed)
        creature.movement_enabled = False
        return creature

    def test_same_rng_seed_produces_same_patrol_motion(self):
        floor = GridFloor()
        first = self.make_creature(seed=99)
        second = self.make_creature(seed=99)
        first.movement_enabled = second.movement_enabled = True
        for _ in range(90):
            first.update(1 / 60, floor)
            second.update(1 / 60, floor)
        self.assertAlmostEqual(first.world_position.x, second.world_position.x, places=5)
        self.assertAlmostEqual(first.world_position.y, second.world_position.y, places=5)
        self.assertEqual(first.current_waypoint, second.current_waypoint)

    def test_creature_moves_and_animation_advances(self):
        floor = GridFloor()
        creature = self.make_creature()
        creature.movement_enabled = True
        start = creature.world_position.copy()
        seen_frames = {creature.animation_frame_index}
        for _ in range(30):
            creature.update(1 / 60, floor)
            seen_frames.add(creature.animation_frame_index)
        self.assertGreater(creature.world_position.distance_to(start), 1.0)
        self.assertGreater(len(seen_frames), 1)

    def test_wall_blocks_creature(self):
        floor = GridFloor()
        floor.set_tile((3, 3), TileType.WALL)
        creature = self.make_creature((2, 3))
        creature.move_by((TILE * 2, 0), floor)
        self.assertLessEqual(creature.collision_rect.right, 3 * TILE)

    def test_obstacle_blocks_creature(self):
        floor = GridFloor()
        floor.set_tile((3, 3), TileType.OBSTACLE)
        creature = self.make_creature((2, 3))
        creature.move_by((TILE * 2, 0), floor)
        self.assertLessEqual(creature.collision_rect.right, 3 * TILE)

    def test_closed_door_blocks_creature(self):
        floor = GridFloor()
        door = FakeDoor((3, 3), open_state=False)
        blockers = DynamicBlockerRegistry([door], TILE)
        creature = self.make_creature((2, 3))
        creature.move_by((TILE * 2, 0), floor, blockers)
        self.assertLessEqual(creature.collision_rect.right, door.collision_rect.left)

    def test_open_door_allows_creature(self):
        floor = GridFloor()
        door = FakeDoor((3, 3), open_state=True)
        blockers = DynamicBlockerRegistry([door], TILE)
        creature = self.make_creature((2, 3))
        creature.move_by((TILE * 2, 0), floor, blockers)
        self.assertGreater(creature.world_position.x, door.collision_rect.right)

    def test_creature_cannot_leave_map(self):
        floor = GridFloor()
        creature = self.make_creature((1, 1))
        creature.move_by((-TILE * 4, -TILE * 4), floor)
        self.assertGreaterEqual(creature.collision_rect.left, TILE)
        self.assertGreaterEqual(creature.collision_rect.top, TILE)

    def test_place_at_tile_resets_path_and_rects(self):
        creature = self.make_creature()
        creature.current_waypoint = (6, 3)
        creature.current_path = [(3, 3), (4, 3)]
        creature.place_at_tile((5, 4))
        self.assertEqual(creature.current_tile, (5, 4))
        self.assertIsNone(creature.current_waypoint)
        self.assertEqual(creature.current_path, [])
        self.assertEqual(creature.collision_rect.center, (round(creature.world_position.x), round(creature.world_position.y)))


if __name__ == "__main__":
    unittest.main()
