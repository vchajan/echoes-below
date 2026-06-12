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
from game.systems.threat_events import ThreatSourceType


def save_frame(game: Game, path: Path) -> None:
    game.render()
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(game.screen, str(path))


def place_player_at(game: Game, tile: tuple[int, int]) -> None:
    if game.player is None or game.camera is None:
        raise RuntimeError("Player and camera must exist before placing the player.")
    game.player.place_at_tile(tile)
    game.camera.update(game.player.world_position)


def update(game: Game, dt: float = 0.0, *, interact_held: bool = False) -> None:
    game.update_gameplay(dt, pygame.Vector2(), interact_held=interact_held)


def freeze_creatures(game: Game) -> None:
    for creature in game.creatures:
        creature.movement_enabled = False


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview Floor 1 restore-power objective flow.")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    game = Game()
    try:
        game.placeholder_run = PlaceholderRun(seed=args.seed, floor=1)
        game.run_exists = True
        game.prepare_generated_floor()
        game.state = GameState.PLAYING
        game.debug_world_view = True
        freeze_creatures(game)

        if game.floor_objectives is None or game.elevator_entity is None:
            raise RuntimeError("Floor 1 objective content was not created.")

        objectives = game.floor_objectives
        artifact_dir = ROOT / "artifacts"
        paths = {
            "initial": artifact_dir / f"floor1_preview_{args.seed}_initial.png",
            "component1": artifact_dir / f"floor1_preview_{args.seed}_component1.png",
            "components_complete": artifact_dir / f"floor1_preview_{args.seed}_components_complete.png",
            "repairing": artifact_dir / f"floor1_preview_{args.seed}_repairing.png",
            "powered": artifact_dir / f"floor1_preview_{args.seed}_powered.png",
            "elevator": artifact_dir / f"floor1_preview_{args.seed}_elevator.png",
            "workshop": artifact_dir / f"floor1_preview_{args.seed}_workshop.png",
        }

        save_frame(game, paths["initial"])

        component_a, component_b = objectives.components
        place_player_at(game, component_a.tile)
        update(game)
        save_frame(game, paths["component1"])

        place_player_at(game, component_b.tile)
        update(game)
        save_frame(game, paths["components_complete"])

        place_player_at(game, objectives.generator.tile)
        update(game, settings.GENERATOR_REPAIR_DURATION * 0.5, interact_held=True)
        save_frame(game, paths["repairing"])

        while not objectives.state.generator_repaired:
            update(game, 1.0 / settings.FPS, interact_held=True)
        save_frame(game, paths["powered"])

        place_player_at(game, game.elevator_entity.tile)
        update(game, 0.0, interact_held=False)
        save_frame(game, paths["elevator"])

        completion_summary = {
            "floor_power_active_before_cleanup": objectives.state.floor_power_active,
            "elevator_unlocked_before_cleanup": objectives.state.elevator_unlocked,
            "generator_powered_before_cleanup": objectives.generator.state.name,
            "generator_threat_event_id": objectives.state.generator_threat_event_id,
        }
        update(game, 0.0, interact_held=True)
        save_frame(game, paths["workshop"])

        generator_events = [
            event for event in game.threat_events.active_events
            if event.source_type is ThreatSourceType.GENERATOR
        ]
        materials = game.placeholder_run.material_counts if game.placeholder_run is not None else {}
        score = game.placeholder_run.score if game.placeholder_run is not None else 0
        completed_count = game.placeholder_run.completed_floor_count if game.placeholder_run is not None else 0

        print(f"initial_preview: {paths['initial']}")
        print(f"component1_preview: {paths['component1']}")
        print(f"components_complete_preview: {paths['components_complete']}")
        print(f"repairing_preview: {paths['repairing']}")
        print(f"powered_preview: {paths['powered']}")
        print(f"elevator_preview: {paths['elevator']}")
        print(f"workshop_preview: {paths['workshop']}")
        print(
            "component_a: "
            f"{component_a.unique_id} room={component_a.room_id} tile={component_a.tile}"
        )
        print(
            "component_b: "
            f"{component_b.unique_id} room={component_b.room_id} tile={component_b.tile}"
        )
        print(
            "generator: "
            f"{objectives.generator.unique_id} room={objectives.generator.room_id} "
            f"tile={objectives.generator.tile}"
        )
        print(f"repair_duration: {settings.GENERATOR_REPAIR_DURATION:0.2f}")
        print(f"completed_floor_summary_last_completed_floor: {game.last_completed_floor}")
        print(f"completed_floor_summary_count: {completed_count}")
        print(f"completed_floor_summary_score: {score}")
        print(f"completed_floor_summary_materials: {materials}")
        print(
            "archived_completion_state: "
            f"floor_power_before_cleanup={completion_summary['floor_power_active_before_cleanup']} "
            f"elevator_unlocked_before_cleanup={completion_summary['elevator_unlocked_before_cleanup']} "
            f"generator_state_before_cleanup={completion_summary['generator_powered_before_cleanup']} "
            f"generator_threat_event_id={completion_summary['generator_threat_event_id']}"
        )
        print(f"runtime_generated_floor_present: {game.placeholder_run.generated_floor is not None}")
        print(f"runtime_floor_objectives_present: {game.floor_objectives is not None}")
        print(f"runtime_floor_power_active: {game.floor_power_available}")
        print(f"runtime_elevator_entity_present: {game.elevator_entity is not None}")
        print(f"runtime_generator_entity_present: {game.floor_objectives is not None and game.floor_objectives.generator is not None}")
        print(f"runtime_player_present: {game.player is not None}")
        print(f"runtime_doors_count: {len(game.doors)}")
        print(f"runtime_creatures_count: {len(game.creatures)}")
        print(f"runtime_material_entities_count: {len(game.material_pickups)}")
        print(f"runtime_threat_events_count: {len(game.threat_events.active_events)}")
        print(f"runtime_generator_threats_count: {len(generator_events)}")
        print(f"runtime_scan_wave_active: {game.scan_system.active_wave is not None}")
        print(f"runtime_scan_traces_count: {len(game.scan_system.traces)}")
        print(f"runtime_snapshots_count: {len(game.snapshot_system.snapshots)}")
        print(f"game_state: {game.state.name}")

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
            game.render()
            pygame.display.flip()
            clock.tick(settings.FPS)
        return 0
    finally:
        game.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
