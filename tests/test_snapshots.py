import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame

from game.systems.scan import ScanWaveStep
from game.systems.snapshots import EchoSnapshot, EchoSnapshotSystem
from game.world.tiles import TileType


class FakeFloor:
    def __init__(self, width: int = 7, height: int = 7) -> None:
        self.width = width
        self.height = height
        self.tiles = np.full((height, width), int(TileType.FLOOR), dtype=np.int16)
        self.tiles[0, :] = int(TileType.WALL)
        self.tiles[-1, :] = int(TileType.WALL)
        self.tiles[:, 0] = int(TileType.WALL)
        self.tiles[:, -1] = int(TileType.WALL)

    def tile_at(self, tile_x: int, tile_y: int) -> TileType:
        return TileType(int(self.tiles[tile_y, tile_x]))


class FakeEntity:
    def __init__(self, entity_id: str, position: tuple[float, float], color=(72, 226, 255, 255)) -> None:
        self.unique_id = entity_id
        self.scan_category = "test_object"
        self.scan_active = True
        self.world_position = pygame.Vector2(position)
        self.frame = pygame.Surface((12, 12), pygame.SRCALPHA)
        self.frame.fill(color)

    @property
    def scan_position(self) -> pygame.Vector2:
        return self.world_position

    def capture_scan_outline(self) -> pygame.Surface:
        return self.frame


def step(scan_id: int, previous: float, current: float, origin=(15.0, 25.0)) -> ScanWaveStep:
    return ScanWaveStep(
        scan_id=scan_id,
        origin=pygame.Vector2(origin),
        previous_radius=previous,
        current_radius=current,
        max_radius=100.0,
    )


class EchoSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        pygame.init()
        if pygame.display.get_surface() is None:
            pygame.display.set_mode((64, 64))
        self.floor = FakeFloor()
        self.system = EchoSnapshotSystem(default_lifetime=2.0)

    def tearDown(self) -> None:
        pygame.quit()

    def test_visible_entity_creates_snapshot_when_front_crosses(self) -> None:
        entity = FakeEntity("visible", (35, 25))
        self.system.update(0.1, step(1, 0, 25), [entity], self.floor, None, 10)
        self.assertEqual(len(self.system.snapshots), 1)
        self.assertEqual(self.system.snapshots[0].source_id, "visible")

    def test_entity_behind_wall_creates_no_snapshot(self) -> None:
        self.floor.tiles[2, 2] = int(TileType.WALL)
        entity = FakeEntity("blocked", (35, 25))
        self.system.update(0.1, step(1, 0, 25), [entity], self.floor, None, 10)
        self.assertEqual(self.system.snapshots, [])
        self.assertEqual(self.system.diagnostics.blocked_entities, 1)

    def test_same_scan_evaluates_entity_once(self) -> None:
        entity = FakeEntity("once", (35, 25))
        self.system.update(0.1, step(1, 0, 25), [entity], self.floor, None, 10)
        self.system.update(0.1, step(1, 25, 40), [entity], self.floor, None, 10)
        self.assertEqual(len(self.system.snapshots_for_source("once")), 1)

    def test_later_scan_can_create_new_snapshot(self) -> None:
        entity = FakeEntity("repeat", (35, 25))
        self.system.update(0.1, step(1, 0, 25), [entity], self.floor, None, 10)
        entity.world_position.update(45, 25)
        self.system.update(0.1, step(2, 0, 35), [entity], self.floor, None, 10)
        snapshots = self.system.snapshots_for_source("repeat")
        self.assertEqual(len(snapshots), 2)
        self.assertNotEqual(snapshots[0].world_position, snapshots[1].world_position)

    def test_snapshot_stays_at_capture_position(self) -> None:
        entity = FakeEntity("fixed", (35, 25))
        self.system.update(0.1, step(1, 0, 25), [entity], self.floor, None, 10)
        snapshot_position = self.system.snapshots[0].world_position.copy()
        entity.world_position.update(50, 25)
        self.system.update(0.1, None, [entity], self.floor, None, 10)
        self.assertEqual(self.system.snapshots[0].world_position, snapshot_position)

    def test_snapshot_captures_frame_copy(self) -> None:
        entity = FakeEntity("frame", (35, 25), color=(10, 20, 30, 255))
        snapshot = EchoSnapshot.capture(entity, 1, 2.0)
        entity.frame.fill((200, 10, 10, 255))
        self.assertEqual(snapshot.image.get_at((2, 2))[:3], (10, 20, 30))

    def test_snapshot_fades_and_expires(self) -> None:
        entity = FakeEntity("fade", (35, 25))
        self.system.update(0.1, step(1, 0, 25), [entity], self.floor, None, 10)
        initial_alpha = self.system.snapshots[0].alpha
        self.system.update(1.0, None, [], self.floor, None, 10)
        self.assertLess(self.system.snapshots[0].alpha, initial_alpha)
        self.system.update(1.1, None, [], self.floor, None, 10)
        self.assertEqual(self.system.snapshots, [])

    def test_inactive_entity_is_ignored(self) -> None:
        entity = FakeEntity("inactive", (35, 25))
        entity.scan_active = False
        self.system.update(0.1, step(1, 0, 25), [entity], self.floor, None, 10)
        self.assertEqual(self.system.snapshots, [])

    def test_moving_entity_is_captured_when_front_overtakes_current_position(self) -> None:
        entity = FakeEntity("moving", (45, 25))
        self.system.update(0.1, step(1, 0, 10), [entity], self.floor, None, 10)
        entity.world_position.update(30, 25)
        self.system.update(0.1, step(1, 10, 20), [entity], self.floor, None, 10)
        self.assertEqual(len(self.system.snapshots), 1)
        self.assertEqual(self.system.snapshots[0].world_position, pygame.Vector2(30, 25))

    def test_reset_clears_snapshots_and_tracking(self) -> None:
        entity = FakeEntity("reset", (35, 25))
        self.system.update(0.1, step(1, 0, 25), [entity], self.floor, None, 10)
        self.system.reset()
        self.assertEqual(self.system.snapshots, [])
        self.assertEqual(self.system.diagnostics.active_snapshots, 0)


if __name__ == "__main__":
    unittest.main()
