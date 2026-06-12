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
from game.world import collision


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def step_gameplay(game: Game, direction: pygame.Vector2, frames: int = 20) -> None:
    for _ in range(frames):
        game.update_gameplay(1.0 / settings.FPS, direction)


def movement_directions_from_spawn(game: Game) -> list[pygame.Vector2]:
    require(game.placeholder_run is not None, "Run was not created.")
    floor = game.placeholder_run.generated_floor
    require(floor is not None, "Floor was not generated.")
    require(game.player is not None, "Player was not created.")

    tile_x, tile_y = game.player.current_tile
    directions: list[pygame.Vector2] = []
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        if floor.is_walkable(tile_x + dx, tile_y + dy):
            directions.append(pygame.Vector2(dx, dy))
    return directions


def find_walkable_tile_next_to_blocker(game: Game) -> tuple[tuple[int, int], pygame.Vector2, pygame.Rect]:
    require(game.placeholder_run is not None, "Run was not created.")
    floor = game.placeholder_run.generated_floor
    require(floor is not None, "Floor was not generated.")

    for y in range(floor.height):
        for x in range(floor.width):
            if not floor.is_walkable(x, y):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                blocker_x = x + dx
                blocker_y = y + dy
                if collision.is_blocking_tile(floor, blocker_x, blocker_y):
                    return (
                        (x, y),
                        pygame.Vector2(dx, dy),
                        collision.tile_to_world_rect(blocker_x, blocker_y, settings.TILE_SIZE),
                    )
    raise AssertionError("Could not find a walkable tile next to a blocker.")


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
        require(game.placeholder_run is not None, "Run data was not created.")
        require(game.placeholder_run.generated_floor is not None, "Generated floor missing in PLAYING.")
        require(game.player is not None, "Player missing in PLAYING.")
        require(game.camera is not None, "Camera missing in PLAYING.")

        directions = movement_directions_from_spawn(game)
        require(len(directions) >= 2, "Spawn did not expose two test movement directions.")
        first_position = game.player.world_position.copy()
        step_gameplay(game, directions[0])
        require(
            game.player.world_position.distance_to(first_position) > 5,
            "Player did not move in the first simulated direction.",
        )
        second_position = game.player.world_position.copy()
        step_gameplay(game, directions[1])
        require(
            game.player.world_position.distance_to(second_position) > 5,
            "Player did not move in the second simulated direction.",
        )

        blocker_start, blocker_direction, blocker_rect = find_walkable_tile_next_to_blocker(game)
        game.player.place_at_tile(blocker_start)
        game.camera.update(game.player.world_position)
        step_gameplay(game, blocker_direction, frames=60)
        if blocker_direction.x > 0:
            require(game.player.collision_rect.right <= blocker_rect.left, "Player passed through a right-side blocker.")
        elif blocker_direction.x < 0:
            require(game.player.collision_rect.left >= blocker_rect.right, "Player passed through a left-side blocker.")
        elif blocker_direction.y > 0:
            require(game.player.collision_rect.bottom <= blocker_rect.top, "Player passed through a lower blocker.")
        elif blocker_direction.y < 0:
            require(game.player.collision_rect.top >= blocker_rect.bottom, "Player passed through an upper blocker.")

        game.handle_keydown(pygame.K_F2)
        require(game.debug_world_view, "F2 did not enable debug mode.")
        game.handle_keydown(pygame.K_F2)
        require(not game.debug_world_view, "F2 did not disable debug mode.")

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        game.run_one_frame(1.0 / settings.FPS)
        require(game.state == GameState.PAUSED, "Escape did not pause from PLAYING.")

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        game.run_one_frame(1.0 / settings.FPS)
        require(game.state == GameState.PLAYING, "Resume did not return to PLAYING.")

        old_player = game.player
        old_camera = game.camera
        game.transition_to(GameState.PAUSED)
        game.selected_indices[GameState.PAUSED] = 1
        game.activate_selected_button()
        require(game.state == GameState.PLAYING, "Restart Run did not return to PLAYING.")
        require(game.player is not None and game.player is not old_player, "Restart did not create a fresh player.")
        require(game.camera is not None and game.camera is not old_camera, "Restart did not create a fresh camera.")
        require(game.placeholder_run is not None and game.placeholder_run.restart_count == 1, "Restart count was not updated.")

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
