from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

if "--headless" in sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game import settings
from game.app import Game
from game.states import GameState, PlaceholderRun


def build_game(seed: int, floor_number: int) -> Game:
    game = Game()
    game.placeholder_run = PlaceholderRun(seed=seed, floor=floor_number)
    game.run_exists = True
    game.prepare_generated_floor()
    game.transition_to(GameState.PLAYING)
    if game.placeholder_run.generated_floor is None or game.player is None or game.camera is None:
        raise RuntimeError(f"Could not prepare seed {seed}, floor {floor_number}: {game.generation_error}")
    return game


def save_frame(game: Game, path: Path) -> None:
    game.render_playing()
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(game.screen, path)


def run_headless(seed: int, floor_number: int) -> int:
    game = build_game(seed, floor_number)
    try:
        prefix = ROOT / "artifacts" / f"scan_preview_{seed}_floor{floor_number}"
        if not game.trigger_scan():
            raise RuntimeError("Initial scan did not trigger.")

        for _ in range(12):
            game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
        early = Path(f"{prefix}_early.png")
        save_frame(game, early)

        for _ in range(70):
            game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
        late = Path(f"{prefix}_late.png")
        save_frame(game, late)

        floor = game.placeholder_run.generated_floor
        target_room = floor.rooms[floor.candidate_objective_rooms[-1]]
        target_world = (
            (target_room.center[0] + 0.5) * settings.TILE_SIZE,
            (target_room.center[1] + 0.5) * settings.TILE_SIZE,
        )
        game.camera.update(target_world)
        shifted = Path(f"{prefix}_camera_shift.png")
        save_frame(game, shifted)

        diagnostics = game.scan_system.diagnostics
        print(f"early_preview: {early}")
        print(f"late_preview: {late}")
        print(f"camera_shift_preview: {shifted}")
        print(f"rays: {settings.SCAN_RAY_COUNT}")
        print(f"raw_hits: {diagnostics.raw_hit_count}")
        print(f"deduplicated_hits: {diagnostics.deduplicated_hit_count}")
        print(f"active_traces: {len(game.scan_system.traces)}")
        print(f"raycast_ms: {diagnostics.last_raycast_ms:.3f}")
        print(f"dynamic_doors: {diagnostics.last_dynamic_door_count}")
        return 0
    finally:
        game.shutdown()


def run_interactive(seed: int, floor_number: int) -> int:
    game = build_game(seed, floor_number)
    clock = pygame.time.Clock()
    try:
        running = True
        while running:
            dt = min(clock.tick(settings.FPS) / 1000.0, settings.MAX_DELTA_TIME)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                else:
                    game.handle_event(event)
            game.update(dt)
            game.render()
            pygame.display.flip()
        return 0
    finally:
        game.shutdown()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview fixed-origin scan raycasting and fading traces.")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--floor", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--headless", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.headless:
        return run_headless(args.seed, args.floor)
    return run_interactive(args.seed, args.floor)


if __name__ == "__main__":
    raise SystemExit(main())
