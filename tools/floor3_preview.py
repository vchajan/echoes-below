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
from game.systems.floor3_objectives import Floor3ObjectiveSystem
from game.systems.threat_events import ThreatSourceType


def save_frame(game: Game, path: Path) -> None:
    game.render()
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(game.screen, str(path))


def place_player_at(game: Game, tile: tuple[int, int]) -> None:
    if game.player is None or game.camera is None:
        raise RuntimeError("Player and camera must exist.")
    game.player.place_at_tile(tile)
    game.camera.update(game.player.world_position)


def update(game: Game, dt: float = 0.0, *, interact_held: bool = False) -> None:
    game.update_gameplay(dt, pygame.Vector2(), interact_held=interact_held)


def freeze_creatures(game: Game) -> None:
    for creature in game.creatures:
        creature.movement_enabled = False


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview Floor 3 Echo Core extraction flow.")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    game = Game()
    try:
        game.placeholder_run = PlaceholderRun(
            seed=args.seed,
            floor=3,
            score=1100,
            completed_floor_count=2,
            floor_completion_summaries={1: {"floor": 1}, 2: {"floor": 2}},
        )
        game.run_exists = True
        game.prepare_generated_floor()
        game.state = GameState.PLAYING
        game.debug_world_view = True

        if not isinstance(game.floor_objectives, Floor3ObjectiveSystem):
            raise RuntimeError("Floor 3 objective content was not created.")
        if game.elevator_entity is None:
            raise RuntimeError("Floor 3 elevator was not created.")

        if not args.headless:
            print("Controls: WASD/arrows move, Space scan, F interact, F2 debug, F3 diagnostics, Esc pause.")
            game.run()
            return 0

        freeze_creatures(game)
        objectives = game.floor_objectives
        artifact_dir = ROOT / "artifacts"
        paths = {
            "initial": artifact_dir / f"floor3_preview_{args.seed}_initial.png",
            "component": artifact_dir / f"floor3_preview_{args.seed}_component.png",
            "component_collected": artifact_dir / f"floor3_preview_{args.seed}_component_collected.png",
            "control_progress": artifact_dir / f"floor3_preview_{args.seed}_control_progress.png",
            "containment_open": artifact_dir / f"floor3_preview_{args.seed}_containment_open.png",
            "core": artifact_dir / f"floor3_preview_{args.seed}_echo_core.png",
            "extraction": artifact_dir / f"floor3_preview_{args.seed}_extraction.png",
            "elevator": artifact_dir / f"floor3_preview_{args.seed}_elevator.png",
            "victory": artifact_dir / f"floor3_preview_{args.seed}_victory.png",
        }

        save_frame(game, paths["initial"])
        place_player_at(game, objectives.component.tile)
        save_frame(game, paths["component"])
        update(game)
        save_frame(game, paths["component_collected"])

        place_player_at(game, objectives.control.tile)
        update(game, settings.CONTAINMENT_INSTALL_DURATION * 0.5, interact_held=True)
        save_frame(game, paths["control_progress"])
        for _ in range(int(settings.CONTAINMENT_INSTALL_DURATION * settings.FPS) + 10):
            if objectives.state.control_active:
                break
            update(game, 1.0 / settings.FPS, interact_held=True)
        if not objectives.state.control_active:
            raise RuntimeError("Containment control did not activate.")
        save_frame(game, paths["containment_open"])

        place_player_at(game, objectives.echo_core.tile)
        save_frame(game, paths["core"])
        initial_creatures = len(game.creatures)
        update(game)
        if not objectives.state.echo_core_collected:
            raise RuntimeError("Echo Core was not collected.")
        save_frame(game, paths["extraction"])

        place_player_at(game, game.elevator_entity.tile)
        update(game, interact_held=False)
        save_frame(game, paths["elevator"])

        archived = {
            "component_collected": objectives.state.component_collected,
            "control_active": objectives.state.control_active,
            "containment_door_state": objectives.containment_door.state.name,
            "echo_core_collected": objectives.state.echo_core_collected,
            "containment_threat_event_id": objectives.state.containment_threat_event_id,
            "echo_core_threat_event_id": objectives.state.echo_core_threat_event_id,
            "creatures_before_extraction": initial_creatures,
            "creatures_during_extraction": len(game.creatures),
        }
        update(game, interact_held=True)
        save_frame(game, paths["victory"])

        run = game.placeholder_run
        containment_events = [
            event for event in game.threat_events.active_events
            if event.source_type is ThreatSourceType.CONTAINMENT_CONTROL
        ]
        core_events = [
            event for event in game.threat_events.active_events
            if event.source_type is ThreatSourceType.ECHO_CORE
        ]
        summary = run.floor_completion_summaries.get(3, {}) if run is not None else {}

        for name, path in paths.items():
            print(f"{name}_preview: {path}")
        print(f"containment_gate_edge: {objectives.placement.containment_gate_edge}")
        print(f"public_side_rooms: {objectives.placement.public_side_room_ids}")
        print(f"containment_side_rooms: {objectives.placement.containment_side_room_ids}")
        print(
            f"component: {objectives.component.unique_id} room={objectives.component.room_id} "
            f"tile={objectives.component.tile}"
        )
        print(
            f"control: {objectives.control.unique_id} room={objectives.control.room_id} "
            f"tile={objectives.control.tile}"
        )
        print(
            f"containment_door: {objectives.containment_door.unique_id} "
            f"tile={objectives.containment_door.tile}"
        )
        print(
            f"echo_core: {objectives.echo_core.unique_id} room={objectives.echo_core.room_id} "
            f"tile={objectives.echo_core.tile}"
        )
        print(f"archived_extraction_state: {archived}")
        print(f"active_containment_events_after_cleanup: {len(containment_events)}")
        print(f"active_echo_core_events_after_cleanup: {len(core_events)}")
        print(f"completed_floor_count: {run.completed_floor_count if run else 0}")
        print(f"final_score: {run.score if run else 0}")
        print(f"final_materials: {run.material_counts if run else {}}")
        print(f"floor3_summary: {summary}")
        print(f"runtime_generated_floor_present: {run.generated_floor is not None if run else False}")
        print(f"runtime_floor_objectives_present: {game.floor_objectives is not None}")
        print(f"runtime_player_present: {game.player is not None}")
        print(f"runtime_doors_count: {len(game.doors)}")
        print(f"runtime_creatures_count: {len(game.creatures)}")
        print(f"runtime_threat_events_count: {len(game.threat_events.active_events)}")
        print(f"runtime_scan_wave_active: {game.scan_system.active_wave is not None}")
        print(f"runtime_scan_traces_count: {len(game.scan_system.traces)}")
        print(f"runtime_snapshots_count: {len(game.snapshot_system.snapshots)}")
        print(f"game_state: {game.state.name}")
        return 0
    finally:
        game.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
