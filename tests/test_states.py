import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.app import Game
from game.states import GameState


class GameStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game()

    def tearDown(self) -> None:
        self.game.shutdown()

    def test_initial_state_is_splash(self) -> None:
        self.assertEqual(self.game.state, GameState.SPLASH)

    def test_splash_transitions_after_timer(self) -> None:
        self.game.update(settings.SPLASH_DURATION + 0.01)
        self.assertEqual(self.game.state, GameState.MAIN_MENU)

    def test_splash_can_be_skipped(self) -> None:
        self.game.handle_keydown(pygame.K_SPACE)
        self.assertEqual(self.game.state, GameState.MAIN_MENU)

    def test_new_run_transitions_from_menu_to_playing(self) -> None:
        self.game.transition_to(GameState.MAIN_MENU)
        self.game.activate_selected_button()
        self.assertEqual(self.game.state, GameState.PLAYING)
        self.assertTrue(self.game.run_exists)

    def test_escape_transitions_from_playing_to_paused(self) -> None:
        self.game.start_new_run()
        self.game.handle_keydown(pygame.K_ESCAPE)
        self.assertEqual(self.game.state, GameState.PAUSED)

    def test_resume_transitions_from_paused_to_playing(self) -> None:
        self.game.start_new_run()
        self.game.transition_to(GameState.PAUSED)
        self.game.activate_selected_button()
        self.assertEqual(self.game.state, GameState.PLAYING)

    def test_main_menu_from_pause_transitions_correctly(self) -> None:
        self.game.start_new_run()
        self.game.transition_to(GameState.PAUSED)
        self.game.selected_indices[GameState.PAUSED] = 2
        self.game.activate_selected_button()
        self.assertEqual(self.game.state, GameState.MAIN_MENU)
        self.assertFalse(self.game.run_exists)

    def test_how_to_play_opens_and_returns(self) -> None:
        self.game.transition_to(GameState.MAIN_MENU)
        self.game.selected_indices[GameState.MAIN_MENU] = 1
        self.game.activate_selected_button()
        self.assertEqual(self.game.state, GameState.HOW_TO_PLAY)
        self.game.handle_keydown(pygame.K_BACKSPACE)
        self.assertEqual(self.game.state, GameState.MAIN_MENU)

    def test_restart_placeholder_resets_run(self) -> None:
        self.game.start_new_run()
        assert self.game.placeholder_run is not None
        original_seed = self.game.placeholder_run.seed
        self.game.placeholder_run.elapsed_time = 12.0
        self.game.placeholder_run.score = 99
        self.game.placeholder_run.floor = 2

        self.game.transition_to(GameState.PAUSED)
        self.game.selected_indices[GameState.PAUSED] = 1
        self.game.activate_selected_button()

        assert self.game.placeholder_run is not None
        self.assertEqual(self.game.state, GameState.PLAYING)
        self.assertEqual(self.game.placeholder_run.seed, original_seed)
        self.assertEqual(self.game.placeholder_run.elapsed_time, 0.0)
        self.assertEqual(self.game.placeholder_run.score, 0)
        self.assertEqual(self.game.placeholder_run.floor, 1)
        self.assertEqual(self.game.placeholder_run.restart_count, 1)

    def test_quit_request_stops_application_loop(self) -> None:
        self.game.transition_to(GameState.MAIN_MENU)
        self.game.selected_indices[GameState.MAIN_MENU] = 2
        self.game.activate_selected_button()
        self.assertFalse(self.game.running)

    def test_gameplay_timers_do_not_advance_while_paused(self) -> None:
        self.game.start_new_run()
        self.game.update(1.0)
        assert self.game.placeholder_run is not None
        running_time = self.game.placeholder_run.elapsed_time

        self.game.transition_to(GameState.PAUSED)
        self.game.update(5.0)
        self.assertEqual(self.game.placeholder_run.elapsed_time, running_time)


if __name__ == "__main__":
    unittest.main()
