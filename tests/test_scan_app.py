import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.app import Game
from game.states import GameState


class ScanAppIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game()
        self.game.start_new_run()

    def tearDown(self) -> None:
        self.game.shutdown()

    def test_space_handler_triggers_scan(self) -> None:
        self.assertIsNone(self.game.scan_system.active_wave)
        self.game.handle_keydown(pygame.K_SPACE)
        self.assertIsNotNone(self.game.scan_system.active_wave)
        self.assertGreater(self.game.scan_system.diagnostics.raw_hit_count, 0)

    def test_pause_freezes_wave_and_cooldown(self) -> None:
        self.assertTrue(self.game.trigger_scan())
        self.game.update_gameplay(0.1, pygame.Vector2())
        wave = self.game.scan_system.active_wave
        self.assertIsNotNone(wave)
        radius = wave.current_radius
        cooldown = self.game.scan_system.cooldown_remaining
        self.game.transition_to(GameState.PAUSED)
        self.game.update(0.5)
        self.assertEqual(wave.current_radius, radius)
        self.assertEqual(self.game.scan_system.cooldown_remaining, cooldown)

    def test_restart_clears_scan_state(self) -> None:
        self.game.trigger_scan()
        self.game.update_gameplay(0.8, pygame.Vector2())
        self.assertTrue(self.game.scan_system.traces)
        self.game.restart_placeholder_run()
        self.assertIsNone(self.game.scan_system.active_wave)
        self.assertEqual(self.game.scan_system.traces, [])
        self.assertTrue(self.game.scan_system.ready)

    def test_f3_toggles_performance_overlay(self) -> None:
        self.assertFalse(self.game.performance_overlay)
        self.game.handle_keydown(pygame.K_F3)
        self.assertTrue(self.game.performance_overlay)
        self.game.handle_keydown(pygame.K_F3)
        self.assertFalse(self.game.performance_overlay)

    def test_scan_origin_is_world_space_and_does_not_follow_camera(self) -> None:
        self.game.trigger_scan()
        wave = self.game.scan_system.active_wave
        self.assertIsNotNone(wave)
        origin = wave.origin.copy()
        self.game.camera.offset += pygame.Vector2(settings.TILE_SIZE, 0)
        self.assertEqual(wave.origin, origin)


if __name__ == "__main__":
    unittest.main()
