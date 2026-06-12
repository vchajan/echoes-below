import os
import unittest

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.assets import AssetManager
from game.camera import Camera
from game.world.rendering import (
    StaticWorldRenderer,
    apply_darkness,
    build_local_glow_surface,
    visible_tile_range,
)
from game.world.tiles import TileType


class RenderableFloor:
    def __init__(self, seed: int = 1, floor_number: int = 1, attempt_seed: int = 10) -> None:
        self.seed = seed
        self.floor_number = floor_number
        self.attempt_seed = attempt_seed
        self.width = 8
        self.height = 6
        self.tiles = np.full((self.height, self.width), int(TileType.FLOOR), dtype=np.int16)

    def tile_at(self, tile_x: int, tile_y: int) -> TileType:
        return TileType(int(self.tiles[tile_y, tile_x]))

    def world_size_pixels(self, tile_size: int) -> tuple[int, int]:
        return (self.width * tile_size, self.height * tile_size)


class WorldRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = AssetManager(audio_available=False)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_visible_tile_range_is_bounded(self) -> None:
        camera = Camera((96, 96), (480, 480))
        camera.update((240, 240))
        x_range, y_range = visible_tile_range(camera, settings.TILE_SIZE, 10, 10, margin=0)
        self.assertEqual(list(x_range), [4, 5])
        self.assertEqual(list(y_range), [4, 5])

    def test_offscreen_tiles_are_not_included_in_visible_range(self) -> None:
        camera = Camera((96, 96), (480, 480))
        camera.update((240, 240))
        x_range, y_range = visible_tile_range(camera, settings.TILE_SIZE, 10, 10, margin=0)
        self.assertNotIn(0, x_range)
        self.assertNotIn(0, y_range)

    def test_static_render_cache_is_reused(self) -> None:
        renderer = StaticWorldRenderer(self.assets, settings.TILE_SIZE)
        floor = RenderableFloor()
        first = renderer.build_for_floor(floor)
        second = renderer.build_for_floor(floor)
        self.assertIs(first, second)
        self.assertEqual(renderer.rebuild_count, 1)

    def test_static_render_cache_rebuilds_on_floor_change(self) -> None:
        renderer = StaticWorldRenderer(self.assets, settings.TILE_SIZE)
        first = renderer.build_for_floor(RenderableFloor(seed=1, floor_number=1, attempt_seed=10))
        second = renderer.build_for_floor(RenderableFloor(seed=1, floor_number=2, attempt_seed=20))
        self.assertIsNot(first, second)
        self.assertEqual(renderer.rebuild_count, 2)

    def test_darkness_layer_does_not_mutate_source_tile_surface(self) -> None:
        renderer = StaticWorldRenderer(self.assets, settings.TILE_SIZE)
        world_surface = renderer.build_for_floor(RenderableFloor())
        source_pixel = world_surface.get_at((12, 12))
        target = pygame.Surface(world_surface.get_size()).convert()
        target.blit(world_surface, (0, 0))
        darkness = pygame.Surface(world_surface.get_size(), pygame.SRCALPHA)
        glow = build_local_glow_surface(settings.LOCAL_VISIBILITY_RADIUS)

        apply_darkness(target, darkness, glow, (48, 48))

        self.assertEqual(world_surface.get_at((12, 12)), source_pixel)


if __name__ == "__main__":
    unittest.main()
