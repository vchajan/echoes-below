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
    parser = argparse.ArgumentParser(description="Preview Floor 2 security-override objective flow.")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    game = Game()
    try:
        game.placeholder_run = PlaceholderRun(
            seed=args.seed,
            floor=2,
            score=settings.GENERATOR_COMPONENT_SCORE * 2
            + settings.GENERATOR_REPAIR_SCORE
            + settings.FLOOR_COMPLETION_SCORE,
            completed_floor_count=1,
            floor_completion_summaries={
                1: {
                    "floor": 1,
                    "power_restored": True,
                    "elevator_unlocked": True,
                    "score": settings.GENERATOR_COMPONENT_SCORE * 2
                    + settings.GENERATOR_REPAIR_SCORE
                    + settings.FLOOR_COMPLETION_SCORE,
                }
            },
        )
        game.run_exists = True
        game.prepare_generated_floor()
        game.state = GameState.PLAYING
        game.debug_world_view = True

        if game.floor_objectives is None or game.elevator_entity is None:
            raise RuntimeError("Floor 2 objective content was not created.")

        if not args.headless:
            print("Controls: WASD/arrows move, Space scan, F interact, F2 debug, F3 diagnostics, Esc pause.")
            game.run()
            return 0

        freeze_creatures(game)
        objectives = game.floor_objectives
        artifact_dir = ROOT / "artifacts"
        paths = {
            "initial": artifact_dir / f"floor2_preview_{args.seed}_initial.png",
            "keycard": artifact_dir / f"floor2_preview_{args.seed}_keycard.png",
            "keycard_collected": artifact_dir / f"floor2_preview_{args.seed}_keycard_collected.png",
            "door_unlocked": artifact_dir / f"floor2_preview_{args.seed}_door_unlocked.png",
            "relay_a_progress": artifact_dir / f"floor2_preview_{args.seed}_relay_a_progress.png",
            "relay_a_active": artifact_dir / f"floor2_preview_{args.seed}_relay_a_active.png",
            "relay_b_progress": artifact_dir / f"floor2_preview_{args.seed}_relay_b_progress.png",
            "relays_complete": artifact_dir / f"floor2_preview_{args.seed}_relays_complete.png",
            "elevator": artifact_dir / f"floor2_preview_{args.seed}_elevator.png",
            "workshop": artifact_dir / f"floor2_preview_{args.seed}_workshop.png",
        }

        save_frame(game, paths["initial"])

        place_player_at(game, objectives.keycard.tile)
        save_frame(game, paths["keycard"])
        update(game)
        save_frame(game, paths["keycard_collected"])
        place_player_at(game, objectives.security_door.tile)
        update(game)
        save_frame(game, paths["door_unlocked"])

        relay_a, relay_b = objectives.relays
        place_player_at(game, relay_a.tile)
        update(game, settings.RELAY_ACTIVATION_DURATION * 0.5, interact_held=True)
        save_frame(game, paths["relay_a_progress"])
        for _ in range(int(settings.RELAY_ACTIVATION_DURATION * settings.FPS) + 10):
            if relay_a.state.name == "ACTIVE":
                break
            update(game, 1.0 / settings.FPS, interact_held=True)
        if relay_a.state.name != "ACTIVE":
            raise RuntimeError("Relay A did not activate during preview.")
        save_frame(game, paths["relay_a_active"])

        place_player_at(game, relay_b.tile)
        update(game, settings.RELAY_ACTIVATION_DURATION * 0.5, interact_held=True)
        save_frame(game, paths["relay_b_progress"])
        for _ in range(int(settings.RELAY_ACTIVATION_DURATION * settings.FPS) + 10):
            if objectives.state.both_relays_active:
                break
            update(game, 1.0 / settings.FPS, interact_held=True)
        if not objectives.state.both_relays_active:
            raise RuntimeError("Relay B did not activate during preview.")
        save_frame(game, paths["relays_complete"])

        place_player_at(game, game.elevator_entity.tile)
        update(game, 0.0, interact_held=False)
        save_frame(game, paths["elevator"])

        relay_events = [
            event for event in game.threat_events.active_events
            if event.source_type is ThreatSourceType.RELAY
        ]
        completion_summary = {
            "keycard_collected_before_cleanup": objectives.state.keycard_collected,
            "security_door_unlocked_before_cleanup": objectives.state.security_door_unlocked,
            "security_door_state_before_cleanup": objectives.security_door.state.name,
            "relay_a_active_before_cleanup": objectives.state.relay_a_active,
            "relay_b_active_before_cleanup": objectives.state.relay_b_active,
            "elevator_unlocked_before_cleanup": objectives.state.elevator_unlocked,
            "elevator_state_before_cleanup": game.elevator_entity.state.name,
            "relay_threat_event_ids": [event.event_id for event in relay_events],
            "relay_threat_strengths": [event.strength for event in relay_events],
            "creature_count_before_cleanup": len(game.creatures),
        }
        update(game, 0.0, interact_held=True)
        save_frame(game, paths["workshop"])

        run = game.placeholder_run
        preserved_summary = run.floor_completion_summaries.get(2, {}) if run is not None else {}
        materials = run.material_counts if run is not None else {}
        score = run.score if run is not None else 0
        completed_count = run.completed_floor_count if run is not None else 0

        print(f"initial_preview: {paths['initial']}")
        print(f"keycard_preview: {paths['keycard']}")
        print(f"keycard_collected_preview: {paths['keycard_collected']}")
        print(f"door_unlocked_preview: {paths['door_unlocked']}")
        print(f"relay_a_progress_preview: {paths['relay_a_progress']}")
        print(f"relay_a_active_preview: {paths['relay_a_active']}")
        print(f"relay_b_progress_preview: {paths['relay_b_progress']}")
        print(f"relays_complete_preview: {paths['relays_complete']}")
        print(f"elevator_preview: {paths['elevator']}")
        print(f"workshop_preview: {paths['workshop']}")
        print(f"security_gate_edge: {objectives.placement.security_gate_edge}")
        print(f"public_side_rooms: {objectives.placement.public_side_room_ids}")
        print(f"secure_side_rooms: {objectives.placement.secure_side_room_ids}")
        print(
            "keycard: "
            f"{objectives.keycard.unique_id} room={objectives.keycard.room_id} "
            f"tile={objectives.keycard.tile}"
        )
        print(
            "security_door: "
            f"{objectives.security_door.unique_id} tile={objectives.security_door.tile} "
            f"unlocked_before_cleanup={completion_summary['security_door_unlocked_before_cleanup']} "
            f"state_before_cleanup={completion_summary['security_door_state_before_cleanup']}"
        )
        print(
            "relay_a: "
            f"{relay_a.unique_id} room={relay_a.room_id} tile={relay_a.tile} "
            f"threat_id={objectives.state.relay_a_threat_event_id}"
        )
        print(
            "relay_b: "
            f"{relay_b.unique_id} room={relay_b.room_id} tile={relay_b.tile} "
            f"threat_id={objectives.state.relay_b_threat_event_id}"
        )
        print(f"relay_activation_duration: {settings.RELAY_ACTIVATION_DURATION:0.2f}")
        print(f"archived_completion_state: {completion_summary}")
        print(f"preserved_run_summary_last_completed_floor: {game.last_completed_floor}")
        print(f"preserved_run_summary_completed_floor_count: {completed_count}")
        print(f"preserved_run_summary_score: {score}")
        print(f"preserved_run_summary_materials: {materials}")
        print(f"preserved_run_summary_floor2: {preserved_summary}")
        print(f"cleared_runtime_generated_floor_present: {run.generated_floor is not None if run else False}")
        print(f"cleared_runtime_floor_objectives_present: {game.floor_objectives is not None}")
        print(f"cleared_runtime_floor_power_active: {game.floor_power_available}")
        print(f"cleared_runtime_elevator_entity_present: {game.elevator_entity is not None}")
        print(f"cleared_runtime_player_present: {game.player is not None}")
        print(f"cleared_runtime_doors_count: {len(game.doors)}")
        print(f"cleared_runtime_creatures_count: {len(game.creatures)}")
        print(f"cleared_runtime_material_entities_count: {len(game.material_pickups)}")
        print(f"cleared_runtime_threat_events_count: {len(game.threat_events.active_events)}")
        print(f"cleared_runtime_scan_wave_active: {game.scan_system.active_wave is not None}")
        print(f"cleared_runtime_scan_traces_count: {len(game.scan_system.traces)}")
        print(f"cleared_runtime_snapshots_count: {len(game.snapshot_system.snapshots)}")
        print(f"game_state: {game.state.name}")

        return 0
    finally:
        game.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
