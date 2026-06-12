import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game.assets import AssetManager
from game.entities.creature import Creature
from game.systems.scan import ScanWaveStep
from game.systems.snapshots import EchoSnapshotSystem, wave_intersects_moving_distance
from game.world.blockers import DynamicBlockerRegistry
from game.world.tiles import TileType, is_walkable


TILE = 48


class GridFloor:
    def __init__(self, width=10, height=8):
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


def center(tile):
    return pygame.Vector2((tile[0] + 0.5) * TILE, (tile[1] + 0.5) * TILE)


def step(scan_id, origin, previous_radius, current_radius):
    return ScanWaveStep(scan_id, pygame.Vector2(origin), previous_radius, current_radius, 900.0)


class CreatureSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = AssetManager(audio_available=False)

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def make_creature(self, tile=(6, 3)):
        creature = Creature("creature", tile, self.assets, TILE, random.Random(10))
        creature.movement_enabled = False
        return creature

    def update_at_crossing(self, system, creature, floor, blockers=None, scan_id=1, origin=None):
        origin = center((2, 3)) if origin is None else pygame.Vector2(origin)
        distance = creature.scan_position.distance_to(origin)
        system.update(0.0, step(scan_id, origin, 0.0, distance + 2.0), [creature], floor, blockers, TILE)

    def test_front_crossing_helper_handles_inward_and_outward_motion(self):
        self.assertTrue(wave_intersects_moving_distance(10, 15, 20, 5))
        self.assertTrue(wave_intersects_moving_distance(10, 15, 5, 20))
        self.assertFalse(wave_intersects_moving_distance(10, 15, 5, 8))
        self.assertFalse(wave_intersects_moving_distance(10, 15, 25, 30))

    def test_visible_creature_creates_snapshot(self):
        floor = GridFloor()
        creature = self.make_creature()
        system = EchoSnapshotSystem()
        self.update_at_crossing(system, creature, floor)
        self.assertEqual(len(system.snapshots_for_source(creature.unique_id)), 1)

    def test_wall_blocks_snapshot(self):
        floor = GridFloor()
        floor.set_tile((4, 3), TileType.WALL)
        creature = self.make_creature()
        system = EchoSnapshotSystem()
        self.update_at_crossing(system, creature, floor)
        self.assertEqual(system.snapshots, [])

    def test_corner_blocks_snapshot(self):
        floor = GridFloor()
        floor.set_tile((3, 2), TileType.WALL)
        floor.set_tile((2, 3), TileType.WALL)
        creature = self.make_creature((4, 4))
        origin = center((2, 2))
        system = EchoSnapshotSystem()
        self.update_at_crossing(system, creature, floor, origin=origin)
        self.assertEqual(system.snapshots, [])

    def test_closed_door_blocks_and_open_door_allows_snapshot(self):
        floor = GridFloor()
        creature = self.make_creature()
        origin = center((2, 3))

        closed = DynamicBlockerRegistry([FakeDoor((4, 3), open_state=False)], TILE)
        blocked_system = EchoSnapshotSystem()
        self.update_at_crossing(blocked_system, creature, floor, closed, origin=origin)
        self.assertEqual(blocked_system.snapshots, [])

        opened = DynamicBlockerRegistry([FakeDoor((4, 3), open_state=True)], TILE)
        visible_system = EchoSnapshotSystem()
        self.update_at_crossing(visible_system, creature, floor, opened, origin=origin)
        self.assertEqual(len(visible_system.snapshots), 1)

    def test_creature_moving_inward_across_front_is_detected(self):
        floor = GridFloor()
        creature = self.make_creature()
        origin = center((2, 3))
        system = EchoSnapshotSystem()
        system.update(0.0, step(1, origin, 0, 20), [creature], floor, None, TILE)
        creature.set_world_position(origin + pygame.Vector2(25, 0))
        system.update(0.0, step(1, origin, 20, 30), [creature], floor, None, TILE)
        self.assertEqual(len(system.snapshots), 1)

    def test_creature_moving_outward_across_front_is_detected(self):
        floor = GridFloor()
        creature = self.make_creature()
        origin = center((2, 3))
        creature.set_world_position(origin + pygame.Vector2(10, 0))
        system = EchoSnapshotSystem()
        system.update(0.0, step(1, origin, 20, 20), [creature], floor, None, TILE)
        creature.set_world_position(origin + pygame.Vector2(40, 0))
        system.update(0.0, step(1, origin, 20, 30), [creature], floor, None, TILE)
        self.assertEqual(len(system.snapshots), 1)

    def test_moving_behind_cover_before_arrival_is_not_detected(self):
        floor = GridFloor()
        floor.set_tile((4, 3), TileType.WALL)
        creature = self.make_creature((3, 3))
        origin = center((2, 3))
        system = EchoSnapshotSystem()
        system.update(0.0, step(1, origin, 0, 20), [creature], floor, None, TILE)
        creature.place_at_tile((6, 3))
        distance = creature.scan_position.distance_to(origin)
        system.update(0.0, step(1, origin, 20, distance + 2), [creature], floor, None, TILE)
        self.assertEqual(system.snapshots, [])

    def test_one_snapshot_per_scan_and_later_scan_can_capture_again(self):
        floor = GridFloor()
        creature = self.make_creature()
        origin = center((2, 3))
        system = EchoSnapshotSystem()
        self.update_at_crossing(system, creature, floor, scan_id=1, origin=origin)
        self.update_at_crossing(system, creature, floor, scan_id=1, origin=origin)
        self.assertEqual(len(system.snapshots), 1)
        self.update_at_crossing(system, creature, floor, scan_id=2, origin=origin)
        self.assertEqual(len(system.snapshots), 2)

    def test_snapshot_captures_facing_frame_and_stays_fixed(self):
        floor = GridFloor()
        creature = self.make_creature()
        creature.facing = "left"
        creature.animations["left"].frame_index = 2
        system = EchoSnapshotSystem()
        self.update_at_crossing(system, creature, floor)
        snapshot = system.snapshots[0]
        captured_position = snapshot.world_position.copy()
        self.assertEqual(snapshot.facing, "left")
        self.assertEqual(snapshot.image.get_size(), creature.capture_scan_outline().get_size())
        creature.place_at_tile((7, 5))
        self.assertEqual(snapshot.world_position, captured_position)

    def test_snapshot_fades_and_expires(self):
        floor = GridFloor()
        creature = self.make_creature()
        system = EchoSnapshotSystem()
        self.update_at_crossing(system, creature, floor)
        first_alpha = system.snapshots[0].alpha
        system.update(creature.snapshot_lifetime * 0.5, None, [], floor, None, TILE)
        self.assertLess(system.snapshots[0].alpha, first_alpha)
        system.update(creature.snapshot_lifetime, None, [], floor, None, TILE)
        self.assertEqual(system.snapshots, [])


if __name__ == "__main__":
    unittest.main()
