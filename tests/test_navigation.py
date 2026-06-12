import unittest

import pygame

from game.world.blockers import BlockerPurpose, DynamicBlockerRegistry
from game.world import navigation
from game.world.tiles import TileType, is_walkable


TILE = 48


class GridFloor:
    def __init__(self, width: int = 9, height: int = 7) -> None:
        self.width = width
        self.height = height
        self._tiles = [[TileType.FLOOR for _ in range(width)] for _ in range(height)]
        for x in range(width):
            self._tiles[0][x] = TileType.WALL
            self._tiles[height - 1][x] = TileType.WALL
        for y in range(height):
            self._tiles[y][0] = TileType.WALL
            self._tiles[y][width - 1] = TileType.WALL

    def tile_at(self, x: int, y: int) -> TileType:
        return self._tiles[y][x]

    def is_walkable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and is_walkable(self._tiles[y][x])

    def walkable_tiles(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if self.is_walkable(x, y)
        ]

    def set_tile(self, tile: tuple[int, int], tile_type: TileType) -> None:
        self._tiles[tile[1]][tile[0]] = tile_type


class FakeDoor:
    def __init__(self, tile: tuple[int, int], *, blocked: bool) -> None:
        self.door_id = f"door-{tile[0]}-{tile[1]}"
        self.tile = tile
        self.blocked = blocked
        self.collision_rect = pygame.Rect(tile[0] * TILE, tile[1] * TILE, TILE, TILE)

    def blocks_purpose(self, _purpose) -> bool:
        return self.blocked


class NavigationTests(unittest.TestCase):
    def test_straight_corridor_returns_valid_path(self) -> None:
        floor = GridFloor()
        path = navigation.astar_path(floor, (1, 3), (6, 3))
        self.assertEqual(path[-1], (6, 3))
        self.assertTrue(navigation.is_path_valid(floor, path, start_tile=(1, 3)))

    def test_path_avoids_wall(self) -> None:
        floor = GridFloor()
        floor.set_tile((3, 3), TileType.WALL)
        path = navigation.astar_path(floor, (1, 3), (6, 3))
        self.assertNotIn((3, 3), path)
        self.assertTrue(path)

    def test_path_avoids_obstacle(self) -> None:
        floor = GridFloor()
        floor.set_tile((3, 3), TileType.OBSTACLE)
        path = navigation.astar_path(floor, (1, 3), (6, 3))
        self.assertNotIn((3, 3), path)

    def test_path_avoids_pillar(self) -> None:
        floor = GridFloor()
        floor.set_tile((3, 3), TileType.PILLAR)
        path = navigation.astar_path(floor, (1, 3), (6, 3))
        self.assertNotIn((3, 3), path)

    def test_closed_door_blocks_path(self) -> None:
        floor = GridFloor(width=7, height=5)
        for y in (1, 2, 3):
            floor.set_tile((3, y), TileType.WALL)
        floor.set_tile((3, 2), TileType.FLOOR)
        blockers = DynamicBlockerRegistry([FakeDoor((3, 2), blocked=True)], TILE)
        self.assertEqual(navigation.astar_path(floor, (1, 2), (5, 2), blockers), [])

    def test_open_door_allows_path(self) -> None:
        floor = GridFloor(width=7, height=5)
        for y in (1, 2, 3):
            floor.set_tile((3, y), TileType.WALL)
        floor.set_tile((3, 2), TileType.FLOOR)
        blockers = DynamicBlockerRegistry([FakeDoor((3, 2), blocked=False)], TILE)
        path = navigation.astar_path(floor, (1, 2), (5, 2), blockers)
        self.assertIn((3, 2), path)

    def test_locked_or_wedged_closed_door_blocks_path(self) -> None:
        floor = GridFloor(width=7, height=5)
        for y in (1, 2, 3):
            floor.set_tile((3, y), TileType.WALL)
        floor.set_tile((3, 2), TileType.FLOOR)
        for blocked in (True, True):
            blockers = DynamicBlockerRegistry([FakeDoor((3, 2), blocked=blocked)], TILE)
            self.assertEqual(navigation.astar_path(floor, (1, 2), (5, 2), blockers), [])

    def test_wedged_open_door_allows_path(self) -> None:
        floor = GridFloor(width=7, height=5)
        for y in (1, 2, 3):
            floor.set_tile((3, y), TileType.WALL)
        floor.set_tile((3, 2), TileType.FLOOR)
        blockers = DynamicBlockerRegistry([FakeDoor((3, 2), blocked=False)], TILE)
        self.assertTrue(navigation.astar_path(floor, (1, 2), (5, 2), blockers))

    def test_unreachable_target_returns_empty(self) -> None:
        floor = GridFloor()
        for tile in ((4, 2), (3, 3), (4, 4), (5, 3)):
            floor.set_tile(tile, TileType.WALL)
        self.assertEqual(navigation.astar_path(floor, (1, 3), (4, 3)), [])

    def test_out_of_bounds_target_is_safe(self) -> None:
        floor = GridFloor()
        self.assertEqual(navigation.astar_path(floor, (1, 1), (99, 99)), [])

    def test_start_equal_target_returns_empty_valid_path(self) -> None:
        floor = GridFloor()
        self.assertEqual(navigation.astar_path(floor, (2, 2), (2, 2)), [])

    def test_path_contains_only_walkable_tiles_and_no_duplicates(self) -> None:
        floor = GridFloor()
        path = navigation.astar_path(floor, (1, 1), (7, 5))
        for previous, current in zip(path, path[1:]):
            self.assertNotEqual(previous, current)
        self.assertTrue(navigation.is_path_valid(floor, path, start_tile=(1, 1)))

    def test_same_inputs_return_deterministic_path(self) -> None:
        floor = GridFloor()
        first = navigation.astar_path(floor, (1, 1), (7, 5))
        second = navigation.astar_path(floor, (1, 1), (7, 5))
        self.assertEqual(first, second)

    def test_existing_path_validity_detects_newly_closed_door(self) -> None:
        floor = GridFloor(width=7, height=5)
        blockers = DynamicBlockerRegistry([FakeDoor((3, 2), blocked=False)], TILE)
        path = navigation.astar_path(floor, (1, 2), (5, 2), blockers)
        self.assertTrue(navigation.is_path_valid(floor, path, blockers, start_tile=(1, 2)))
        blockers.doors[0].blocked = True
        self.assertFalse(navigation.is_path_valid(floor, path, blockers, start_tile=(1, 2)))

    def test_nearest_reachable_tile_falls_back_from_blocked_target(self) -> None:
        floor = GridFloor()
        floor.set_tile((4, 3), TileType.WALL)
        nearest = navigation.nearest_reachable_tile(floor, (1, 3), (4, 3), max_radius=2)
        self.assertIsNotNone(nearest)
        self.assertNotEqual(nearest, (4, 3))


if __name__ == "__main__":
    unittest.main()
