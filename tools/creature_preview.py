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


def find_scan_tile_for_creature(game: Game, creature) -> tuple[int, int]:
    floor = game.placeholder_run.generated_floor
    assert floor is not None
    candidates: list[tuple[float, tuple[int, int]]] = []
    for tile in floor.walkable_tiles():
        if tile == creature.current_tile:
            continue
        origin = pygame.Vector2(
            (tile[0] + 0.5) * settings.TILE_SIZE,
            (tile[1] + 0.5) * settings.TILE_SIZE,
        )
        distance = origin.distance_to(creature.scan_position)
        if not (settings.TILE_SIZE * 1.5 <= distance <= settings.SCAN_MAX_RADIUS * 0.65):
            continue
        if has_line_of_sight(
            origin,
            creature.scan_position,
            floor,
            game.dynamic_blockers,
            settings.TILE_SIZE,
        ):
            candidates.append((distance, tile))
    if not candidates:
        raise RuntimeError("Could not find a safe scan position with line of sight to the creature.")
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def move_creature_to_neighbour(game: Game, creature) -> tuple[int, int]:
    floor = game.placeholder_run.generated_floor
    assert floor is not None
    x, y = creature.current_tile
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        tile = (x + dx, y + dy)
        if floor.is_walkable(*tile) and not game.dynamic_blockers.blocks_tile(*tile, purpose="creature_movement"):
            creature.place_at_tile(tile)
            return tile
    raise RuntimeError("Could not move preview creature to a neighbouring tile.")


def build_game(seed: int, floor_number: int) -> Game:
    game = Game()
    game.placeholder_run = PlaceholderRun(seed=seed, floor=floor_number)
    game.run_exists = True
    game.prepare_generated_floor()
    game.state = GameState.PLAYING
    if not game.creatures or game.player is None or game.camera is None:
        game.shutdown()
        raise RuntimeError("Generated floor did not create the Phase 9 gameplay session.")
    return game


def run_headless(game: Game, seed: int, floor_number: int) -> int:
    creature = game.creatures[0]
    creature.movement_enabled = False
    scan_tile = find_scan_tile_for_creature(game, creature)
    game.player.place_at_tile(scan_tile)
    game.camera.update(game.player.world_position)

    artifact_dir = ROOT / "artifacts"
    prefix = f"creature_preview_{seed}_floor{floor_number}"
    debug_path = artifact_dir / f"{prefix}_debug.png"
    before_path = artifact_dir / f"{prefix}_before_scan.png"
    snapshot_path = artifact_dir / f"{prefix}_snapshot.png"
    moved_path = artifact_dir / f"{prefix}_moved.png"
    death_path = artifact_dir / f"{prefix}_death.png"

    game.debug_world_view = True
    save_frame(game, debug_path)
    game.debug_world_view = False
    save_frame(game, before_path)

    if not game.trigger_scan():
        raise RuntimeError("Could not trigger scan for creature preview.")
    scan_id = game.scan_system.active_wave.scan_id
    for _ in range(180):
        game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
        if game.snapshot_system.snapshots_for_source(creature.unique_id):
            break
    snapshots = game.snapshot_system.snapshots_for_source(creature.unique_id)
    if len(snapshots) != 1:
        raise RuntimeError(f"Expected exactly one creature snapshot, got {len(snapshots)}.")

    snapshot = snapshots[0]
    captured_position = snapshot.world_position.copy()
    save_frame(game, snapshot_path)

    moved_tile = move_creature_to_neighbour(game, creature)
    game.debug_world_view = True
    save_frame(game, moved_path)
    stationary = snapshot.world_position == captured_position

    game.debug_world_view = False
    game.player.world_position = creature.world_position.copy()
    game.player._sync_rects_from_world()
    game.camera.update(game.player.world_position)
    game.update_gameplay(0.0, pygame.Vector2())
    if game.state is not GameState.DEATH:
        raise RuntimeError("Forced contact did not enter DEATH state.")
    save_frame(game, death_path)

    print(f"debug_preview: {debug_path}")
    print(f"before_scan_preview: {before_path}")
    print(f"snapshot_preview: {snapshot_path}")
    print(f"moved_preview: {moved_path}")
    print(f"death_preview: {death_path}")
    print(f"creature_spawn: {creature.spawn_tile}")
    print(f"creature_moved_tile: {moved_tile}")
    print(f"snapshot_position: ({captured_position.x:.1f}, {captured_position.y:.1f})")
    print(f"creature_position: ({creature.world_position.x:.1f}, {creature.world_position.y:.1f})")
    print(f"scan_id: {scan_id}")
    print(f"snapshot_count: {len(snapshots)}")
    print(f"snapshot_stationary: {stationary}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview invisible moving creature scan snapshots.")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--floor", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    game = build_game(args.seed, args.floor)
    try:
        if args.headless:
            return run_headless(game, args.seed, args.floor)
        print("Controls: WASD/arrows move, Space scans, F2 debug, F3 diagnostics, Esc pauses.")
        game.run()
        return 0
    finally:
        game.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
