import unittest

import numpy as np
import pygame

from game import settings
from game.world import collision
from game.world.tiles import TileType


class FakeFloor:
    def __init__(self, rows: list[list[TileType]]) -> None:
        self.tiles = np.array([[int(tile) for tile in row] for row in rows], dtype=np.int16)
        self.height, self.width = self.tiles.shape

    def tile_at(self, tile_x: int, tile_y: int) -> TileType:
        if not (0 <= tile_x < self.width and 0 <= tile_y < self.height):
            raise IndexError((tile_x, tile_y))
        return TileType(int(self.tiles[tile_y, tile_x]))


class CollisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.floor = FakeFloor(
            [
                [TileType.WALL, TileType.WALL, TileType.WALL, TileType.WALL],
                [TileType.WALL, TileType.FLOOR, TileType.DOORWAY, TileType.WALL],
                [TileType.WALL, TileType.OBSTACLE, TileType.ELEVATOR_FLOOR, TileType.WALL],
                [TileType.WALL, TileType.WALL, TileType.WALL, TileType.WALL],
            ]
        )

    def test_world_coordinate_converts_to_tile(self) -> None:
        self.assertEqual(collision.world_to_tile((0, 0), settings.TILE_SIZE), (0, 0))
        self.assertEqual(collision.world_to_tile((47.9, 48), settings.TILE_SIZE), (0, 1))
        self.assertEqual(collision.world_to_tile(pygame.Vector2(96, 95), settings.TILE_SIZE), (2, 1))

    def test_tile_coordinate_converts_to_world_rect(self) -> None:
        rect = collision.tile_to_world_rect(2, 3, settings.TILE_SIZE)
        self.assertEqual(rect.topleft, (96, 144))
        self.assertEqual(rect.size, (48, 48))

    def test_negative_coordinates_are_out_of_bounds_and_blocking(self) -> None:
        self.assertFalse(collision.tile_in_bounds(self.floor, -1, 0))
        self.assertTrue(collision.is_blocking_tile(self.floor, -1, 0))
        self.assertTrue(collision.is_blocking_tile(self.floor, 0, -1))

    def test_beyond_map_coordinates_are_out_of_bounds_and_blocking(self) -> None:
        self.assertFalse(collision.tile_in_bounds(self.floor, self.floor.width, 1))
        self.assertTrue(collision.is_blocking_tile(self.floor, self.floor.width, 1))
        self.assertTrue(collision.is_blocking_tile(self.floor, 1, self.floor.height))

    def test_tiles_overlapping_rect_only_returns_nearby_tiles(self) -> None:
        rect = pygame.Rect(47, 47, 49, 49)
        self.assertEqual(
            collision.tiles_overlapping_rect(rect, settings.TILE_SIZE),
            [(0, 0), (1, 0), (0, 1), (1, 1)],
        )

    def test_blocking_rects_include_obstacles_and_walls_only(self) -> None:
        rect = pygame.Rect(48, 48, 96, 96)
        blockers = collision.blocking_rects_for_rect(self.floor, rect, settings.TILE_SIZE)
        self.assertEqual([blocker.topleft for blocker in blockers], [(48, 96)])

    def test_resolve_axis_stops_at_blocker_boundary(self) -> None:
        rect = pygame.Rect(72, 60, 24, 24)
        moved, collided = collision.resolve_axis(rect, 60, "x", self.floor, settings.TILE_SIZE)
        self.assertTrue(collided)
        self.assertEqual(moved.right, collision.tile_to_world_rect(3, 1, settings.TILE_SIZE).left)


if __name__ == "__main__":
    unittest.main()
