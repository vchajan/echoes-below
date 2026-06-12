import os
import unittest

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.assets import AssetManager
from game.entities.player import Player, movement_direction_from_bools
from game.world import collision
from game.world.tiles import TileType


class FakeFloor:
    def __init__(self, width: int = 10, height: int = 10, default: TileType = TileType.FLOOR) -> None:
        self.width = width
        self.height = height
        self.tiles = np.full((height, width), int(default), dtype=np.int16)

    def set_tile(self, tile: tuple[int, int], tile_type: TileType) -> None:
        self.tiles[tile[1], tile[0]] = int(tile_type)

    def tile_at(self, tile_x: int, tile_y: int) -> TileType:
        if not (0 <= tile_x < self.width and 0 <= tile_y < self.height):
            raise IndexError((tile_x, tile_y))
        return TileType(int(self.tiles[tile_y, tile_x]))

    def is_walkable(self, tile_x: int, tile_y: int) -> bool:
        return not collision.is_blocking_tile(self, tile_x, tile_y)


class PlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = AssetManager(audio_available=False)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def make_player(self, floor: FakeFloor | None = None, speed: float = 120.0) -> tuple[Player, FakeFloor]:
        floor = floor or FakeFloor()
        return Player((3, 3), self.assets, settings.TILE_SIZE, speed=speed), floor

    def test_player_moves_expected_distance_with_delta_time(self) -> None:
        player, floor = self.make_player(speed=120.0)
        start_x = player.world_position.x
        player.update(pygame.Vector2(1, 0), 1.0, floor)
        self.assertAlmostEqual(player.world_position.x, start_x + 120.0, delta=0.01)

    def test_30_fps_and_60_fps_simulations_match(self) -> None:
        player_30, floor = self.make_player(speed=120.0)
        player_60, _ = self.make_player(floor=FakeFloor(), speed=120.0)
        for _ in range(30):
            player_30.update(pygame.Vector2(1, 0), 1.0 / 30.0, floor)
        for _ in range(60):
            player_60.update(pygame.Vector2(1, 0), 1.0 / 60.0, floor)
        self.assertAlmostEqual(player_30.world_position.x, player_60.world_position.x, delta=0.01)

    def test_diagonal_input_is_normalised(self) -> None:
        direction = movement_direction_from_bools(True, False, False, True)
        self.assertAlmostEqual(direction.length(), 1.0, delta=0.001)

    def test_opposite_input_cancels(self) -> None:
        direction = movement_direction_from_bools(True, True, True, True)
        self.assertEqual(direction, pygame.Vector2(0, 0))

    def test_facing_direction_is_stable_on_equal_diagonal(self) -> None:
        player, floor = self.make_player()
        player.update(pygame.Vector2(1, 0), 0.05, floor)
        player.update(pygame.Vector2(1, 1).normalize(), 0.05, floor)
        self.assertEqual(player.facing, "right")

    def test_idle_animation_is_used_when_movement_stops(self) -> None:
        player, floor = self.make_player()
        player.update(pygame.Vector2(0, -1), 0.05, floor)
        player.update(pygame.Vector2(0, 0), 0.05, floor)
        self.assertEqual(player.animation_key, "idle_up")

    def test_walking_animation_advances_with_delta_time(self) -> None:
        player, floor = self.make_player()
        player.update(pygame.Vector2(1, 0), 0.15, floor)
        self.assertEqual(player.animation_key, "walk_right")
        self.assertGreater(player.animations[player.animation_key].frame_index, 0)

    def assert_blocking_tile_stops_player(self, tile_type: TileType) -> None:
        floor = FakeFloor()
        floor.set_tile((4, 3), tile_type)
        player, _ = self.make_player(floor=floor, speed=180.0)
        player.update(pygame.Vector2(1, 0), 0.5, floor)
        blocker = collision.tile_to_world_rect(4, 3, settings.TILE_SIZE)
        self.assertLessEqual(player.collision_rect.right, blocker.left)

    def test_player_cannot_enter_wall(self) -> None:
        self.assert_blocking_tile_stops_player(TileType.WALL)

    def test_player_cannot_enter_damaged_wall(self) -> None:
        self.assert_blocking_tile_stops_player(TileType.DAMAGED_WALL)

    def test_player_cannot_enter_obstacle(self) -> None:
        self.assert_blocking_tile_stops_player(TileType.OBSTACLE)

    def test_player_cannot_enter_pillar(self) -> None:
        self.assert_blocking_tile_stops_player(TileType.PILLAR)

    def test_player_cannot_leave_map(self) -> None:
        floor = FakeFloor(width=5, height=5)
        player, _ = self.make_player(floor=floor, speed=180.0)
        player.place_at_tile((0, 2))
        player.update(pygame.Vector2(-1, 0), 0.5, floor)
        self.assertGreaterEqual(player.collision_rect.left, 0)

    def test_player_can_move_over_walkable_floor_variants(self) -> None:
        for tile_type in (TileType.FLOOR_ALT, TileType.DAMAGED_FLOOR, TileType.DOORWAY, TileType.ELEVATOR_FLOOR):
            with self.subTest(tile_type=tile_type):
                floor = FakeFloor()
                floor.set_tile((4, 3), tile_type)
                player, _ = self.make_player(floor=floor, speed=180.0)
                player.update(pygame.Vector2(1, 0), 0.35, floor)
                self.assertGreater(player.world_position.x, player.spawn_position.x + 40)

    def test_player_slides_along_wall_on_free_axis(self) -> None:
        floor = FakeFloor()
        for tile_y in range(3, 7):
            floor.set_tile((4, tile_y), TileType.WALL)
        player, _ = self.make_player(floor=floor, speed=180.0)
        start_y = player.world_position.y
        player.update(pygame.Vector2(1, 1).normalize(), 0.5, floor)
        blocker = collision.tile_to_world_rect(4, 3, settings.TILE_SIZE)
        self.assertLessEqual(player.collision_rect.right, blocker.left)
        self.assertGreater(player.world_position.y, start_y)

    def test_player_does_not_clip_diagonally_through_corner(self) -> None:
        floor = FakeFloor()
        floor.set_tile((4, 3), TileType.WALL)
        floor.set_tile((3, 4), TileType.WALL)
        player, _ = self.make_player(floor=floor, speed=240.0)
        player.update(pygame.Vector2(1, 1).normalize(), 0.5, floor)
        self.assertLess(player.collision_rect.right, collision.tile_to_world_rect(4, 3, settings.TILE_SIZE).right)
        self.assertLess(player.collision_rect.bottom, collision.tile_to_world_rect(3, 4, settings.TILE_SIZE).bottom)
        self.assertEqual(player.current_tile, (3, 3))

    def test_large_allowed_dt_does_not_tunnel_through_wall(self) -> None:
        floor = FakeFloor(width=12, height=8)
        floor.set_tile((5, 3), TileType.WALL)
        player, _ = self.make_player(floor=floor, speed=600.0)
        player.update(pygame.Vector2(1, 0), 0.25, floor)
        blocker = collision.tile_to_world_rect(5, 3, settings.TILE_SIZE)
        self.assertLessEqual(player.collision_rect.right, blocker.left)

    def test_collision_rect_stays_synchronised_with_world_position(self) -> None:
        player, floor = self.make_player()
        player.update(pygame.Vector2(0, 1), 0.2, floor)
        self.assertEqual(player.collision_rect.centerx, round(player.world_position.x))
        self.assertEqual(player.collision_rect.bottom, player.visual_rect.bottom - settings.PLAYER_COLLISION_BOTTOM_OFFSET)

    def test_visual_rect_stays_centred_on_world_position(self) -> None:
        player, floor = self.make_player()
        player.update(pygame.Vector2(-1, 0), 0.2, floor)
        self.assertEqual(player.visual_rect.center, (round(player.world_position.x), round(player.world_position.y)))


if __name__ == "__main__":
    unittest.main()
