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
from game.systems.creature_ai import CreatureState
from game.systems.raycasting import has_line_of_sight


def save_frame(game: Game, path: Path) -> None:
    game.render()
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(game.screen, str(path))


def build_game(seed: int, floor_number: int) -> Game:
    game = Game()
    game.placeholder_run = PlaceholderRun(seed=seed, floor=floor_number)
    game.run_exists = True
    game.prepare_generated_floor()
    game.state = GameState.PLAYING
    if not game.creatures or game.player is None or game.camera is None:
        game.shutdown()
        raise RuntimeError("Generated floor did not create a playable AI preview session.")
    return game


def world_for_tile(tile: tuple[int, int]) -> pygame.Vector2:
    return pygame.Vector2((tile[0] + 0.5) * settings.TILE_SIZE, (tile[1] + 0.5) * settings.TILE_SIZE)


def place_player_at(game: Game, tile: tuple[int, int]) -> None:
    if game.player is None or game.camera is None:
        raise RuntimeError("Player/camera missing.")
    game.player.place_at_tile(tile)
    game.camera.update(game.player.world_position)


def find_scan_tile_for_creature(game: Game, creature) -> tuple[int, int]:
    floor = game.placeholder_run.generated_floor
    assert floor is not None
    candidates: list[tuple[float, tuple[int, int]]] = []
    for tile in floor.walkable_tiles():
        if tile == creature.current_tile:
            continue
        origin = world_for_tile(tile)
        distance = origin.distance_to(creature.scan_position)
        if not (settings.TILE_SIZE * 1.5 <= distance <= settings.SCAN_MAX_RADIUS * 0.6):
            continue
        if has_line_of_sight(origin, creature.scan_position, floor, game.dynamic_blockers, settings.TILE_SIZE):
            candidates.append((distance, tile))
    if not candidates:
        raise RuntimeError("Could not find a scan tile with line of sight to the creature.")
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def find_visible_tile_for_creature(game: Game, creature) -> tuple[int, int]:
    floor = game.placeholder_run.generated_floor
    assert floor is not None
    candidates: list[tuple[float, tuple[int, int]]] = []
    for tile in floor.walkable_tiles():
        if tile == creature.current_tile:
            continue
        world = world_for_tile(tile)
        distance = world.distance_to(creature.world_position)
        if not (settings.TILE_SIZE * 2.0 <= distance <= settings.CREATURE_DETECTION_DISTANCE * 0.8):
            continue
        if has_line_of_sight(world, creature.world_position, floor, game.dynamic_blockers, settings.TILE_SIZE):
            candidates.append((distance, tile))
    if not candidates:
        raise RuntimeError("Could not find a direct visible tile for CHASE preview.")
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def find_hidden_tile_for_creature(game: Game, creature) -> tuple[int, int]:
    floor = game.placeholder_run.generated_floor
    assert floor is not None
    candidates: list[tuple[float, tuple[int, int]]] = []
    for tile in floor.walkable_tiles():
        world = world_for_tile(tile)
        distance = world.distance_to(creature.world_position)
        if distance > settings.CREATURE_DETECTION_DISTANCE + settings.TILE_SIZE:
            candidates.append((distance, tile))
    if not candidates:
        raise RuntimeError("Could not find a tile outside creature perception range.")
    candidates.sort(reverse=True)
    return candidates[0][1]


def update_until(game: Game, predicate, *, frames: int = 180) -> bool:
    for _ in range(frames):
        game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
        if predicate():
            return True
    return False


def wait_for_scan_ready(game: Game) -> None:
    while not game.scan_system.ready:
        game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())


def run_headless(game: Game, seed: int, floor_number: int) -> int:
    creature = game.creatures[0]
    ai = creature.ai
    if ai is None:
        raise RuntimeError("Creature AI is not attached.")

    artifact_dir = ROOT / "artifacts"
    prefix = f"ai_preview_{seed}_floor{floor_number}"
    patrol_path = artifact_dir / f"{prefix}_patrol.png"
    investigate_path = artifact_dir / f"{prefix}_investigate.png"
    search_path = artifact_dir / f"{prefix}_search.png"
    chase_path = artifact_dir / f"{prefix}_chase.png"
    stunned_path = artifact_dir / f"{prefix}_stunned.png"

    transitions = [ai.state.name]
    game.debug_world_view = True
    for _ in range(8):
        game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
    patrol_calls = ai.pathfinding_call_count
    for _ in range(6):
        game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
    astar_throttled = ai.pathfinding_call_count == patrol_calls
    save_frame(game, patrol_path)

    scan_tile = find_scan_tile_for_creature(game, creature)
    place_player_at(game, scan_tile)
    wait_for_scan_ready(game)
    if not game.trigger_scan():
        raise RuntimeError("Could not trigger AI preview scan.")
    threat_ids = [event.event_id for event in game.threat_events.active_events]
    place_player_at(game, find_hidden_tile_for_creature(game, creature))
    if not update_until(game, lambda: ai.state is CreatureState.INVESTIGATE, frames=120):
        raise RuntimeError("Creature did not enter INVESTIGATE after player scan.")
    transitions.append(ai.state.name)
    investigate_path_length = len(ai.current_path)
    save_frame(game, investigate_path)

    if ai.investigation_target_tile is None:
        raise RuntimeError("Investigate state did not store a target tile.")
    creature.place_at_tile(ai.investigation_target_tile)
    game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
    if ai.state is not CreatureState.SEARCH:
        raise RuntimeError("Creature did not enter SEARCH at the investigation point.")
    transitions.append(ai.state.name)
    search_path_length = len(ai.current_path)
    save_frame(game, search_path)

    visible_tile = find_visible_tile_for_creature(game, creature)
    place_player_at(game, visible_tile)
    if not update_until(game, lambda: ai.state is CreatureState.CHASE, frames=120):
        raise RuntimeError("Creature did not enter CHASE with direct LOS.")
    transitions.append(ai.state.name)
    chase_path_length = len(ai.current_path)
    last_known = ai.last_known_player_position.copy() if ai.last_known_player_position is not None else None
    save_frame(game, chase_path)

    ai.apply_stun(2.0)
    game.update_gameplay(0.0, pygame.Vector2())
    if ai.state is not CreatureState.STUNNED:
        raise RuntimeError("Direct stun API did not enter STUNNED.")
    transitions.append(ai.state.name)
    save_frame(game, stunned_path)

    pathfinding_calls = ai.pathfinding_call_count
    path_lengths = {
        "investigate": investigate_path_length,
        "search": search_path_length,
        "chase": chase_path_length,
    }
    reset_old_ai = ai
    game.retry_same_seed()
    reset_cleaned = (
        len(game.threat_events.active_events) == 0
        and game.creatures
        and game.creatures[0].ai is not reset_old_ai
        and game.creatures[0].ai.state is CreatureState.PATROL
        and game.creatures[0].ai.selected_threat_event_id is None
    )

    print(f"patrol_preview: {patrol_path}")
    print(f"investigate_preview: {investigate_path}")
    print(f"search_preview: {search_path}")
    print(f"chase_preview: {chase_path}")
    print(f"stunned_preview: {stunned_path}")
    print(f"state_transition_sequence: {' -> '.join(transitions)}")
    print(f"threat_event_ids: {threat_ids}")
    print(f"pathfinding_call_count: {pathfinding_calls}")
    print(f"path_lengths: {path_lengths}")
    if last_known is not None:
        print(f"last_known_player_position: ({last_known.x:.1f}, {last_known.y:.1f})")
    else:
        print("last_known_player_position: None")
    print(f"astar_throttled: {astar_throttled}")
    print(f"reset_cleaned_ai_state: {reset_cleaned}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview Phase 10 creature AI states and diagnostics.")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--floor", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    game = build_game(args.seed, args.floor)
    try:
        if args.headless:
            return run_headless(game, args.seed, args.floor)
        print("Controls: WASD/arrows move, Space scan, F2 AI debug, F3 diagnostics, Esc pause.")
        game.run()
        return 0
    finally:
        game.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
