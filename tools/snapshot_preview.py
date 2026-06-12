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
from game.systems.raycasting import has_line_of_sight


def save_frame(game: Game, path: Path) -> None:
    game.render()
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(game.screen, str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview scan-detectable objects and fading echo snapshots.")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--floor", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    game = Game()
    try:
        game.placeholder_run = PlaceholderRun(seed=args.seed, floor=args.floor)
        game.run_exists = True
        game.prepare_generated_floor()
        game.state = GameState.PLAYING
        if not game.material_pickups or game.player is None or game.camera is None:
            raise RuntimeError("Generated floor did not create material content.")

        pickup = game.material_pickups[0]
        floor = game.placeholder_run.generated_floor
        scan_tile = None
        for distance in (2, 1, 3, 4):
            for dx, dy in ((distance, 0), (-distance, 0), (0, distance), (0, -distance)):
                candidate = (pickup.tile[0] + dx, pickup.tile[1] + dy)
                if not floor.is_walkable(*candidate):
                    continue
                candidate_world = pygame.Vector2(
                    (candidate[0] + 0.5) * settings.TILE_SIZE,
                    (candidate[1] + 0.5) * settings.TILE_SIZE,
                )
                if has_line_of_sight(
                    candidate_world, pickup.world_position, floor, game.dynamic_blockers, settings.TILE_SIZE
                ):
                    scan_tile = candidate
                    break
            if scan_tile is not None:
                break
        if scan_tile is None:
            raise RuntimeError("Could not find a clear scan position near material.")

        game.player.place_at_tile(scan_tile)
        game.camera.update(game.player.world_position)
        if not game.trigger_scan():
            raise RuntimeError("Could not trigger scan.")
        for _ in range(90):
            game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
            if game.snapshot_system.snapshots_for_source(pickup.unique_id):
                break
        if not game.snapshot_system.snapshots_for_source(pickup.unique_id):
            raise RuntimeError("Material echo snapshot was not created.")

        artifact_dir = ROOT / "artifacts"
        detected = artifact_dir / f"snapshot_preview_{args.seed}_floor{args.floor}_detected.png"
        collected = artifact_dir / f"snapshot_preview_{args.seed}_floor{args.floor}_collected.png"
        fading = artifact_dir / f"snapshot_preview_{args.seed}_floor{args.floor}_fading.png"
        expired = artifact_dir / f"snapshot_preview_{args.seed}_floor{args.floor}_expired.png"
        save_frame(game, detected)

        game.player.place_at_tile(pickup.tile)
        game.camera.update(game.player.world_position)
        game.update_gameplay(0.0, pygame.Vector2())
        save_frame(game, collected)

        game.update_gameplay(settings.OBJECT_SNAPSHOT_LIFETIME * 0.45, pygame.Vector2())
        save_frame(game, fading)
        game.update_gameplay(settings.OBJECT_SNAPSHOT_LIFETIME * 0.65, pygame.Vector2())
        save_frame(game, expired)

        print(f"detected_preview: {detected}")
        print(f"collected_preview: {collected}")
        print(f"fading_preview: {fading}")
        print(f"expired_preview: {expired}")
        print(f"pickup: {pickup.unique_id}")
        print(f"material_counts: {game.placeholder_run.material_counts}")
        print(f"score: {game.placeholder_run.score}")
        print(f"active_snapshots: {len(game.snapshot_system.snapshots)}")

        if args.headless:
            return 0

        clock = pygame.time.Clock()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
                ):
                    running = False
            game.update_gameplay(clock.tick(settings.FPS) / 1000.0)
            game.render()
            pygame.display.flip()
        return 0
    finally:
        game.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
