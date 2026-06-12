import math
import unittest

import numpy as np
import pygame

from game.systems.raycasting import cast_ray, cast_rays, has_line_of_sight
from game.world.blockers import DynamicBlockerRegistry
from game.world.tiles import TileType


class FakeFloor:
    def __init__(self, rows: list[list[TileType]]) -> None:
        self.tiles = np.array([[int(tile) for tile in row] for row in rows], dtype=np.int16)
        self.height, self.width = self.tiles.shape

    def tile_at(self, tile_x: int, tile_y: int) -> TileType:
        if not (0 <= tile_x < self.width and 0 <= tile_y < self.height):
            raise IndexError((tile_x, tile_y))
        return TileType(int(self.tiles[tile_y, tile_x]))


class FakeDoor:
    def __init__(self, tile: tuple[int, int], rect: pygame.Rect, *, blocked: bool = True) -> None:
        self.tile = tile
        self.collision_rect = rect
        self.door_id = f"door-{tile[0]}-{tile[1]}"
        self.unique_id = self.door_id
        self.orientation = "vertical_door_plane"
        self.door_type = type("DoorTypeValue", (), {"value": "powered"})()
        self.blocked = blocked

    def blocks_purpose(self, purpose: object) -> bool:
        return self.blocked


def bordered_floor(width: int = 7, height: int = 7) -> FakeFloor:
    rows = [[TileType.FLOOR for _ in range(width)] for _ in range(height)]
    for x in range(width):
        rows[0][x] = TileType.WALL
        rows[-1][x] = TileType.WALL
    for y in range(height):
        rows[y][0] = TileType.WALL
        rows[y][-1] = TileType.WALL
    return FakeFloor(rows)


class RaycastingTests(unittest.TestCase):
    TILE = 10

    def test_horizontal_positive_ray_hits_wall_boundary(self) -> None:
        floor = bordered_floor()
        hit = cast_ray((25, 35), 0.0, floor, None, self.TILE, 100)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.tile, (6, 3))
        self.assertAlmostEqual(hit.distance, 35.0)
        self.assertAlmostEqual(hit.world_position[0], 60.0)
        self.assertEqual(hit.side, "vertical")

    def test_horizontal_negative_ray_hits_wall(self) -> None:
        floor = bordered_floor()
        hit = cast_ray((25, 35), math.pi, floor, None, self.TILE, 100)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.tile, (0, 3))
        self.assertAlmostEqual(hit.distance, 15.0)

    def test_vertical_positive_and_negative_rays(self) -> None:
        floor = bordered_floor()
        down = cast_ray((25, 35), math.pi / 2, floor, None, self.TILE, 100)
        up = cast_ray((25, 35), -math.pi / 2, floor, None, self.TILE, 100)
        self.assertEqual(down.tile, (2, 6))
        self.assertEqual(up.tile, (2, 0))
        self.assertAlmostEqual(down.distance, 25.0)
        self.assertAlmostEqual(up.distance, 25.0)

    def test_first_wall_hides_second_wall(self) -> None:
        floor = bordered_floor(9, 5)
        floor.tiles[2, 4] = int(TileType.WALL)
        floor.tiles[2, 6] = int(TileType.DAMAGED_WALL)
        hit = cast_ray((25, 25), 0.0, floor, None, self.TILE, 100)
        self.assertEqual(hit.tile, (4, 2))
        self.assertEqual(hit.category, "wall")

    def test_obstacle_and_pillar_block(self) -> None:
        for tile_type, expected in ((TileType.OBSTACLE, "obstacle"), (TileType.PILLAR, "pillar")):
            with self.subTest(tile_type=tile_type):
                floor = bordered_floor()
                floor.tiles[3, 4] = int(tile_type)
                hit = cast_ray((25, 35), 0.0, floor, None, self.TILE, 100)
                self.assertEqual(hit.tile, (4, 3))
                self.assertEqual(hit.category, expected)

    def test_max_radius_can_end_before_wall(self) -> None:
        floor = bordered_floor()
        self.assertIsNone(cast_ray((25, 35), 0.0, floor, None, self.TILE, 20))

    def test_void_boundary_stops_safely(self) -> None:
        floor = FakeFloor([[TileType.FLOOR] * 3 for _ in range(3)])
        hit = cast_ray((15, 15), 0.0, floor, None, self.TILE, 100)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.category, "void_boundary")
        self.assertEqual(hit.tile, (3, 1))

    def test_closed_dynamic_door_blocks_and_records_id(self) -> None:
        floor = bordered_floor()
        door = FakeDoor((3, 3), pygame.Rect(34, 30, 2, 10), blocked=True)
        registry = DynamicBlockerRegistry([door], self.TILE)
        hit = cast_ray((15, 35), 0.0, floor, registry, self.TILE, 100)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.blocker_id, door.door_id)
        self.assertEqual(hit.category, "powered_door")
        self.assertAlmostEqual(hit.distance, 19.0)

    def test_open_dynamic_door_allows_ray_through(self) -> None:
        floor = bordered_floor()
        door = FakeDoor((3, 3), pygame.Rect(34, 30, 2, 10), blocked=False)
        registry = DynamicBlockerRegistry([door], self.TILE)
        hit = cast_ray((15, 35), 0.0, floor, registry, self.TILE, 100)
        self.assertEqual(hit.tile, (6, 3))
        self.assertIsNone(hit.blocker_id)

    def test_exact_diagonal_corner_is_conservatively_blocked(self) -> None:
        rows = [[TileType.FLOOR for _ in range(5)] for _ in range(5)]
        rows[1][2] = TileType.WALL
        rows[2][1] = TileType.WALL
        floor = FakeFloor(rows)
        hit = cast_ray((15, 15), math.pi / 4, floor, None, self.TILE, 100)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.side, "corner")
        self.assertAlmostEqual(hit.distance, math.sqrt(50), places=5)
        self.assertFalse(has_line_of_sight((15, 15), (35, 35), floor, None, self.TILE))

    def test_clear_line_of_sight_and_target_before_wall(self) -> None:
        floor = bordered_floor()
        self.assertTrue(has_line_of_sight((15, 35), (45, 35), floor, None, self.TILE))
        self.assertFalse(has_line_of_sight((15, 35), (65, 35), floor, None, self.TILE))

    def test_line_of_sight_respects_door_state(self) -> None:
        floor = bordered_floor()
        door = FakeDoor((3, 3), pygame.Rect(34, 30, 2, 10), blocked=True)
        registry = DynamicBlockerRegistry([door], self.TILE)
        self.assertFalse(has_line_of_sight((15, 35), (45, 35), floor, registry, self.TILE))
        door.blocked = False
        self.assertTrue(has_line_of_sight((15, 35), (45, 35), floor, registry, self.TILE))

    def test_same_point_and_out_of_bounds_line_of_sight(self) -> None:
        floor = bordered_floor()
        self.assertTrue(has_line_of_sight((25, 25), (25, 25), floor, None, self.TILE))
        self.assertFalse(has_line_of_sight((25, 25), (-5, 25), floor, None, self.TILE))

    def test_full_cast_is_deterministic(self) -> None:
        floor = bordered_floor()
        first = cast_rays((25, 35), floor, None, self.TILE, 100, 32, scan_id=3)
        second = cast_rays((25, 35), floor, None, self.TILE, 100, 32, scan_id=3)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 32)

    def test_door_state_is_snapshotted_when_rays_are_cast(self) -> None:
        floor = bordered_floor()
        door = FakeDoor((3, 3), pygame.Rect(34, 30, 2, 10), blocked=True)
        registry = DynamicBlockerRegistry([door], self.TILE)
        closed_hits = cast_rays((15, 35), floor, registry, self.TILE, 100, 16, scan_id=8)
        closed_door_hits = [hit for hit in closed_hits if hit.blocker_id == door.door_id]
        self.assertTrue(closed_door_hits)

        door.blocked = False
        # Already calculated hits remain historical data for the original scan.
        self.assertTrue([hit for hit in closed_hits if hit.blocker_id == door.door_id])
        open_hits = cast_rays((15, 35), floor, registry, self.TILE, 100, 16, scan_id=9)
        self.assertFalse([hit for hit in open_hits if hit.blocker_id == door.door_id])


if __name__ == "__main__":
    unittest.main()
