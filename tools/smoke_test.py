import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pygame

from game import settings
from game.app import Game
from game.states import GameState


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    game = Game()
    try:
        require(game.state == GameState.SPLASH, "Application did not start on splash.")

        frames = int(settings.SPLASH_DURATION * settings.FPS) + 5
        for _ in range(frames):
            game.run_one_frame(1.0 / settings.FPS)
        require(game.state == GameState.MAIN_MENU, "Splash did not transition to main menu.")

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        game.run_one_frame(1.0 / settings.FPS)
        require(game.state == GameState.PLAYING, "New Run did not enter PLAYING.")

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        game.run_one_frame(1.0 / settings.FPS)
        require(game.state == GameState.PAUSED, "Escape did not pause from PLAYING.")

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        game.run_one_frame(1.0 / settings.FPS)
        require(game.state == GameState.PLAYING, "Resume did not return to PLAYING.")

        game.transition_to(GameState.WORKSHOP)
        game.run_one_frame(1.0 / settings.FPS)
        game.activate_selected_button()
        require(game.state == GameState.FLOOR_TRANSITION, "Workshop continue did not enter transition.")

        game.request_quit()
        game.run_one_frame(1.0 / settings.FPS)
        require(not game.running, "Quit request did not stop the application loop.")
    finally:
        game.shutdown()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
