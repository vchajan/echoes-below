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
from game.entities.door import DoorState
from game.states import GameState
from game.systems.creature_ai import CreatureState
from game.systems.modules import MODULE_DEFINITIONS, ModuleType
from game.systems.threat_events import ThreatSourceType
from tools.smoke_test import (
    approach_tile_for_door,
    find_powered_door,
    find_visible_tile_for_creature,
    freeze_creatures,
    place_player_at,
)


def save_frame(game: Game, path: Path) -> None:
    game.render()
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(game.screen, str(path))


def grant_modules(game: Game) -> None:
    assert game.placeholder_run is not None
    run = game.placeholder_run
    run.material_counts = {"scrap": 20, "circuit": 20, "power_cell": 20}
    for definition in MODULE_DEFINITIONS:
        run.module_loadout.craft(definition.module_type, run.material_counts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview all active Echoes Below modules.")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    game = Game()
    try:
        game.next_seed = args.seed - 1
        game.start_new_run()
        grant_modules(game)
        assert game.placeholder_run is not None
        assert game.player is not None
        assert game.creatures
        freeze_creatures(game)

        if not args.headless:
            game.placeholder_run.module_loadout.equip(ModuleType.SHOCK_PULSE, 0)
            game.placeholder_run.module_loadout.equip(ModuleType.DECOY_BEACON, 1)
            print("Q/E activate equipped modules. F2 debug, F3 diagnostics.")
            game.run()
            return 0

        artifact_dir = ROOT / "artifacts"
        paths = {
            "shock": artifact_dir / f"module_preview_{args.seed}_shock.png",
            "decoy": artifact_dir / f"module_preview_{args.seed}_decoy.png",
            "wedge": artifact_dir / f"module_preview_{args.seed}_wedge.png",
            "projector": artifact_dir / f"module_preview_{args.seed}_projector.png",
            "cooldowns": artifact_dir / f"module_preview_{args.seed}_cooldowns.png",
        }

        run = game.placeholder_run
        run.module_loadout.equip(ModuleType.SHOCK_PULSE, 0)
        run.module_loadout.equip(ModuleType.DECOY_BEACON, 1)
        target = game.creatures[0]
        place_player_at(game, find_visible_tile_for_creature(game, target))
        if not game.activate_module_slot(0):
            raise RuntimeError("Shock Pulse preview activation failed")
        save_frame(game, paths["shock"])
        shock_state = target.ai.state.name if target.ai is not None else "NO_AI"

        if not game.activate_module_slot(1):
            raise RuntimeError("Decoy Beacon preview activation failed")
        game.update_gameplay(settings.DECOY_BEACON_PULSE_INTERVAL + 0.01, pygame.Vector2())
        save_frame(game, paths["decoy"])

        run.module_loadout.equip(ModuleType.DOOR_WEDGE, 0)
        run.module_loadout.equip(ModuleType.SCAN_PROJECTOR, 1)
        door = find_powered_door(game)
        door.force_open()
        place_player_at(game, approach_tile_for_door(game, door))
        if not game.activate_module_slot(0):
            raise RuntimeError("Door Wedge preview activation failed")
        save_frame(game, paths["wedge"])

        if not game.activate_module_slot(1):
            raise RuntimeError("Scan Projector preview activation failed")
        game.update_gameplay(settings.SCAN_PROJECTOR_ACTIVATION_DELAY + 0.01, pygame.Vector2())
        save_frame(game, paths["projector"])
        game.render()
        save_frame(game, paths["cooldowns"])

        for name, path in paths.items():
            print(f"{name}_preview: {path}")
        print(f"shock_target_state: {shock_state}")
        print(f"decoy_devices: {len(game.module_effects.decoys)}")
        print(f"decoy_pulses: {game.module_effects.diagnostics.decoy_pulses}")
        print(f"wedged_door: {door.door_id} state={door.state.name} remaining={door.wedge_remaining:0.2f}")
        print(f"projector_devices: {len(game.module_effects.projectors)}")
        print(f"projector_scans: {game.module_effects.diagnostics.projector_scans}")
        print(
            "module_threats:",
            [event.source_type.name for event in game.threat_events.active_events if event.source_type in {
                ThreatSourceType.SHOCK_PULSE,
                ThreatSourceType.DECOY_BEACON,
                ThreatSourceType.SCAN_PROJECTOR,
            }],
        )
        print(f"cooldowns: {run.module_runtime.snapshot()['cooldowns']}")
        print(f"scan_origin: {tuple(game.scan_system.active_wave.origin) if game.scan_system.active_wave else None}")
        print(f"game_state: {game.state.name}")
        if door.state is not DoorState.WEDGED_OPEN:
            raise RuntimeError("Door preview did not remain wedged open")
        if target.ai is not None and target.ai.state is not CreatureState.STUNNED:
            raise RuntimeError("Shock preview target was not stunned")
        return 0
    finally:
        game.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
