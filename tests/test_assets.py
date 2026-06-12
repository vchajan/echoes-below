import contextlib
import io
import os
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game.animation import Animation
from game.assets import SPRITESHEETS, AssetManager


class AssetManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        self.assets = AssetManager(audio_available=False)

    def test_known_image_loads_successfully(self) -> None:
        image = self.assets.load_image("assets/tiles/industrial_tileset.png")
        self.assertGreater(image.get_width(), 0)
        self.assertGreater(image.get_height(), 0)

    def test_repeated_loading_returns_cached_source(self) -> None:
        first = self.assets.load_image("assets/tiles/industrial_tileset.png")
        second = self.assets.load_image("assets/tiles/industrial_tileset.png")
        self.assertIs(first, second)

    def test_missing_image_returns_fallback(self) -> None:
        image = self.assets.load_image("assets/missing/not_here.png", (32, 24))
        self.assertEqual(image.get_size(), (32, 24))
        self.assertNotEqual(image.get_at((0, 0)).a, 0)

    def test_missing_image_warning_is_not_repeated(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assets.load_image("assets/missing/repeated.png", (16, 16))
            self.assets.load_image("assets/missing/repeated.png", (16, 16))
        self.assertEqual(output.getvalue().count("Warning: missing asset"), 1)

    def test_spritesheet_slicing_returns_expected_frame_count(self) -> None:
        frames = self.assets.get_frames("player", "walk_down")
        self.assertEqual(len(frames), 5)

    def test_every_frame_has_expected_dimensions(self) -> None:
        for sheet_name, metadata in SPRITESHEETS.items():
            with self.subTest(sheet_name=sheet_name):
                for frame in self.assets.get_sheet_frames(sheet_name):
                    self.assertEqual(frame.get_size(), (metadata.frame_width, metadata.frame_height))

    def test_outline_contains_contour_pixels(self) -> None:
        outline = self.assets.get_outline_frames("player", "idle_down")[0]
        outline_mask = pygame.mask.from_surface(outline)
        self.assertGreater(outline_mask.count(), 0)

    def test_outline_does_not_fill_original_opaque_area(self) -> None:
        frame = self.assets.get_frames("player", "idle_down")[0]
        outline = self.assets.get_outline_frames("player", "idle_down")[0]
        source_mask = pygame.mask.from_surface(frame)
        outline_mask = pygame.mask.from_surface(outline)
        self.assertEqual(outline_mask.overlap_area(source_mask, (0, 0)), 0)

    def test_outline_result_is_cached(self) -> None:
        first = self.assets.get_outline_frames("creature", "move")[0]
        second = self.assets.get_outline_frames("creature", "move")[0]
        self.assertIs(first, second)

    def test_horizontally_flipped_frame_is_cached(self) -> None:
        first = self.assets.get_flipped_frames("creature", "move")[0]
        second = self.assets.get_flipped_frames("creature", "move")[0]
        self.assertIs(first, second)
        self.assertEqual(first.get_size(), (64, 64))

    def test_asset_paths_work_when_cwd_changes(self) -> None:
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                image = self.assets.load_image("assets/tiles/industrial_tileset.png")
                self.assertEqual(image.get_size(), (288, 96))
            finally:
                os.chdir(original_cwd)

    def test_missing_audio_does_not_crash(self) -> None:
        sound = self.assets.load_sound("menu_select")
        self.assertIsNone(sound.play())


class AnimationTests(unittest.TestCase):
    def make_frames(self, count: int) -> list[pygame.Surface]:
        return [pygame.Surface((8, 8), pygame.SRCALPHA) for _ in range(count)]

    def test_animation_advances_with_delta_time(self) -> None:
        animation = Animation(self.make_frames(3), frame_duration=0.2)
        animation.update(0.21)
        self.assertEqual(animation.frame_index, 1)

    def test_looping_animation_wraps(self) -> None:
        animation = Animation(self.make_frames(2), frame_duration=0.1, looping=True)
        animation.update(0.25)
        self.assertEqual(animation.frame_index, 0)
        self.assertFalse(animation.is_complete)

    def test_non_looping_animation_reports_completion(self) -> None:
        animation = Animation(self.make_frames(2), frame_duration=0.1, looping=False)
        animation.update(0.25)
        self.assertEqual(animation.frame_index, 1)
        self.assertTrue(animation.is_complete)


if __name__ == "__main__":
    unittest.main()
